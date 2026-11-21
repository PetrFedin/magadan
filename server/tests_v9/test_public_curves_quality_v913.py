"""V9.13 independent public table candidate QA; real dispatch always blocked."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import pytest

from hydro_api.public_curves_quality_v913 import (
    DIR, SOURCE_EXPECTED, MISSING, RESEARCH, load_candidate,
    validate_volume_candidate, candidate_volume_at_stage,
    candidate_exact_inverse, review_quarantined_public_tables,
    validate_second_publisher_partial_crosscheck,
)

ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("site,rows,coordinates,ties",[
    ("kolyma",111,1101,0),
    ("ust_srednekan",71,701,73),
])
def test_full_public_source_grids_are_exact_and_contiguous(site,rows,coordinates,ties):
    a=load_candidate(site)
    evidence=validate_volume_candidate(a,site)
    assert evidence["source_rows"]==rows
    assert evidence["numeric_coordinates"]==coordinates
    assert evidence["adjacent_equal_rounded_volumes"]==ties
    assert evidence["physical_operation_admitted"] is False
    assert evidence["source_is_secondary"] is True
    assert len(a["rows"][-1]["volume_km3_by_0p1m_offset"])==1


@pytest.mark.parametrize("site,stage,volume",[
    ("kolyma","431.06","7.838"),
    ("kolyma","450.56","15.077"),
    ("kolyma","456.66","17.961"),
    ("ust_srednekan","278.00","2.863"),
    ("ust_srednekan","290.00","5.436"),
    ("ust_srednekan","292.30","6.085"),
])
def test_statutory_section_v_volume_anchors_match_independently(site,stage,volume):
    r=candidate_volume_at_stage(site,stage)
    assert Decimal(r["rounded_table_volume_km3"])==Decimal(volume)
    assert r["interpolated_within_0p1m_published_grid"] is False
    assert r["approved_real_curve"] is False


def test_full_kolyma_vertical_datum_offset_is_0p94m():
    a=load_candidate("kolyma")
    for row in a["rows"]:
        assert (Decimal(row["stage_os_base_m"])
                -Decimal(row["stage_bs_base_m"]))==Decimal("0.94")
    assert candidate_volume_at_stage("kolyma","450.56")[
        "rounded_table_volume_km3"]=="15.077"


def test_lower_stage_rounded_flat_volume_does_not_allow_unique_inverse():
    a=load_candidate("ust_srednekan")
    assert a["adjacent_equal_rounded_volumes"]==73
    result=candidate_exact_inverse("ust_srednekan","0.000")
    assert result["status"]=="AMBIGUOUS_INVERSE_DUE_TO_ROUNDED_PLATEAU"
    assert result["unique_stage_m_bs"] is None
    assert Decimal(result["candidate_stage_interval_m_bs"][1]) > Decimal(
        result["candidate_stage_interval_m_bs"][0])


def test_candidate_stage_interpolation_is_visible_and_never_operator_approved():
    r=candidate_volume_at_stage("kolyma","450.61")
    assert r["status"]==RESEARCH
    assert r["interpolated_within_0p1m_published_grid"] is True
    assert r["firm_capacity_mw"] is None
    assert r["approved_real_curve"] is False
    left=Decimal(candidate_volume_at_stage("kolyma","450.56")[
        "rounded_table_volume_km3"])
    right=Decimal(candidate_volume_at_stage("kolyma","450.66")[
        "rounded_table_volume_km3"])
    assert left<Decimal(r["rounded_table_volume_km3"])<right


def test_field_mode_always_refuses_candidate_curve_before_interpolation():
    r=candidate_volume_at_stage("kolyma","450.56",mode="field")
    assert r["status"]==MISSING
    assert r["volume_km3"] is None
    assert r["approved_real_curve"] is False


@pytest.mark.parametrize("site,stage",[
    ("kolyma","369.05"),("kolyma","479.07"),
    ("ust_srednekan","229.90"),("ust_srednekan","300.10")
])
def test_no_stage_curve_extrapolation(site,stage):
    with pytest.raises(ValueError,match="EXTRAPOLATION_NOT_PERMITTED"):
        candidate_volume_at_stage(site,stage)


def test_source_cannot_silently_claim_primary_authenticity():
    d=load_candidate("kolyma")
    wrong=deepcopy(d)
    wrong["source"]["primary_official_original_authenticity_verified"]=True
    with pytest.raises(ValueError,match="FORGED_APPROVAL"):
        validate_volume_candidate(wrong,"kolyma")


def test_source_cannot_become_operational_ready_while_unreviewed():
    d=load_candidate("ust_srednekan")
    d["operational_use_allowed"]=True
    with pytest.raises(ValueError,match="CANDIDATE_NOT_QUARANTINED"):
        validate_volume_candidate(d,"ust_srednekan")


def test_missing_upper_row_is_detected_not_interpolated():
    d=load_candidate("kolyma")
    d["rows"].pop(30)
    with pytest.raises(ValueError,match="ROW_COUNT_MISMATCH"):
        validate_volume_candidate(d,"kolyma")


def test_malformed_volume_or_wrong_vertical_datum_rejected():
    d=load_candidate("kolyma")
    d["rows"][1]["volume_km3_by_0p1m_offset"][5]="1.002bad"
    with pytest.raises(ValueError,match="ROUNDED_VOLUME_FORMAT"):
        validate_volume_candidate(d,"kolyma")
    x=load_candidate("kolyma")
    x["rows"][10]["stage_bs_base_m"]="379.07"
    with pytest.raises(ValueError,match="STAGE_ROW_GAP"):
        validate_volume_candidate(x,"kolyma")


def test_one_hidden_inner_coordinate_missing_is_detected():
    d=load_candidate("ust_srednekan")
    d["rows"][18]["volume_km3_by_0p1m_offset"].pop()
    with pytest.raises(ValueError,match="POINT_GAP_OR_SURPLUS"):
        validate_volume_candidate(d,"ust_srednekan")


def test_monotone_rounded_volume_can_be_nonstrict_but_never_decrease():
    d=load_candidate("ust_srednekan")
    d["rows"][20]["volume_km3_by_0p1m_offset"][0]="0.000"
    with pytest.raises(ValueError,match="VOLUME_DECREASE"):
        validate_volume_candidate(d,"ust_srednekan")


def test_six_source_candidates_keep_tailwater_and_zone_tables_quarantined():
    audit=review_quarantined_public_tables()
    assert set(audit)=={
        "kolyma_tailwater","ust_tailwater",
        "kolyma_dispatch","ust_dispatch"
    }
    assert audit["ust_tailwater"]["published_series_count"]==2
    assert audit["ust_tailwater"]["raw_readings"]==11
    assert audit["ust_tailwater"]["nonmonotonic_series_2_drop_m"]==2.45
    assert audit["ust_tailwater"]["active_tailwater_function"] is False
    for x in audit.values():
        assert x["active_tailwater_function"] is False


def test_bad_second_tailwater_series_cannot_be_auto_smoothed_in_qa():
    p=DIR/"order174_v913_ust_tailwater_candidate.json"
    d=json.loads(p.read_text(encoding="utf-8"))
    a={row["discharge_m3_s"]:row for row in d["readings"]}
    assert a[6000]["stage_series_2_m_bs"]==231.78
    assert a[8000]["stage_series_2_m_bs"]==229.33
    assert a[10000]["stage_series_2_m_bs"]==231.78
    assert d["numeric_geometry_ready"] is False
    assert d["operator_admitted"] is False
    assert "NONMONOTONIC" in d["flags"][0]


@pytest.mark.parametrize("name,count",[
    ("kolyma_tailwater",3),("ust_tailwater",13),
    ("kolyma_dispatch",50),("ust_dispatch",25)
])
def test_secondary_supplementary_publication_grain_is_preserved(name,count):
    a=json.loads((DIR/f"order174_v913_{name}_candidate.json").read_text(encoding="utf-8"))
    assert len(a["raw_table_lines"])==count
    assert a["numeric_geometry_ready"] is False
    assert a["operator_admitted"] is False
    assert a["source"]["primary_original_bytes_verified"] is False


def test_real_physics_engine_is_not_modified_to_use_public_candidates():
    # Inspection boundary: V9.12 synthetic engine is still synthetic-only.
    script=(ROOT/"server/hydro_api/causal_cascade_v912.py").read_text(encoding="utf-8")
    assert "SYNTHETIC_UPPER" in script
    assert "SYNTHETIC_LOWER" in script
    assert "V912_REAL_CURVES_ZONES_WEATHER_RIGHTS_NOT_AUTHENTICATED" in script
    assert "public_curves_quality_v913" not in script


def test_committed_v913_data_quality_receipt_matches_input_bytes():
    p=ROOT/"artifacts_v9/magadan_public_curves_quality_v913.json"
    assert p.is_file(),"V913_INSPECTABLE_REPORT_MISSING"
    a=json.loads(p.read_text(encoding="utf-8"))
    data={k:v for k,v in a.items() if k!="payload_sha256"}
    payload=json.dumps(data,sort_keys=True,indent=2,ensure_ascii=False).encode()
    assert hashlib.sha256(payload).hexdigest()==a["payload_sha256"]
    assert len(a["source_sha256"])==9
    for filename,expected in a["source_sha256"].items():
        path=ROOT/filename
        assert path.is_file(),filename
        assert hashlib.sha256(path.read_bytes()).hexdigest()==expected,filename
    assert a["summary"]["total_volume_coordinates"]==1802
    assert a["summary"]["quarantined_secondary_tables"]==4
    assert a["summary"]["registered_tailwater_declines"]==1
    assert a["summary"]["second_publisher_matching_coordinates"]==1521
    assert a["summary"]["second_publisher_unchecked_coordinates"]==281
    assert a["source_primary_authenticity_verified"] is False
    assert a["operator_hydraulic_admissibility_signed"] is False
    assert a["production_ready"] is False
    assert a["firm_available_capacity_mw"] is None


def test_second_public_publisher_matches_1521_cells_with_explicit_281_gap():
    r=validate_second_publisher_partial_crosscheck()
    assert r["independent_secondary_publisher_cells_compared"]==1521
    assert r["matching_secondary_publisher_cells"]==1521
    assert r["uncompared_kolyma_tail_cells"]==281
    assert r["lower_curve_complete_second_publisher_match"] is True
    assert r["upper_curve_complete_second_publisher_match"] is False
    assert r["original_official_document_authenticated"] is False
    assert r["full_geometry_operator_admitted"] is False


def test_publication_cannot_launder_partial_review_into_complete_validation():
    p=DIR/"order174_v913_two_publisher_partial_crosscheck.json"
    d=json.loads(p.read_text(encoding="utf-8"))
    assert d["summary"]["complete_independent_second_publisher_cell_comparison"] is False
    assert d["summary"]["remaining_uncompared_coordinates"]==281
    assert d["primary_official_original_verified"] is False
    assert d["permitted_for_real_hydraulic_engine"] is False


def test_cross_publisher_row_gaps_are_explicit_and_not_silently_filled():
    p=DIR/"order174_v913_two_publisher_partial_crosscheck.json"
    d=json.loads(p.read_text(encoding="utf-8"))
    assert len(d["consultant_accessible_rows"]["kolyma"])==82
    assert len(d["consultant_accessible_rows"]["ust_srednekan"])==71
    assert d["per_reservoir"]["kolyma"]["table_truncated_in_free_consultant_version"] is True
    assert d["per_reservoir"]["ust_srednekan"]["table_truncated_in_free_consultant_version"] is False
    assert d["per_reservoir"]["kolyma"]["unavailable_sudact_coordinates"]==281
