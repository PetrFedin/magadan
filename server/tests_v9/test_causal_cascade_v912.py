"""V9.12 multi-period synthetic hydraulic and adequacy integrity tests."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from math import isfinite
import pytest

from hydro_api.causal_cascade_v912 import (
    Infeasible, InvalidInput, MonotoneCurve, ReservoirModel, Step,
    simulate_multiperiod, synthetic_demo,
)

BEGIN = datetime.fromisoformat("2026-11-01T00:00:00+03:00")


def steps(**changes):
    base = {
        "duration_hours": 24.0, "upstream_inflow_m3_s": 100.0,
        "lateral_inflow_m3_s": 30.0, "upper_turbine_m3_s": 80.0,
        "upper_bypass_m3_s": 0.0, "lower_turbine_m3_s": 75.0,
        "lower_bypass_m3_s": 0.0, "demand_mw": 120.0,
        "thermal_available_mw": 100.0, "stable_negative_temperatures": True,
    }
    base.update(changes)
    return tuple(
        Step(start=(BEGIN + timedelta(days=i)).isoformat(), **base)
        for i in range(8)
    )


def run(**changes):
    return synthetic_demo(steps=steps(**changes))


def test_baseline_is_algebraically_consistent_synthetic_only():
    r = synthetic_demo()
    assert r["status"] == "SYNTHETIC_CONSISTENT"
    assert r["energy_status"] == "NO_CALCULATED_SHORTFALL"
    assert r["period_count"] == 8
    assert len(r["steps"]) == 8
    assert abs(r["season_mass_residual_km3"]) < 1e-9
    assert r["production_ready"] is False
    assert r["real_available_capacity_mw"] is None
    assert r["water_rule_certification"] is False
    assert r["operator_calibrated_routing"] is False


def test_delayed_arrival_has_no_same_step_future_water():
    r = synthetic_demo()
    m = r["steps"]
    assert m[0]["delayed_arrival_km3"] == 0.0
    assert m[1]["delayed_arrival_km3"] == 0.0
    assert m[2]["delayed_arrival_km3"] == pytest.approx(
        m[0]["upper_release_to_transit_km3"], abs=1e-11)
    assert m[3]["delayed_arrival_km3"] == pytest.approx(
        m[1]["upper_release_to_transit_km3"], abs=1e-11)


def test_persistent_pipeline_is_counted_in_whole_cascade_mass():
    r = synthetic_demo()
    s = r["steps"][-1]
    left = r["initial_system_stock_km3"] + r["cumulative_exogenous_inflow_km3"]
    right = (r["cumulative_outlet_flow_km3"]
             + r["terminal_upstream_km3"] + r["terminal_downstream_km3"]
             + r["terminal_water_in_flight_km3"])
    assert left == pytest.approx(right, abs=1e-9)
    assert s["water_in_flight_end_km3"] > 0


def test_dynamic_head_varies_with_storage_not_fixed_constant():
    r = synthetic_demo()
    upper = [s["upper_net_head_assumed_m"] for s in r["steps"]]
    lower = [s["lower_net_head_assumed_m"] for s in r["steps"]]
    assert len(set(upper)) > 1
    assert len(set(lower)) > 1


def test_energy_accounting_closes_each_period():
    r = synthetic_demo()
    for x in r["steps"]:
        assert x["load_gwh"] == pytest.approx(
            x["hydro_gwh"] + x["thermal_gwh"]
            + x["deterministic_unserved_gwh"], abs=1e-8)
        assert abs(x["full_system_mass_residual_km3"]) < 1e-9


def test_thermal_outage_produces_shortfall_with_valid_water_route():
    r = run(thermal_available_mw=0.0, demand_mw=400.0)
    assert r["status"] == "SYNTHETIC_CONSISTENT"
    assert r["energy_status"] == "DETERMINISTIC_SHORTFALL"
    assert r["total_unserved_gwh"] > 0.0
    assert abs(r["season_mass_residual_km3"]) < 1e-9


def test_even_zero_demand_deficit_cannot_hide_cold_bypass():
    r = run(upper_bypass_m3_s=20, thermal_available_mw=1000.0)
    assert r["status"] == "INFEASIBLE_DISPATCH"
    assert r["energy_status"] == "NOT_EVALUATED"
    assert r["failing_step"] == 0
    assert r["total_unserved_gwh"] is None
    assert "COLD_PERIOD_BYPASS" in r["reason"]


def test_unknown_cold_weather_requires_data_not_fictional_compliance():
    r = run(lower_bypass_m3_s=2,
            stable_negative_temperatures=None)
    assert r["status"] == "DATA_INSUFFICIENT"
    assert r["energy_status"] == "NOT_EVALUATED"
    assert r["total_unserved_gwh"] is None
    assert r["production_ready"] is False


def test_explicit_non_cold_bypass_can_be_modeled_but_not_certified():
    r = run(lower_bypass_m3_s=1,
            stable_negative_temperatures=False)
    assert r["status"] == "SYNTHETIC_CONSISTENT"
    assert r["water_rule_certification"] is False


def test_inflow_overflow_without_legal_outlet_is_infeasible_not_clipped():
    r = run(upstream_inflow_m3_s=20000)
    assert r["status"] == "INFEASIBLE_DISPATCH"
    assert "INVENTORY_OVERFLOW_OR_UNDERFLOW" in r["reason"]
    assert r["total_unserved_gwh"] is None


def test_lower_inventory_cannot_use_unarrived_upstream_flow():
    r = run(lower_turbine_m3_s=2000)
    assert r["status"] == "INFEASIBLE_DISPATCH"
    assert r["failing_step"] == 0
    assert r["total_unserved_gwh"] is None


def test_unknown_real_curve_and_unverified_dispatch_fail_closed():
    r = synthetic_demo(mode="field")
    assert r["status"] == "DATA_INSUFFICIENT"
    assert r["energy_status"] == "NOT_EVALUATED"
    assert r["total_unserved_gwh"] is None
    assert r["steps"] == []
    assert r["real_available_capacity_mw"] is None


def test_explicit_hydro_energy_sinking_missing_is_infeasible():
    r = run(demand_mw=1.0, thermal_available_mw=0.0)
    assert r["status"] == "INFEASIBLE_DISPATCH"
    assert "NO_DEMAND_OR_EXPORT_SINK" in r["reason"]


def test_model_outputs_are_deterministic_identical_json_data():
    assert synthetic_demo() == synthetic_demo()


def test_non_monotonic_volume_stage_curve_rejected():
    with pytest.raises(InvalidInput, match="CURVE_NOT_STRICTLY_MONOTONIC"):
        MonotoneCurve(((1, 100), (2, 95)), "km3", "m_synthetic_datum")


def test_unsupported_authoritative_curve_never_fabricated():
    with pytest.raises(Exception, match="UNVERIFIED_REAL_CURVE"):
        MonotoneCurve(((1, 100), (2, 105)), "km3",
                      "m_synthetic_datum", provenance="OFFICIAL_VERIFIED")


def test_unlicensed_curve_extrapolation_is_forbidden():
    c = MonotoneCurve(((1.0, 100.0), (2.0, 115.0)),
                      "km3", "m_synthetic_datum")
    with pytest.raises(Infeasible, match="EXTRAPOLATION_FORBIDDEN"):
        c.at(2.1)


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf")])
def test_step_rejects_corrupt_flows(value):
    with pytest.raises(InvalidInput):
        Step(start=BEGIN.isoformat(), duration_hours=24,
             upstream_inflow_m3_s=value, lateral_inflow_m3_s=0,
             upper_turbine_m3_s=0, upper_bypass_m3_s=0,
             lower_turbine_m3_s=0, lower_bypass_m3_s=0,
             demand_mw=500, thermal_available_mw=10,
             stable_negative_temperatures=True)


@pytest.mark.parametrize("weather", [0, 1, "yes"])
def test_coldness_boolean_evidence_cannot_be_forged(weather):
    with pytest.raises(InvalidInput, match="UNSUPPORTED_COLDNESS"):
        steps(stable_negative_temperatures=weather)


def test_horizon_with_missing_step_rejected():
    s = steps()
    adjusted = (s[0], s[2])
    with pytest.raises(InvalidInput, match="HORIZON_HAS_GAP"):
        synthetic_demo(steps=adjusted)


def test_inconsistent_hour_widths_rejected():
    s = steps()
    changed = replace(s[1], duration_hours=12)
    with pytest.raises(InvalidInput, match="UNEQUAL_STEPS"):
        synthetic_demo(steps=(s[0], changed))


@pytest.mark.parametrize("delay", [0, -1, 31, 2.0, True])
def test_bad_routing_delay_rejected(delay):
    from hydro_api.causal_cascade_v912 import simulate_multiperiod
    original = simulate_multiperiod
    # Invalid delay can be exercised on the exact same engine by returning
    # the original independent synthetic ReservoirModel inputs via factory.
    from hydro_api.causal_cascade_v912 import ReservoirModel, MonotoneCurve
    c1 = MonotoneCurve(((1.0, 100.0), (2.0, 120.0)),
                       "km3", "m_synthetic_datum")
    c2 = MonotoneCurve(((0.0, 20.0), (100.0, 21.0)),
                       "m3/s", "m_synthetic_datum")
    spec = ReservoirModel("DELAY_TEST", c1, c2, 1.0, 2.0,
                          100.0, 400.0, 0.9, 1.0, 60.0, 130.0)
    with pytest.raises(InvalidInput, match="DELAY_NOT_POSITIVE"):
        original(upper=spec, lower=spec, steps=steps(),
                 initial_upper_km3=1.5, initial_lower_km3=1.5,
                 transit_delay_steps=delay)


def test_no_real_dispatch_claim_even_if_synthetic_no_shortfall():
    r = synthetic_demo()
    for flag in ("water_rule_certification", "production_ready",
                 "actual_stage_volume_curves_present",
                 "actual_unit_efficiency_curves_present",
                 "network_n_minus_one_verified",
                 "probabilistic_lole_eens_computed"):
        assert r[flag] is False
    assert r["investment_decision"] == "HOLD"
    assert r["real_available_capacity_mw"] is None


def test_committed_v912_receipt_matches_exact_input_files():
    """Persisted study must be reproducible from current input source bytes."""
    import hashlib
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    report = root / "artifacts_v9/magadan_causal_cascade_v912.json"
    assert report.is_file(), "V912_REPORT_NOT_COMMITTED"
    a = json.loads(report.read_text(encoding="utf-8"))
    raw = json.dumps({k:v for k,v in a.items() if k!="payload_sha256"},
                     sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")
    assert hashlib.sha256(raw).hexdigest() == a["payload_sha256"]
    assert len(a["source_sha256"]) == 4
    for source, receipt in a["source_sha256"].items():
        path = root / source
        assert path.is_file(), source
        assert hashlib.sha256(path.read_bytes()).hexdigest() == receipt, source
    assert a["experiment_count"] == len(a["results"]) == 8
    assert a["summary"] == {
        "synthetic_consistent_cases": 3,
        "infeasible_cases": 3,
        "insufficient_evidence_cases": 2,
        "calculated_shortfall_cases": 1,
        "zero_shortfall_overrides_a_hard_rule": False,
    }
    assert a["results"]["zero_shortfall_cannot_approve_cold_bypass"]["status"] == "INFEASIBLE_DISPATCH"
    assert a["results"]["real_world_sources_missing"]["total_unserved_gwh"] is None
    assert a["firm_capacity_mw"] is None
    assert a["production_ready"] is False


def test_independent_first_step_head_oracle():
    """Hand-calculated independently from the published SYNTHETIC knot values."""
    first = synthetic_demo()["steps"][0]
    # U_start=2.3; (100-80)*86400/1e9 = +0.001728 km3.
    # Mid U=2.300864; z=120+15*(2.300864-2)=124.51296.
    # Tailwater(80)=20+0.5*(80/100)=20.4; loss=1 -> H=103.11296.
    assert first["upper_net_head_assumed_m"] == pytest.approx(103.11296,abs=1e-9)
    # L_start=1.7; lateral(30)-lower turbine(75) produces -0.003888.
    # Mid L=1.698056; stage=61+14*(1.698056-1.5)=63.772784.
    # Tailwater(75)=25+0.5*(75/100)=25.375; loss=0.4.
    assert first["lower_net_head_assumed_m"] == pytest.approx(37.997784,abs=1e-9)


def test_independent_first_step_power_oracle_in_gwh():
    """Checks power/energy units without calling the production power helper."""
    first = synthetic_demo()["steps"][0]
    upper_mw = 1000*9.80665*80*103.11296*0.9/1e6
    lower_mw = 1000*9.80665*75*37.997784*0.9/1e6
    expected = (upper_mw + lower_mw)*24/1000
    assert expected == pytest.approx(2.351003170380984,abs=1e-12)
    assert first["hydro_gwh"] == pytest.approx(expected,abs=1e-9)
    assert first["thermal_gwh"] == pytest.approx(2.88-expected,abs=1e-9)


def test_bypass_water_is_delayed_even_when_no_hydro_generated_from_it():
    candidate = steps(upper_bypass_m3_s=10,
                      stable_negative_temperatures=False)
    r=synthetic_demo(steps=candidate)
    assert r["status"] == "SYNTHETIC_CONSISTENT"
    x=r["steps"]
    assert x[0]["delayed_arrival_km3"] == 0
    assert x[1]["delayed_arrival_km3"] == 0
    assert x[2]["delayed_arrival_km3"] == pytest.approx(
        (80+10)*86400/1e9,abs=1e-11)
    assert abs(r["season_mass_residual_km3"]) < 1e-9
    assert r["water_rule_certification"] is False
