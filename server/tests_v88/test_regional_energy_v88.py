"""V8.8 regional energy mathematical contract, no-real-data safeguards, HTTP roles."""
import calendar
from copy import deepcopy
from decimal import Decimal
from sqlalchemy import select, func
import pytest
from pydantic import ValidationError

from hydro_api.regional_energy_v88 import (
    RegionalEnergyDecisionV88, evaluate_regional_energy_v88,
)
from hydro_api.storage import (
    StudyRun, BenefitReservationV79, Initiative, AuditEvent,
)
from tests_v88.fixture import synthetic_region_v88


BASE = "/v88/orgs/magadan-lab/regional-energy/evaluate"


def evaluated(mw=50, **kwargs):
    data = synthetic_region_v88(mw, **kwargs)
    return evaluate_regional_energy_v88(RegionalEnergyDecisionV88.model_validate(data))


def test_10_50_150_mw_monthly_demand_is_calculated_not_assumed():
    for mw in (10, 50, 150):
        x = evaluated(mw)
        assert x["annual_hours"] == 8760
        assert x["portfolio_conservative_coincident_peak_mw"] == mw
        assert x["annual_requested_new_energy_mwh"] == mw * .85 * 8760
        normal = x["scenarios"][0]
        assert normal["code"] == "NORMAL"
        for month in normal["months"]:
            expected = mw * 0.85 * calendar.monthrange(2031, month["month"])[1] * 24
            assert abs(month["new_load_requested_mwh"] - expected) < 1e-6
        assert normal["new_load_requested_mwh"] == mw * 0.85 * 8760
        assert x["investment_decision"] == "HOLD"
        assert x["financial_ledger_eligible"] is False


def test_deficit_and_coincident_peak_are_separate_and_never_dispatch():
    x = evaluated(150)
    scenarios = {s["code"]: s for s in x["scenarios"]}
    assert scenarios["NORMAL"]["all_months_feasible"]
    assert scenarios["LOW_WATER"]["incremental_energy_shortfall_mwh"] > 0
    assert not scenarios["LOW_WATER"]["all_months_feasible"]
    assert scenarios["NETWORK_CONTINGENCY"]["maximum_coincident_peak_shortfall_mw"] > 0
    assert not scenarios["NETWORK_CONTINGENCY"]["all_months_feasible"]
    assert x["synthetic_all_scenarios_adequate"] is False
    assert x["modelled_operational_adequacy"] == "DEFICIT_OR_RELIABILITY_LIMIT"
    assert x["production_dispatch_eligible"] is False
    assert x["financial_ledger_eligible"] is False
    assert x["investment_decision"] == "HOLD"
    assert "NO_NETWORK_TOPOLOGY_OR_N_MINUS_ONE_EMERGENCY_CONSTRAINTS" in x["limitations"]


def test_all_synthetic_scenarios_can_pass_without_financial_or_dispatch_authority():
    d = synthetic_region_v88(10)
    for month in d["scenarios"][2]["months"]:
        month["regional_network_deliverable_peak_mw"] = 840
    x = evaluate_regional_energy_v88(RegionalEnergyDecisionV88.model_validate(d))
    assert x["synthetic_all_scenarios_adequate"] is True
    assert x["modelled_operational_adequacy"] == "PASS_SYNTHETIC_ASSUMPTIONS_ONLY"
    assert x["investment_decision"] == "HOLD"
    assert x["production_dispatch_eligible"] is False
    assert x["financial_ledger_eligible"] is False
    assert all(s["all_months_feasible"] for s in x["scenarios"])


def test_overstated_reserve_produces_explicit_violation_and_zero_firm_peak():
    d = synthetic_region_v88(10)
    d["scenarios"][0]["months"][0]["firm_operating_reserve_mw"] = 2000
    x = evaluate_regional_energy_v88(RegionalEnergyDecisionV88.model_validate(d))
    january = x["scenarios"][0]["months"][0]
    assert january["firm_peak_after_reserve_mw"] == 0
    assert "FIRM_RESERVE_EXCEEDS_TRANSFER_OR_GENERATION" in january["violations"]
    assert x["investment_decision"] == "HOLD"


