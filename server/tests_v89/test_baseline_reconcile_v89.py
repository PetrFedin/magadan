"""Synthetic V8.9 cross-record reconciliation: negative and multi-point tests."""
from copy import deepcopy
import pytest
from pydantic import ValidationError

from hydro_api.baseline_reconcile_v89 import BaselineReconcileCase, assess_baseline_reconciliation


def sample():
    return {
        "mode": "SYNTHETIC_ONLY", "region": "MAGADAN",
        "forecast_revision": "SYNTHETIC-SIPR2031-REV1", "forecast_year": 2031,
        "source_snapshot_digest_declared": "a" * 64,
        "source_owner_permission_independently_verified": False,
        "independent_engineer_approved": False,
        "forecast_rows": [{
            "record_id": "row_001", "forecast_revision": "SYNTHETIC-SIPR2031-REV1",
            "canonical_consumer_id": "consumer_A", "connection_contract_id": "contract_A",
            "supply_point_id": "point_A", "node_id": "node_A",
            "already_counted_mw": "30", "evidence_ref": "SYNTHETIC-BASELINE-EVIDENCE-A",
        }],
        "projects": [{
            "project_id": "project_A", "canonical_consumer_id": "consumer_A",
            "connection_contract_id": "contract_A", "supply_point_id": "point_A",
            "node_id": "node_A", "requested_mw": "50",
            "declared_baseline_status": "PARTIAL", "split_allocation_ref": None,
        }],
    }


def out(data):
    return assess_baseline_reconciliation(BaselineReconcileCase.model_validate(data))


def issues(data):
    return {entry["code"] for entry in out(data)["quality_issues"]}


def test_valid_partial_counts_only_the_20_synthetic_mw_not_the_50():
    result = out(sample())
    assert result["synthetic_join_consistent"]
    assert result["synthetic_additional_mw_total"] == "20"
    assert result["synthetic_matched_decisions"][0]["already_counted_mw_synthetic"] == "30"
    assert result["actual_available_capacity_mw"] is None
    assert result["approved_investment_decision"] == "HOLD"
    assert not result["declared_source_digest_independently_verified"]
    assert result == out(sample())


@pytest.mark.parametrize("counted,status,expected", [
    ("50", "IN_BASELINE", "0"), ("0", "ADDITIONAL", "50"), ("30", "PARTIAL", "20"),
])
def test_supported_inclusion_status(counted, status, expected):
    data = sample()
    data["forecast_rows"][0]["already_counted_mw"] = counted
    data["projects"][0]["declared_baseline_status"] = status
    assert out(data)["synthetic_additional_mw_total"] == expected


@pytest.mark.parametrize("counted,status,code", [
    ("20", "IN_BASELINE", "IN_BASELINE_NOT_FULLY_COUNTED"),
    ("20", "ADDITIONAL", "ADDITIONAL_ALREADY_PARTLY_IN_FORECAST"),
    ("0", "PARTIAL", "PARTIAL_INCLUSION_NOT_BETWEEN_ZERO_AND_REQUESTED"),
    ("50", "PARTIAL", "PARTIAL_INCLUSION_NOT_BETWEEN_ZERO_AND_REQUESTED"),
    ("60", "PARTIAL", "BASELINE_EXCEEDS_REQUESTED_CAPACITY"),
])
def test_mismatch_is_fail_closed(counted, status, code):
    data = sample()
    data["forecast_rows"][0]["already_counted_mw"] = counted
    data["projects"][0]["declared_baseline_status"] = status
    result = out(data)
    assert code in {x["code"] for x in result["quality_issues"]}
    assert result["synthetic_additional_mw_total"] is None
    assert result["synthetic_matched_decisions"] == []


@pytest.mark.parametrize("field,value", [
    ("connection_contract_id", "different_contract"),
    ("canonical_consumer_id", "different_consumer"),
    ("supply_point_id", "different_point"), ("node_id", "different_node"),
])
def test_identity_join_cannot_be_assumed(field, value):
    data = sample()
    data["projects"][0][field] = value
    assert not out(data)["synthetic_join_consistent"]


