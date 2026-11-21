"""V9.11 statutory-anchor necessary-screen, with deliberate fail-closed cases."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from hydro_api.normative_stage_v911 import (
    REFERENCE_PATH, EXPECTED, WINTER_MONTHS,
    decimal_value, load_catalog, validate_anchor_catalog,
    only_published_stage_anchor, seasonal_max_stage_bs,
    review_necessary_stage_bounds, review_daily_level_slew,
    hydraulic_power_synthetic_mw, review_winter_spill,
    review_v99_winter_grid, review_v910_reference_trajectories,
    build_v911_research_receipt,
)

ROOT = Path(__file__).resolve().parents[2]
V99_FILE = ROOT / "artifacts_v9/magadan_dispatch_policy_v99.json"
V910_FILE = ROOT / "artifacts_v9/magadan_terminal_reserve_stress_v910.json"


@pytest.fixture()
def catalog():
    return load_catalog()


@pytest.fixture()
def older_artifacts():
    return (json.loads(V99_FILE.read_text(encoding="utf-8")),
            json.loads(V910_FILE.read_text(encoding="utf-8")))


def test_reference_catalog_exists_and_has_no_authenticity_overclaim(catalog):
    assert REFERENCE_PATH.is_file()
    assert catalog["source_document"]["original_document_independently_checked"] is False
    assert catalog["source_document"]["primary_official_document_sha256"] is None
    assert catalog["full_stage_volume_curves_ingested"] is False
    assert catalog["real_operator_data_present"] is False
    assert catalog["production_ready"] is False
    assert catalog["seasonal_regime_guardrails"]["normative_section"] == "VIII, paragraphs 44-52"


def test_statutory_usable_and_forced_volumes_balance_exactly(catalog):
    result = validate_anchor_catalog(catalog)
    assert result["usable_identity_by_reservoir"]["kolyma"]["usable_km3"] == "7.239"
    assert result["usable_identity_by_reservoir"]["ust_srednekan"]["usable_km3"] == "2.573"
    assert result["data_periods_and_observation_methods_comparable"] is False
    assert result["official_source_bytes_independently_verified"] is False
    assert result["real_operator_approval"] is False


def test_source_annual_cascade_15_193_plus_9_820_exact(catalog):
    d = validate_anchor_catalog(catalog)
    assert d["annual_upper_outflow_plus_lateral_equals_lower_km3"] == "25.013"
    assert d["published_long_run_lateral_km3_per_year"] == "9.820"
    assert d["absolute_lateral_reference_difference_km3_per_year"] == "5.320"


@pytest.mark.parametrize("reservoir,usable,forced", [
    ("kolyma", "7.239", "2.884"),
    ("ust_srednekan", "2.573", "0.649"),
])
def test_necessary_volume_anchors_are_not_synthetic_fractions(catalog,reservoir,usable,forced):
    a = catalog["reservoirs"][reservoir]
    assert Decimal(a["usable_volume_km3"]) == Decimal(usable)
    assert Decimal(a["forced_volume_km3"]) == Decimal(forced)
    assert Decimal(a["total_volume_km3"]["npu"]) - Decimal(a["total_volume_km3"]["umo"]) == Decimal(usable)
    assert Decimal(a["total_volume_km3"]["fpu"]) - Decimal(a["total_volume_km3"]["npu"]) == Decimal(forced)


@pytest.mark.parametrize("reservoir,anchor", [
    ("kolyma","umo"),("kolyma","npu"),("kolyma","fpu"),
    ("ust_srednekan","umo"),("ust_srednekan","npu"),("ust_srednekan","fpu"),
])
def test_only_exact_statutory_anchor_is_available_not_full_curve(catalog,reservoir,anchor):
    level=catalog["reservoirs"][reservoir]["stage_m_bs"][anchor]
    obj=only_published_stage_anchor(catalog,reservoir,level)
    assert Decimal(obj["total_volume_km3"]) == Decimal(
        catalog["reservoirs"][reservoir]["total_volume_km3"][anchor])
    assert obj["interpolation_performed"] is False
    assert obj["engineering_approval"] is False


@pytest.mark.parametrize("reservoir,between", [
    ("kolyma","440"),("ust_srednekan","285")
])
def test_intermediate_real_volume_cannot_be_invented(catalog,reservoir,between):
    with pytest.raises(ValueError,match="NON_ANCHOR_CURVE_NOT_DIGITIZED"):
        only_published_stage_anchor(catalog,reservoir,between)


def test_kolyma_bs_os_offset_is_explicit_and_no_ust_os_conversion(catalog):
    assert Decimal(catalog["reservoirs"]["kolyma"]["stage_m_bs"]["npu"]) + Decimal("0.94") == Decimal("451.50")
    assert catalog["reservoirs"]["ust_srednekan"]["os_above_bs_m"] is None


@pytest.mark.parametrize("key,field,value", [
    ("kolyma","usable_volume_km3","7.24"),
    ("ust_srednekan","forced_volume_km3","0.65"),
    ("kolyma","maximum_daily_drawdown_m","1.5"),
    ("ust_srednekan","installed_capacity_mw","900"),
])
def test_tampered_normative_anchor_is_rejected(catalog,key,field,value):
    modified=deepcopy(catalog)
    modified["reservoirs"][key][field]=value
    with pytest.raises(ValueError,match="NORMATIVE_ANCHOR_DRIFT"):
        validate_anchor_catalog(modified)


def test_lateral_original_4_5_cannot_replace_published_9_82(catalog):
    modified=deepcopy(catalog)
    modified["historical_long_run_water_balance"]["lateral_lower_inflow_km3_per_year"]="4.5"
    with pytest.raises(ValueError,match="ANNUAL_CASCADE_FLOW_IDENTITY"):
        validate_anchor_catalog(modified)


def test_source_version_and_primary_sha_claims_fail_closed(catalog):
    x=deepcopy(catalog)
    x["source_document"]["order_number"]="287"
    with pytest.raises(ValueError,match="SOURCE_VERSION"):
        validate_anchor_catalog(x)
    x=deepcopy(catalog)
    x["source_document"]["original_document_independently_checked"]=True
    with pytest.raises(ValueError,match="UNSUPPORTED_PRIMARY"):
        validate_anchor_catalog(x)
    x=deepcopy(catalog)
    x["source_document"]["primary_official_document_sha256"]="0"*64
    with pytest.raises(ValueError,match="UNSIGNED_ORIGINAL"):
        validate_anchor_catalog(x)


def test_incomplete_curve_cannot_claim_calibrated_status(catalog):
    x=deepcopy(catalog)
    x["full_stage_volume_curves_ingested"]=True
    with pytest.raises(ValueError,match="UNVERIFIED_STAGE_VOLUME_CURVE"):
        validate_anchor_catalog(x)


@pytest.mark.parametrize("day,cap",[
    (date(2026,5,20),"450.56"),(date(2026,5,21),"456.66"),
    (date(2026,9,30),"456.66"),(date(2026,10,1),"450.56"),
    (date(2027,1,15),"450.56")
])
def test_seasonal_cap_switch_on_may21_and_oct1(catalog,day,cap):
    assert seasonal_max_stage_bs(catalog,"kolyma",day) == Decimal(cap)


def test_necessary_stage_gate_does_not_approve_operation(catalog):
    ok=review_necessary_stage_bounds(catalog,"kolyma",date(2026,1,15),"445")
    assert ok["status"]=="NECESSARY_STAGE_BOUND_ONLY"
    assert ok["comprehensive_dispatch_compliance_established"] is False
    over=review_necessary_stage_bounds(catalog,"kolyma",date(2026,1,15),"451")
    assert "ABOVE_SEASONAL_STATUTORY_CAP" in over["violations"]
    below=review_necessary_stage_bounds(catalog,"ust_srednekan",date(2026,6,1),"277.99")
    assert "BELOW_STATUTORY_UMO" in below["violations"]


def test_flood_cap_does_not_automatically_mean_operationally_admissible(catalog):
    r=review_necessary_stage_bounds(catalog,"ust_srednekan",date(2026,6,1),"292")
    assert r["status"]=="NECESSARY_STAGE_BOUND_ONLY"
    assert r["comprehensive_dispatch_compliance_established"] is False


@pytest.mark.parametrize("reservoir,prev,next_value,elapsed,breach",[
    ("kolyma","450","448.9","1",True),
    ("kolyma","450","449.1","1",False),
    ("kolyma","430","433","1",False),
    ("ust_srednekan","289","290.1","1",True),
    ("ust_srednekan","289","289.9","1",False),
    ("ust_srednekan","290","288","2",False),
])
def test_daily_stage_slew_screen(catalog,reservoir,prev,next_value,elapsed,breach):
    out=review_daily_level_slew(catalog,reservoir,prev,next_value,elapsed)
    assert out["rate_bound_breached"] is breach
    assert out["full_hydraulic_operating_constraints_verified"] is False


def test_elapsed_time_cannot_be_zero(catalog):
    with pytest.raises(ValueError,match="INVALID_ELAPSED_DAYS"):
        review_daily_level_slew(catalog,"kolyma","445","444","0")


@pytest.mark.parametrize("bad",[-1,"NaN","Infinity",True,False,None,{}])
def test_numeric_parser_rejects_corrupt_quantities(bad):
    with pytest.raises(ValueError):
        decimal_value(bad,"quantity")


def test_synthetic_power_follows_units_and_cannot_certify_capacity(catalog):
    p=hydraulic_power_synthetic_mw(catalog,"kolyma","100","108","0.9")
    assert p == Decimal("95.32063800")
    assert p < Decimal(catalog["reservoirs"]["kolyma"]["installed_capacity_mw"])


@pytest.mark.parametrize("key,q,head,eff",[
    ("kolyma","100","89.999","0.9"),
    ("kolyma","100","119.1","0.9"),
    ("ust_srednekan","100","37.9","0.9"),
    ("ust_srednekan","100","61.1","0.9"),
])
def test_physical_calculation_refuses_head_outside_published_range(catalog,key,q,head,eff):
    with pytest.raises(ValueError,match="HEAD_OUTSIDE_PUBLISHED"):
        hydraulic_power_synthetic_mw(catalog,key,q,head,eff)


@pytest.mark.parametrize("q,head,eff", [
    ("-1","108","0.9"),("100","108","1.01"),("100","108","0"),
    ("100","108","NaN"),("100","108",True),
])
def test_synthetic_power_rejects_bad_inputs(catalog,q,head,eff):
    with pytest.raises(ValueError):
        hydraulic_power_synthetic_mw(catalog,"kolyma",q,head,eff)


def test_synthetic_mechanical_power_over_installed_rating_is_rejected(catalog):
    with pytest.raises(ValueError,match="EXCEEDS_INSTALLED_RATING"):
        hydraulic_power_synthetic_mw(catalog,"kolyma","3000","108","0.9")


def test_viii52_winter_spill_with_unknown_weather_is_conditional():
    result=review_winter_spill(1,"0","0.25")
    assert result["status"]=="POTENTIAL_VIII_52_CONFLICT_PENDING_COLDNESS_EVIDENCE"
    assert result["legally_compliant"] is None


def test_viii52_winter_spill_with_confirmed_negative_temperatures_conflicts():
    result=review_winter_spill(12,"0.001","0",True)
    assert result["status"]=="CONFLICT_WITH_VIII_52_DURING_CONFIRMED_STABLE_COLD"
    assert result["temperature_condition_verified"] is True


def test_viii52_without_stable_cold_cannot_prove_full_compliance():
    r=review_winter_spill(10,"0.01","0",False)
    assert r["status"]=="STABLE_NEGATIVE_TEMPERATURE_CONDITION_NOT_MET_OTHER_RULES_UNVERIFIED"
    assert r["legally_compliant"] is None


def test_zero_winter_spill_does_not_mean_normative_compliance():
    r=review_winter_spill(11,0,0)
    assert r["status"]=="NO_NON_TURBINE_SPILL_DETECTED_OTHER_RULES_UNVERIFIED"
    assert r["legally_compliant"] is None


def test_nonwinter_spill_does_not_rely_on_viii52():
    r=review_winter_spill(6,"5","1")
    assert r["status"]=="NOT_REVIEWED_BY_WINTER_SECTION_VIII_52"


@pytest.mark.parametrize("invalid",["NaN","Infinity",True,-1])
def test_winter_spill_corrupt_input_rejected(invalid):
    with pytest.raises(ValueError):
        review_winter_spill(1,invalid,0)


def test_small_rounding_volume_not_treated_as_real_spill():
    r=review_winter_spill(1,Decimal("0.0000000001"),0,True)
    assert r["positive_non_turbine_release"] is False


def test_v99_full_grid_review_has_no_certified_cases(catalog,older_artifacts):
    v99,_=older_artifacts
    result=review_v99_winter_grid(catalog,v99)
    assert result["v99_total_selected_scenarios"]==216
    for policy in ("thermal_first","hydro_first"):
        assert result["policy_winter_non_turbine_screening"][policy]["cases_certified_compliant"]==0
    assert result["observed_real_operating_regime_assessed"] is False
    assert result["regulatory_admission"]=="HOLD"


def test_v99_spill_screen_is_independent_of_hydro_output(catalog,older_artifacts):
    v99,_=older_artifacts
    result=review_v99_winter_grid(catalog,v99)
    row=result["policy_winter_non_turbine_screening"]
    assert row["thermal_first"]["selected_cases_with_positive_lower_non_turbine_winter_release"]>0
    assert (row["thermal_first"]["selected_cases_with_positive_lower_non_turbine_winter_release"]
            +row["thermal_first"]["selected_cases_without_reported_lower_non_turbine_release"])==216
    assert row["upper_spill_series_in_complete_v99_grid_available"] is False


def test_v910_only_detailed_references_can_be_screened(catalog,older_artifacts):
    _,v910=older_artifacts
    out=review_v910_reference_trajectories(catalog,v910)
    assert out["v910_selected_scenario_rows"]==384
    assert out["fully_detailed_reference_scenarios_only"]==4
    assert out["reference_trajectory_variants_checked"]==12
    assert out["reference_months_checked"]==72
    assert out["remaining_undetailed_scenarios_not_certified"]==380
    assert out["regulatory_admission"]=="HOLD"


def test_compiled_receipt_refuses_unsupported_claims(catalog,older_artifacts):
    v99,v910=older_artifacts
    inputs={
        "data/reference/kolyma_cascade_rules_2025_v911.json":
            hashlib.sha256(REFERENCE_PATH.read_bytes()).hexdigest(),
        "artifacts_v9/magadan_dispatch_policy_v99.json":
            hashlib.sha256(V99_FILE.read_bytes()).hexdigest(),
        "artifacts_v9/magadan_terminal_reserve_stress_v910.json":
            hashlib.sha256(V910_FILE.read_bytes()).hexdigest(),
    }
    report=build_v911_research_receipt(catalog,v99,v910,inputs)
    assert report==build_v911_research_receipt(catalog,v99,v910,inputs)
    assert report["official_document_original_bytes_verified"] is False
    assert report["field_data_or_operator_approval"] is False
    assert report["firm_capacity_mw"] is None
    assert report["investment_decision"]=="HOLD"
    assert report["production_ready"] is False
    assert len(report["payload_sha256"])==64
