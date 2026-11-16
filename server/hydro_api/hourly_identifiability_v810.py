"""V8.10 synthetic full-calendar-month adequacy identifiability experiment.

Demonstrates that matching aggregate demand, available-capacity histograms,
and even optimistic aggregate/peak screens does not determine hourly shortage.
Never represents generation production, formal N-1, dispatch, LOLE, EENS, or
actual Magadan capacity. No network, database, file or financial writes.
"""
from __future__ import annotations

import calendar
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ENGINE = "V810-SYNTHETIC-HOURLY-IDENTIFIABILITY-1"
SYNTHETIC_ID = r"^SYNTHETIC-[A-Za-z0-9_.-]{6,100}$"
ONE_HOUR = timedelta(hours=1)
ZERO = Decimal("0")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class HourlyState(Strict):
    hour_utc: datetime
    existing_demand_mw: Decimal = Field(ge=0, le=20000)
    additional_demand_mw: Decimal = Field(ge=0, le=20000)
    usable_generation_mw: Decimal = Field(ge=0, le=20000)
    network_envelope_mw: Decimal = Field(ge=0, le=20000)
    held_operating_reserve_mw: Decimal = Field(ge=0, le=10000)

    @field_validator(
        "existing_demand_mw", "additional_demand_mw", "usable_generation_mw",
        "network_envelope_mw", "held_operating_reserve_mw", mode="before"
    )
    @classmethod
    def reject_bool_as_mw(cls, value):
        if isinstance(value, bool):
            raise ValueError("BOOLEAN_CANNOT_REPRESENT_MW")
        return value

    @field_validator("hour_utc")
    @classmethod
    def require_exact_utc_hour(cls, value: datetime):
        if (value.tzinfo is None or value.utcoffset() != timedelta(0)
                or value.minute or value.second or value.microsecond):
            raise ValueError("HOURLY_TIMESTAMP_MUST_BE_ON_UTC_HOUR")
        return value

    @model_validator(mode="after")
    def require_reserve_within_envelope(self):
        if self.held_operating_reserve_mw > min(
            self.usable_generation_mw, self.network_envelope_mw
        ):
            raise ValueError("RESERVE_EXCEEDS_INSTANTANEOUS_ENVELOPE")
        return self


class SyntheticMonth(Strict):
    mode: Literal["SYNTHETIC_RESEARCH_ONLY"]
    case_id: str = Field(pattern=SYNTHETIC_ID)
    source_ref: str = Field(pattern=SYNTHETIC_ID)
    real_source_rights_verified: Literal[False]
    real_operational_data_accepted: Literal[False]
    independent_n1_verified: Literal[False]
    hours: list[HourlyState] = Field(min_length=672, max_length=744)

    @model_validator(mode="after")
    def require_complete_contiguous_utc_calendar_month(self):
        first = self.hours[0].hour_utc
        if first.day != 1 or first.hour != 0:
            raise ValueError("UTC_MONTH_MUST_START_AT_FIRST_MIDNIGHT")
        expected = calendar.monthrange(first.year, first.month)[1] * 24
        if len(self.hours) != expected:
            raise ValueError("MISSING_OR_EXCESS_UTC_HOURLY_ROWS")
        for position, row in enumerate(self.hours):
            if row.hour_utc != first + position * ONE_HOUR:
                raise ValueError("OUT_OF_ORDER_DUPLICATE_OR_MISSING_UTC_HOUR")
        return self


