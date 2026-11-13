"""Synthetic-only V8.9 cross-record baseline inclusion reconciliation.

A consistent synthetic register is NOT proof of an actual SIPR forecast,
network transfer right, data-use license, N-1 capacity or investment approval.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

VERSION = "V89-BASELINE-CROSSRECONCILIATION-SYNTHETIC-1"
ID = r"^[A-Za-z][A-Za-z0-9_.-]{2,79}$"
SYNTH = r"^SYNTHETIC-[A-Za-z0-9_.-]{6,100}$"
SHA = r"^[a-f0-9]{64}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class ForecastMatch(Strict):
    record_id: str = Field(pattern=ID)
    forecast_revision: str = Field(pattern=SYNTH)
    canonical_consumer_id: str = Field(pattern=ID)
    connection_contract_id: str = Field(pattern=ID)
    supply_point_id: str = Field(pattern=ID)
    node_id: str = Field(pattern=ID)
    already_counted_mw: Decimal = Field(ge=0, le=100000)
    evidence_ref: str = Field(pattern=SYNTH)

    @field_validator("already_counted_mw", mode="before")
    @classmethod
    def forbid_bool(cls, v):
        if isinstance(v, bool):
            raise ValueError("BOOLEAN_NOT_MW")
        return v


class ProjectConnection(Strict):
    project_id: str = Field(pattern=ID)
    canonical_consumer_id: str = Field(pattern=ID)
    connection_contract_id: str = Field(pattern=ID)
    supply_point_id: str = Field(pattern=ID)
    node_id: str = Field(pattern=ID)
    requested_mw: Decimal = Field(gt=0, le=100000)
    declared_baseline_status: Literal["IN_BASELINE", "ADDITIONAL", "PARTIAL", "UNKNOWN"]
    split_allocation_ref: str | None = Field(default=None, pattern=SYNTH)

    @field_validator("requested_mw", mode="before")
    @classmethod
    def forbid_bool(cls, v):
        if isinstance(v, bool):
            raise ValueError("BOOLEAN_NOT_MW")
        return v


class BaselineReconcileCase(Strict):
    mode: Literal["SYNTHETIC_ONLY"]
    region: Literal["MAGADAN"]
    forecast_revision: str = Field(pattern=SYNTH)
    forecast_year: int = Field(ge=2020, le=2100)
    source_snapshot_digest_declared: str = Field(pattern=SHA)
    source_owner_permission_independently_verified: Literal[False]
    independent_engineer_approved: Literal[False]
    forecast_rows: list[ForecastMatch] = Field(min_length=1, max_length=1500)
    projects: list[ProjectConnection] = Field(min_length=1, max_length=500)

    @field_validator("forecast_year", mode="before")
    @classmethod
    def forbid_bool_year(cls, v):
        if isinstance(v, bool):
            raise ValueError("BOOLEAN_NOT_YEAR")
        return v


def _norm(v: str) -> str:
    return v.casefold()


def assess_baseline_reconciliation(case: BaselineReconcileCase) -> dict:
    issues: list[dict] = []

    def issue(code, number=1):
        issues.append({"code": code, "severity": "CRITICAL", "count": number})

    records_by_contract: dict[str, list[ForecastMatch]] = defaultdict(list)
    forecast_ids = Counter(_norm(r.record_id) for r in case.forecast_rows)
    for row in case.forecast_rows:
        records_by_contract[_norm(row.connection_contract_id)].append(row)
        if row.forecast_revision != case.forecast_revision:
            issue("FORECAST_REVISION_MISMATCH")
    if (dupes := sum(v - 1 for v in forecast_ids.values() if v > 1)):
        issue("DUPLICATE_BASELINE_RECORD_ID", dupes)
    if (dupes := sum(len(v) - 1 for v in records_by_contract.values() if len(v) > 1)):
        issue("DUPLICATE_BASELINE_CONTRACT", dupes)

    project_ids = Counter(_norm(p.project_id) for p in case.projects)
    contract_ids = Counter(_norm(p.connection_contract_id) for p in case.projects)
    point_ids = Counter(_norm(p.supply_point_id) for p in case.projects)
    for label, counter in (("DUPLICATE_PROJECT_ID", project_ids),
                           ("DUPLICATE_PROJECT_CONTRACT", contract_ids),
                           ("DUPLICATE_SUPPLY_POINT", point_ids)):
        if (duplicates := sum(n - 1 for n in counter.values() if n > 1)):
            issue(label, duplicates)

    same_consumer: dict[str, list[ProjectConnection]] = defaultdict(list)
    for project in case.projects:
        same_consumer[_norm(project.canonical_consumer_id)].append(project)
    for group in same_consumer.values():
        if len(group) <= 1:
            continue
        groups = {p.split_allocation_ref for p in group}
        if None in groups or len(groups) != 1:
            issue("MULTI_POINT_CONSUMER_MISSING_COMMON_ALLOCATION_PROOF")
        # Multiple contracts to the same physical point are not automatically additive.
        if len({_norm(p.supply_point_id) for p in group}) != len(group):
            issue("MULTI_POINT_CONSUMER_DUPLICATE_SUPPLY_POINT")

    decisions = []
    for p in case.projects:
        matches = records_by_contract.get(_norm(p.connection_contract_id), [])
        if len(matches) != 1:
            issue("MISSING_OR_AMBIGUOUS_FORECAST_MATCH")
            continue
        row = matches[0]
        if (_norm(row.canonical_consumer_id) != _norm(p.canonical_consumer_id)
                or _norm(row.supply_point_id) != _norm(p.supply_point_id)
                or _norm(row.node_id) != _norm(p.node_id)):
            issue("FORECAST_JOIN_IDENTITY_OR_NODE_MISMATCH")
            continue
        if row.already_counted_mw > p.requested_mw:
            issue("BASELINE_EXCEEDS_REQUESTED_CAPACITY")
            continue
        if p.declared_baseline_status == "UNKNOWN":
            issue("DECLARED_BASELINE_STATUS_UNKNOWN")
            continue
        counted = row.already_counted_mw
        if p.declared_baseline_status == "IN_BASELINE" and counted != p.requested_mw:
            issue("IN_BASELINE_NOT_FULLY_COUNTED")
            continue
        if p.declared_baseline_status == "ADDITIONAL" and counted != Decimal("0"):
            issue("ADDITIONAL_ALREADY_PARTLY_IN_FORECAST")
            continue
        if p.declared_baseline_status == "PARTIAL" and not Decimal("0") < counted < p.requested_mw:
            issue("PARTIAL_INCLUSION_NOT_BETWEEN_ZERO_AND_REQUESTED")
            continue
        decisions.append({
            "project_id": p.project_id,
            "canonical_consumer_id": p.canonical_consumer_id,
            "connection_contract_id": p.connection_contract_id,
            "supply_point_id": p.supply_point_id,
            "node_id": p.node_id,
            "declared_status": p.declared_baseline_status,
            "requested_mw": str(p.requested_mw),
            "already_counted_mw_synthetic": str(counted),
            "additional_mw_synthetic": str(p.requested_mw - counted),
            "baseline_record_id": row.record_id,
        })
    quality_pass = not issues and len(decisions) == len(case.projects)
    digest = hashlib.sha256(json.dumps(case.model_dump(mode="json"), sort_keys=True,
            separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    return {
        "engine": VERSION,
        "input_sha256": digest,
        "status": "SYNTHETIC_JOIN_CONSISTENT_ONLY" if quality_pass else "BASELINE_RECONCILIATION_HOLD",
        "synthetic_join_consistent": quality_pass,
        "issue_count": len(issues),
        "quality_issues": issues,
        "matched_project_count": len(decisions) if quality_pass else 0,
        "synthetic_additional_mw_total": (str(sum((Decimal(x["additional_mw_synthetic"]) for x in decisions), Decimal("0")))
                                          if quality_pass else None),
        "synthetic_matched_decisions": decisions if quality_pass else [],
        "declared_source_digest_independently_verified": False,
        "actual_sipr_inclusion_independently_verified": False,
        "owner_rights_independently_verified": False,
        "actual_available_capacity_mw": None,
        "approved_investment_decision": "HOLD",
        "industrial_dispatch_eligible": False,
        "production_ready": False,
    }