def test_duplicate_baseline_contract_and_record_fail():
    data = sample()
    data["forecast_rows"].append(deepcopy(data["forecast_rows"][0]))
    assert {"DUPLICATE_BASELINE_CONTRACT", "DUPLICATE_BASELINE_RECORD_ID"} <= issues(data)


def test_duplicate_project_contract_case_insensitive_fails():
    data = sample()
    p = deepcopy(data["projects"][0])
    p.update(project_id="project_B", connection_contract_id="CONTRACT_A")
    data["projects"].append(p)
    assert "DUPLICATE_PROJECT_CONTRACT" in issues(data)


def test_revision_drift_cannot_pass():
    data = sample()
    data["forecast_rows"][0]["forecast_revision"] = "SYNTHETIC-SIPR2031-REV2"
    assert "FORECAST_REVISION_MISMATCH" in issues(data)


def test_unknown_baseline_never_implies_zero():
    data = sample()
    data["projects"][0]["declared_baseline_status"] = "UNKNOWN"
    assert "DECLARED_BASELINE_STATUS_UNKNOWN" in issues(data)
    assert out(data)["synthetic_additional_mw_total"] is None


def test_two_real_separate_supply_points_require_shared_allocation_reference():
    data = sample()
    p = deepcopy(data["projects"][0])
    p.update(project_id="project_B", connection_contract_id="contract_B",
             supply_point_id="point_B", node_id="node_B")
    row = deepcopy(data["forecast_rows"][0])
    row.update(record_id="row_002", connection_contract_id="contract_B",
               supply_point_id="point_B", node_id="node_B")
    data["projects"].append(p)
    data["forecast_rows"].append(row)
    assert "MULTI_POINT_CONSUMER_MISSING_COMMON_ALLOCATION_PROOF" in issues(data)
    for project in data["projects"]:
        project["split_allocation_ref"] = "SYNTHETIC-MULTI-SUPPLY-ALLOCATION"
    result = out(data)
    assert result["synthetic_join_consistent"]
    assert result["synthetic_additional_mw_total"] == "40"
    assert result["actual_available_capacity_mw"] is None


def test_duplicate_supply_point_fails_even_with_allocation_ref():
    data = sample()
    p = deepcopy(data["projects"][0])
    p.update(project_id="project_B", connection_contract_id="contract_B",
             split_allocation_ref="SYNTHETIC-MULTI-SUPPLY-ALLOCATION")
    data["projects"][0]["split_allocation_ref"] = "SYNTHETIC-MULTI-SUPPLY-ALLOCATION"
    row = deepcopy(data["forecast_rows"][0])
    row.update(record_id="row_002", connection_contract_id="contract_B")
    data["projects"].append(p)
    data["forecast_rows"].append(row)
    assert "DUPLICATE_SUPPLY_POINT" in issues(data)


def test_owner_permission_claim_cannot_be_supplied_by_caller():
    data = sample()
    data["source_owner_permission_independently_verified"] = True
    with pytest.raises(ValidationError):
        BaselineReconcileCase.model_validate(data)


def test_independent_engineer_approval_cannot_be_supplied_by_caller():
    data = sample()
    data["independent_engineer_approved"] = True
    with pytest.raises(ValidationError):
        BaselineReconcileCase.model_validate(data)


def test_boolean_mw_and_year_rejected():
    data = sample()
    data["forecast_rows"][0]["already_counted_mw"] = True
    with pytest.raises(ValidationError):
        BaselineReconcileCase.model_validate(data)
    data = sample()
    data["forecast_year"] = True
    with pytest.raises(ValidationError):
        BaselineReconcileCase.model_validate(data)


def test_declared_source_hash_is_not_independently_verified():
    data = sample()
    data["source_snapshot_digest_declared"] = "0" * 64
    result = out(data)
    assert result["synthetic_join_consistent"]
    assert not result["declared_source_digest_independently_verified"]


def test_non_synthetic_forecast_revision_is_invalid():
    data = sample()
    data["forecast_revision"] = "actual-sipr"
    with pytest.raises(ValidationError):
        BaselineReconcileCase.model_validate(data)