def _hash_case(case: SyntheticMonth) -> str:
    raw = json.dumps(case.model_dump(mode="json"), sort_keys=True,
                     separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _str(value: Decimal) -> str:
    return format(value, "f")


def _cap(hour: HourlyState) -> Decimal:
    # A hypothetical per-hour serving envelope, not energy actually generated.
    return min(hour.usable_generation_mw, hour.network_envelope_mw) - hour.held_operating_reserve_mw


def evaluate_synthetic_month(case: SyntheticMonth) -> dict:
    """Deterministic hourly residuals; not a probabilistic reliability study."""
    # Snapshot and revalidate: callers may have mutated Pydantic objects.
    case = SyntheticMonth.model_validate(case.model_dump(mode="python"))
    envelope = existing = additional = baseline_ens = combined_ens = ZERO
    baseline_hours = loss_hours = additional_caused_hours = 0
    max_deficit = ZERO
    first_deficit_hour: str | None = None
    peak_requested = peak_envelope = ZERO
    for hour in case.hours:
        available = _cap(hour)
        demanded = hour.existing_demand_mw + hour.additional_demand_mw
        baseline_short = max(ZERO, hour.existing_demand_mw - available)
        combined_short = max(ZERO, demanded - available)
        incremental_short = combined_short - baseline_short
        assert incremental_short >= ZERO  # Addition cannot reduce deficit.
        envelope += available
        existing += hour.existing_demand_mw
        additional += hour.additional_demand_mw
        baseline_ens += baseline_short
        combined_ens += combined_short
        peak_requested = max(peak_requested, demanded)
        peak_envelope = max(peak_envelope, available)
        if baseline_short > ZERO:
            baseline_hours += 1
        if combined_short > ZERO:
            loss_hours += 1
            max_deficit = max(max_deficit, combined_short)
            if first_deficit_hour is None:
                first_deficit_hour = hour.hour_utc.isoformat()
        if incremental_short > ZERO:
            additional_caused_hours += 1
    total_demand = existing + additional
    return {
        "engine": ENGINE,
        "case_id": case.case_id,
        "input_sha256": _hash_case(case),
        "month_utc": case.hours[0].hour_utc.strftime("%Y-%m"),
        "complete_utc_hour_count": len(case.hours),
        "capacity_hour_envelope_mwh_not_actual_generation": _str(envelope),
        "existing_demand_mwh": _str(existing),
        "additional_demand_mwh": _str(additional),
        "combined_demand_mwh": _str(total_demand),
        "optimistic_aggregate_envelope_pass": envelope >= total_demand,
        "optimistic_maximum_peak_pass": peak_envelope >= peak_requested,
        "maximum_hourly_envelope_mw_not_firm": _str(peak_envelope),
        "maximum_hourly_demand_mw": _str(peak_requested),
        "baseline_deterministic_shortfall_mwh": _str(baseline_ens),
        "combined_deterministic_shortfall_mwh": _str(combined_ens),
        "incremental_deterministic_shortfall_mwh": _str(combined_ens - baseline_ens),
        "baseline_shortfall_hours": baseline_hours,
        "combined_shortfall_hours": loss_hours,
        "additional_caused_shortfall_hours": additional_caused_hours,
        "maximum_hourly_shortfall_mw": _str(max_deficit),
        "first_shortfall_hour_utc": first_deficit_hour,
        "synthetic_hourly_fully_served": combined_ens == ZERO,
        "probabilistic_lole_or_eens_calculated": False,
        "formal_n_minus_one_study_performed": False,
        "water_balance_and_thermal_constraints_modelled": False,
        "real_source_rights_verified": False,
        "real_available_capacity_mw": None,
        "investment_decision": "HOLD",
        "production_ready": False,
    }


def compare_permuted_synthetic_months(adequate: SyntheticMonth, stressed: SyntheticMonth) -> dict:
    """Compare identical hourly demand and supply marginals in a different order.

    A counterexample disproves a *universal inference* from optimistic
    aggregates, not the physically stronger premise of independently confirmed
    firm deliverability at every hour. Nothing is learned about real likelihoods.
    """
    # Revalidate both cases before comparing their UTC axes and marginals.
    adequate = SyntheticMonth.model_validate(adequate.model_dump(mode="python"))
    stressed = SyntheticMonth.model_validate(stressed.model_dump(mode="python"))
    if adequate.case_id == stressed.case_id:
        raise ValueError("DISTINCT_SYNTHETIC_CASE_IDS_REQUIRED")
    if len(adequate.hours) != len(stressed.hours):
        raise ValueError("DIFFERENT_UTC_CALENDAR_MONTH")
    for a, b in zip(adequate.hours, stressed.hours):
        if (a.hour_utc != b.hour_utc
                or a.existing_demand_mw != b.existing_demand_mw
                or a.additional_demand_mw != b.additional_demand_mw):
            raise ValueError("DEMAND_OR_UTC_AXIS_NOT_IDENTICAL")

    def capacity_histogram(case: SyntheticMonth) -> Counter:
        return Counter((r.usable_generation_mw, r.network_envelope_mw,
                        r.held_operating_reserve_mw) for r in case.hours)

    if capacity_histogram(adequate) != capacity_histogram(stressed):
        raise ValueError("HOURLY_RESOURCE_MULTISETS_NOT_IDENTICAL")
    a = evaluate_synthetic_month(adequate)
    b = evaluate_synthetic_month(stressed)
    same_screen = (
        a["capacity_hour_envelope_mwh_not_actual_generation"] ==
        b["capacity_hour_envelope_mwh_not_actual_generation"]
        and a["maximum_hourly_envelope_mw_not_firm"] ==
        b["maximum_hourly_envelope_mw_not_firm"]
        and a["combined_demand_mwh"] == b["combined_demand_mwh"]
        and a["maximum_hourly_demand_mw"] == b["maximum_hourly_demand_mw"]
    )
    assert same_screen  # Held by exact marginals, but retain explicit guard.
    has_proof = (
        a["optimistic_aggregate_envelope_pass"]
        and a["optimistic_maximum_peak_pass"]
        and a["synthetic_hourly_fully_served"]
        and not b["synthetic_hourly_fully_served"]
    )
    return {
        "engine": ENGINE,
        "status": "AGGREGATE_INFERENCE_COUNTEREXAMPLE_SYNTHETIC_ONLY" if has_proof else "NO_TARGETED_COUNTEREXAMPLE",
        "same_demand_and_resource_marginals": True,
        "same_optimistic_monthly_proxy_results": same_screen,
        "counterexample_proven_for_synthetic_inputs": has_proof,
        "adequate_case": a,
        "stressed_case": b,
        "probabilistic_lole_or_eens_calculated": False,
        "formal_n_minus_one_study_performed": False,
        "real_source_rights_verified": False,
        "real_available_capacity_mw": None,
        "investment_decision": "HOLD",
        "production_ready": False,
    }