def test_baseline_unserved_is_not_mislabelled_as_new_project_shortfall():
    d = synthetic_region_v88(10)
    for s in d["scenarios"]:
        for m in s["months"]:
            m["existing_demand_energy_mwh"] = 350_000
            m["existing_coincident_peak_mw"] = 700
    x = evaluate_regional_energy_v88(RegionalEnergyDecisionV88.model_validate(d))
    jan = x["scenarios"][0]["months"][0]
    assert jan["baseline_energy_shortfall_mwh"] == 30_000
    assert jan["incremental_energy_shortfall_mwh"] == 10 * 0.85 * 744
    assert jan["total_energy_shortfall_mwh"] == 30_000 + 10 * 0.85 * 744


def test_full_year_leap_vs_regular_uses_actual_month_hours():
    leap = evaluated(10, year=2032)
    plain = evaluated(10, year=2031)
    assert leap["annual_hours"] == 8784
    assert plain["annual_hours"] == 8760
    assert leap["annual_requested_new_energy_mwh"] - plain["annual_requested_new_energy_mwh"] == 204.0
    assert leap["scenarios"][0]["months"][1]["hours"] == 696
    assert plain["scenarios"][0]["months"][1]["hours"] == 672


def test_conditional_npv_is_decimal_reproducible_and_never_certified():
    x = evaluated(50)
    p = x["conditional_project_economics"][0]
    expected_energy = Decimal("50") * Decimal("0.85") * Decimal(8760)
    expected_flow = expected_energy * (Decimal("12000")-Decimal("5500"))-Decimal("40000000")
    assert Decimal(p["annual_net_cashflow_if_fully_supplied_rub"]) == expected_flow
    annuity = sum(Decimal(1)/(Decimal(1)+Decimal("0.10"))**i for i in range(1,13))
    expected = Decimal("-1500000000") + expected_flow*annuity
    assert abs(Decimal(p["conditional_npv_if_fully_supplied_rub"])-expected) < Decimal("0.02")
    assert p["real_revenue_or_costs_verified"] is False
    assert p["eligible_for_investment_approval"] is False
    assert evaluated(50) == evaluated(50)


