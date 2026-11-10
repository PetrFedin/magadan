"""V8.9 data-intake preflight: provenance, hourly grain and demand deduplication.

NO field-data ingestion, no owner-permission verification, no SCADA/network IO,
no capacity certification, no investment approval and no database writes.
The only numerical input accepted is explicit synthetic QA data. Real-source
metadata may be screened but never accompanied by operational measurements.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VERSION = "V89-SYNTHETIC-SOURCE-CONTRACT-2026-11"
DATASET_PATTERN = r"^(SYNTHETIC|PUBLIC)-[A-Za-z0-9_.-]{3,70}$"
IDENTIFIER_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{2,79}$"
DIGEST_PATTERN = r"^[a-f0-9]{64}$"
class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class SourceDeclaration(Contract):
    source_id: str = Field(pattern=DATASET_PATTERN)
    source_type: Literal["HOURLY_ENERGY", "NODE_CONSTRAINT", "BASELINE_INCLUSION", "NEW_CONNECTIONS", "PUBLIC_FORECAST"]
    owner_name: str = Field(min_length=4, max_length=150)
    permission_basis: Literal["SYNTHETIC_TEST", "PUBLIC_METADATA", "PENDING_OWNER_PERMISSION"]
    owner_document_ref: str = Field(min_length=6, max_length=260)
    digest_sha256_declared: str = Field(pattern=DIGEST_PATTERN)
    independently_verified: Literal[False] = False


class NodeConstraint(Contract):
    node_id: str = Field(pattern=IDENTIFIER_PATTERN)
    constraint_source_id: str = Field(pattern=DATASET_PATTERN)
    firm_n1_limit_mw: Decimal = Field(ge=0, le=100000)
    baseline_coincident_peak_mw: Decimal = Field(ge=0, le=100000)
    operating_reserve_mw: Decimal = Field(ge=0, le=100000)

    @field_validator("firm_n1_limit_mw", "baseline_coincident_peak_mw", "operating_reserve_mw", mode="before")
    @classmethod
    def check_non_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError("BOOLEAN_NOT_A_QUANTITY")
        return value


class ConnectionDemand(Contract):
    project_id: str = Field(pattern=IDENTIFIER_PATTERN)
    connection_contract_id: str = Field(pattern=IDENTIFIER_PATTERN)
    canonical_consumer_id: str = Field(pattern=IDENTIFIER_PATTERN)
    node_id: str = Field(pattern=IDENTIFIER_PATTERN)
    source_id: str = Field(pattern=DATASET_PATTERN)
    baseline_inclusion: Literal["IN_BASELINE", "ADDITIONAL", "UNKNOWN"]
    baseline_reconciliation_ref: str | None = Field(default=None, max_length=260)
    rated_mw: Decimal = Field(gt=0, le=100000)
    utilization_fraction: Decimal = Field(ge=0, le=1)

    @field_validator("rated_mw", "utilization_fraction", mode="before")
    @classmethod
    def check_non_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError("BOOLEAN_NOT_A_QUANTITY")
        return value


class HourlyNodeRecord(Contract):
    node_id: str = Field(pattern=IDENTIFIER_PATTERN)
    source_id: str = Field(pattern=DATASET_PATTERN)
    timestamp_utc: str = Field(min_length=20, max_length=20)
    supply_mwh: Decimal = Field(ge=0, le=100000)
    baseline_load_mwh: Decimal = Field(ge=0, le=100000)

    @field_validator("timestamp_utc")
    @classmethod
    def require_exact_utc_hour(cls, value: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:00:00Z", value):
            raise ValueError("UTC_FULL_HOUR_REQUIRED")
        try:
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            raise ValueError("INVALID_UTC_TIMESTAMP") from exc
        return value

    @field_validator("supply_mwh", "baseline_load_mwh", mode="before")
    @classmethod
    def check_non_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError("BOOLEAN_NOT_A_QUANTITY")
        return value


class MonthlyIntake(Contract):
    mode: Literal["SYNTHETIC_ONLY", "PROPOSED_METADATA_ONLY"]
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    region: Literal["MAGADAN"]
    sources: list[SourceDeclaration] = Field(min_length=1, max_length=50)
    nodes: list[NodeConstraint] = Field(default_factory=list, max_length=20)
    connections: list[ConnectionDemand] = Field(default_factory=list, max_length=500)
    hourly: list[HourlyNodeRecord] = Field(default_factory=list, max_length=18000)

    @field_validator("year", "month", mode="before")
    @classmethod
    def reject_bool_calendar(cls, value):
        if isinstance(value, bool):
            raise ValueError("BOOLEAN_NOT_A_CALENDAR_FIELD")
        return value

    @model_validator(mode="after")
    def metadata_does_not_admit_operational_values(self):
        if self.mode == "PROPOSED_METADATA_ONLY" and (self.nodes or self.connections or self.hourly):
            raise ValueError("FIELD_METADATA_MODE_MUST_NOT_CONTAIN_OPERATIONAL_MEASUREMENTS")
        if self.mode == "SYNTHETIC_ONLY" and (not self.nodes or not self.hourly):
            raise ValueError("SYNTHETIC_SCENARIO_REQUIRES_NODE_AND_HOURLY_RECORDS")
        return self


def _issue(code: str, severity: str, count: int = 1) -> dict:
    return {"code": code, "severity": severity, "count": count}


def _snapshot_sha(data: MonthlyIntake) -> str:
    canonical = json.dumps(data.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assess_v89(data: MonthlyIntake) -> dict:
    """Fail-closed synthetic intake profile; no field permission can be self-granted.

    When quality blockers exist, calculated nodal surplus is null: never 0 or
    an implied deliverable MW. The source digest is DECLARED, not verified
    without the actual rights-cleared underlying document.
    """
    issues: list[dict] = []
    source_ids = [row.source_id for row in data.sources]
    known_sources = {row.source_id: row for row in data.sources}
    if len(source_ids) != len(set(source_ids)):
        issues.append(_issue("DUPLICATE_SOURCE_ID", "CRITICAL"))
    expected_hours = calendar.monthrange(data.year, data.month)[1] * 24
    common = {
        "engine": VERSION,
        "mode": data.mode,
        "region": data.region,
        "year": data.year,
        "month": data.month,
        "input_sha256": _snapshot_sha(data),
        "source_count": len(data.sources),
        "declared_digests_independently_matched": False,
        "owner_rights_independently_verified": False,
        "n1_engineering_model_independently_verified": False,
        "external_grid_operator_approval": False,
        "investment_decision": "HOLD",
        "real_available_capacity_mw": None,
        "financial_ledger_eligible": False,
        "industrial_dispatch_eligible": False,
        "production_ready": False,
    }
    if data.mode == "PROPOSED_METADATA_ONLY":
        issues.append(_issue("OWNER_PERMISSION_AND_DATASETS_NOT_INDEPENDENTLY_VERIFIED", "CRITICAL"))
        if any(src.permission_basis == "SYNTHETIC_TEST" for src in data.sources):
            issues.append(_issue("SYNTHETIC_PERMISSION_IN_REAL_METADATA_CANDIDATE", "HIGH"))
        return {**common, "status": "QUARANTINED_METADATA_ONLY", "quality_pass": False,
                "monthly_hours_expected_per_node": expected_hours,
                "quality_issues": issues, "nodal_synthetic_results": [],
                "new_project_mw_synthetic_total": None, "unknown_baseline_projects": []}

    if any(source.permission_basis != "SYNTHETIC_TEST" for source in data.sources):
        issues.append(_issue("NON_SYNTHETIC_PERMISSION_IN_SYNTHETIC_LAB", "CRITICAL"))
    node_ids = [row.node_id for row in data.nodes]
    if len(node_ids) != len(set(node_ids)):
        issues.append(_issue("DUPLICATE_NODE_ID", "CRITICAL"))
    nodes = {row.node_id: row for row in data.nodes}

    for node in data.nodes:
        src = known_sources.get(node.constraint_source_id)
        if not src or src.source_type != "NODE_CONSTRAINT":
            issues.append(_issue("NODE_CONSTRAINT_SOURCE_MISSING_OR_WRONG_TYPE", "CRITICAL"))
        if node.baseline_coincident_peak_mw + node.operating_reserve_mw > node.firm_n1_limit_mw:
            issues.append(_issue("BASELINE_PEAK_AND_RESERVE_EXCEED_N1_LIMIT", "HIGH"))

    project_ids = [c.project_id.casefold() for c in data.connections]
    contract_ids = [c.connection_contract_id.casefold() for c in data.connections]
    consumer_ids = [c.canonical_consumer_id.casefold() for c in data.connections]
    if len(project_ids) != len(set(project_ids)):
        issues.append(_issue("DUPLICATE_PROJECT_ID", "CRITICAL"))
    if len(contract_ids) != len(set(contract_ids)):
        issues.append(_issue("DUPLICATE_CONNECTION_CONTRACT", "CRITICAL"))
    if len(consumer_ids) != len(set(consumer_ids)):
        issues.append(_issue("CANONICAL_CONSUMER_MULTIPLE_ROWS_NEEDS_ALLOCATION_PROOF", "CRITICAL"))

    unknown = []
    incremental: dict[str, Decimal] = defaultdict(Decimal)
    for project in data.connections:
        src = known_sources.get(project.source_id)
        if not src or src.source_type != "NEW_CONNECTIONS":
            issues.append(_issue("PROJECT_SOURCE_MISSING_OR_WRONG_TYPE", "CRITICAL"))
        if project.node_id not in nodes:
            issues.append(_issue("PROJECT_UNKNOWN_GRID_NODE", "CRITICAL"))
        if project.baseline_inclusion == "UNKNOWN":
            unknown.append(project.project_id)
        elif project.baseline_inclusion == "ADDITIONAL":
            if not project.baseline_reconciliation_ref or not project.baseline_reconciliation_ref.startswith("SYNTHETIC-"):
                issues.append(_issue("ADDITIONAL_PROJECT_MISSING_BASELINE_RECONCILIATION", "CRITICAL"))
            incremental[project.node_id] += project.rated_mw
        elif project.baseline_inclusion == "IN_BASELINE":
            # Never silently trust an assertion that the load was already counted.
            if not project.baseline_reconciliation_ref or not project.baseline_reconciliation_ref.startswith("SYNTHETIC-"):
                issues.append(_issue("IN_BASELINE_PROJECT_MISSING_RECONCILIATION", "CRITICAL"))
        # IN_BASELINE contributes ZERO incremental new load *only with evidence*.
    if unknown:
        issues.append(_issue("UNKNOWN_BASELINE_INCLUSION_REQUIRES_OWNER_RECONCILIATION", "CRITICAL", len(unknown)))

    series_keys: Counter[tuple[str, str]] = Counter()
    per_node: dict[str, dict[str, HourlyNodeRecord]] = defaultdict(dict)
    start = datetime(data.year, data.month, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=expected_hours)
    invalid_hours = 0
    unknown_nodes = 0
    bad_sources = 0
    over_baseline_peak = 0
    for record in data.hourly:
        key = (record.node_id, record.timestamp_utc)
        series_keys[key] += 1
        timestamp = datetime.strptime(record.timestamp_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if not start <= timestamp < end:
            invalid_hours += 1
        if record.node_id not in nodes:
            unknown_nodes += 1
        src = known_sources.get(record.source_id)
        if not src or src.source_type != "HOURLY_ENERGY":
            bad_sources += 1
        node = nodes.get(record.node_id)
        if node and record.baseline_load_mwh > node.baseline_coincident_peak_mw:
            over_baseline_peak += 1
        per_node[record.node_id][record.timestamp_utc] = record

    duplicates = sum(n - 1 for n in series_keys.values() if n > 1)
    if duplicates:
        issues.append(_issue("DUPLICATE_NODE_UTC_HOUR", "CRITICAL", duplicates))
    if invalid_hours:
        issues.append(_issue("HOUR_OUTSIDE_DECLARED_MONTH", "CRITICAL", invalid_hours))
    if unknown_nodes:
        issues.append(_issue("HOURLY_UNKNOWN_NODE", "CRITICAL", unknown_nodes))
    if bad_sources:
        issues.append(_issue("HOURLY_SOURCE_MISSING_OR_WRONG_TYPE", "CRITICAL", bad_sources))
    if over_baseline_peak:
        issues.append(_issue("HOURLY_BASELINE_EXCEEDS_DECLARED_PEAK", "CRITICAL", over_baseline_peak))
    expected_keys = {(node_id, (start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ"))
                     for node_id in nodes for i in range(expected_hours)}
    missing = len(expected_keys - set(series_keys))
    if missing:
        issues.append(_issue("MISSING_NODE_UTC_HOURS", "CRITICAL", missing))

    quality_pass = not issues
    details: list[dict] = []
    if quality_pass:
        for node_id in sorted(nodes):
            node = nodes[node_id]
            rows = per_node[node_id]
            project_mw = incremental.get(node_id, Decimal("0"))
            load_average_mwh = sum(
                p.rated_mw * p.utilization_fraction
                for p in data.connections if p.node_id == node_id and p.baseline_inclusion == "ADDITIONAL"
            )
            original_deficit = Decimal("0")
            additional_deficit = Decimal("0")
            for row in rows.values():
                before = max(Decimal("0"), row.baseline_load_mwh - row.supply_mwh)
                after = max(Decimal("0"), row.baseline_load_mwh + load_average_mwh - row.supply_mwh)
                original_deficit += before
                additional_deficit += after - before
            remaining_peak = node.firm_n1_limit_mw - node.baseline_coincident_peak_mw - node.operating_reserve_mw
            details.append({
                "node_id": node_id,
                "complete_utc_hours": len(rows),
                "new_additional_mw_synthetic": str(project_mw),
                "illustrative_peak_headroom_mw": str(max(Decimal("0"), remaining_peak)),
                "illustrative_peak_deficit_after_new_mw": str(max(Decimal("0"), project_mw - remaining_peak)),
                "baseline_energy_shortfall_mwh_synthetic": str(original_deficit),
                "incremental_energy_shortfall_mwh_synthetic": str(additional_deficit),
            })
    return {
        **common,
        "status": "SYNTHETIC_QUALITY_PASS_ONLY" if quality_pass else "SYNTHETIC_QUALITY_BLOCKED",
        "quality_pass": quality_pass,
        "monthly_hours_expected_per_node": expected_hours,
        "hourly_rows_received": len(data.hourly),
        "hourly_rows_expected": len(nodes) * expected_hours,
        "missing_hour_count": missing,
        "duplicate_hour_count": duplicates,
        "unknown_baseline_projects": unknown,
        "new_project_mw_synthetic_total": str(sum(incremental.values())) if quality_pass else None,
        "nodal_synthetic_results": details,
        "quality_issues": issues,
    }