@pytest.mark.parametrize("case,expected", [
    ("duplicate_projects", "DUPLICATE_PROJECT_ID"),
    ("duplicate_months", "SCENARIO_REQUIRES_ALL_12_DISTINCT_MONTHS"),
    ("duplicate_scenarios", "THREE_DISTINCT_REQUIRED_SCENARIOS"),
    ("bad_source", "string_pattern_mismatch"),
    ("missing_attestation", "literal_error"),
    ("impossible_monthly_generation", "GENERATION_ENERGY_EXCEEDS_FIRM_POWER_TIMES_HOURS"),
    ("impossible_existing_demand", "EXISTING_ENERGY_EXCEEDS_PEAK_TIMES_HOURS"),
    ("wrong_drought", "LOW_WATER_HYDRO_CANNOT_EXCEED_NORMAL"),
    ("wrong_contingency", "CONTINGENCY_NETWORK_LIMIT_CANNOT_EXCEED_NORMAL"),
    ("negative_mw", "greater_than"),
    ("boolean_power", "BOOLEAN_NOT_A_QUANTITY"),
    ("boolean_monthly_demand", "BOOLEAN_NOT_A_QUANTITY"),
    ("boolean_discount", "BOOLEAN_NOT_A_QUANTITY"),
    ("too_many_projects", "too_long"),
    ("unknown_fields", "extra_forbidden"),
])
def test_untrustworthy_inputs_fail_closed(case, expected):
    d = synthetic_region_v88()
    if case == "duplicate_projects":
        d["projects"].append(deepcopy(d["projects"][0]))
    elif case == "duplicate_months":
        d["scenarios"][0]["months"][2]["month"] = 2
    elif case == "duplicate_scenarios":
        d["scenarios"][2]["code"] = "LOW_WATER"
    elif case == "bad_source":
        d["source_ref"] = "NOT-REAL-SCADA-SOURCE"
    elif case == "missing_attestation":
        d["real_source_attested"] = True
    elif case == "impossible_monthly_generation":
        d["scenarios"][0]["months"][0]["firm_generation_peak_mw"] = 40
    elif case == "impossible_existing_demand":
        d["scenarios"][0]["months"][0]["existing_coincident_peak_mw"] = 1
    elif case == "wrong_drought":
        d["scenarios"][1]["months"][0]["hydro_deliverable_energy_mwh"] = 900_000
        d["scenarios"][1]["months"][0]["firm_generation_peak_mw"] = 2000
    elif case == "wrong_contingency":
        d["scenarios"][2]["months"][0]["regional_network_deliverable_peak_mw"] = 1600
    elif case == "negative_mw":
        d["projects"][0]["rated_mw"] = -1
    elif case == "boolean_power":
        d["projects"][0]["rated_mw"] = True
    elif case == "boolean_monthly_demand":
        d["scenarios"][0]["months"][0]["existing_demand_energy_mwh"] = False
    elif case == "boolean_discount":
        d["discount_rate_fraction"] = True
    elif case == "too_many_projects":
        for i in range(12):
            p = deepcopy(d["projects"][0])
            p["project_id"] += "-" + str(i)
            d["projects"].append(p)
    elif case == "unknown_fields":
        d["operator_dispatch_signal"] = "START"
    with pytest.raises(ValidationError, match=expected):
        RegionalEnergyDecisionV88.model_validate(d)


def test_http_roles_tenants_deterministic_proof_and_immutability(env):
    c, h = env["client"], env["h"]
    body = synthetic_region_v88(50)
    with env["db"]() as db:
        baseline = tuple(db.scalar(select(func.count()).select_from(model))
                         for model in (StudyRun, BenefitReservationV79, Initiative, AuditEvent))
    eng = c.post(BASE, headers=h("lead"), json=body)
    aud = c.post(BASE, headers=h("audit"), json=body)
    assert eng.status_code == 200, eng.text
    assert aud.status_code == 200, aud.text
    assert eng.json() == aud.json()
    receipt = eng.json()["proof"]
    assert receipt["financial_ledger_updated"] is False
    assert receipt["stateful_record_saved"] is False
    assert receipt["dispatch_recommendation"] is None
    for k in ("input_sha256","report_sha256","engine_sha256"):
        assert len(receipt[k]) == 64
    assert c.post(BASE, json=body).status_code == 401
    for role in ("finance", "manager", "viewer"):
        assert c.post(BASE, headers=h(role), json=body).status_code == 403
    assert c.post(BASE, headers=h("other"), json=body).status_code == 404
    assert c.post("/v88/orgs/separate-org/regional-energy/evaluate", headers=h("lead"), json=body).status_code == 404
    with env["db"]() as db:
        after = tuple(db.scalar(select(func.count()).select_from(model))
                      for model in (StudyRun, BenefitReservationV79, Initiative, AuditEvent))
    assert after == baseline


def test_http_real_asset_source_or_approval_claims_blocked(env):
    c,h=env["client"],env["h"]
    d=synthetic_region_v88()
    d["source_ref"] = "COLYMA-SCADA-2026"
    assert c.post(BASE,headers=h("lead"),json=d).status_code == 422
    d=synthetic_region_v88()
    d["independent_engineering_approval"] = True
    assert c.post(BASE,headers=h("lead"),json=d).status_code == 422
    d=synthetic_region_v88()
    d["corporate_financial_approval"] = True
    assert c.post(BASE,headers=h("lead"),json=d).status_code == 422
    r = c.get("/v88/meta/regional-energy-readiness")
    assert r.status_code == 200
    assert r.json()["production_ready"] is False
    assert r.json()["real_magadan_source_data_verified"] is False
