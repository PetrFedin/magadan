"""Strictly synthetic two-reservoir mass-conservation research (V8.11).

Hourly release plans are supplied by the test; this code NEVER optimizes or
issues real plant dispatch. Travel delay, water stocks and fixed MWh/1000m3
factors are fictional. The calculation cannot certify head, N-1 or capacity.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ENGINE = "V811-SYNTHETIC-INTERTEMPORAL-CASCADE-1"
SOURCE_PATTERN = r"^SYNTHETIC-[A-Za-z0-9_.-]{6,100}$"
HOUR = timedelta(hours=1)
ZERO = Decimal("0")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class Reservoir(Contract):
    initial_1000m3: Decimal = Field(ge=0, le=100000000)
    minimum_1000m3: Decimal = Field(ge=0, le=100000000)
    maximum_1000m3: Decimal = Field(gt=0, le=100000000)
    max_turbine_1000m3_per_hour: Decimal = Field(gt=0, le=100000000)
    max_total_release_1000m3_per_hour: Decimal = Field(gt=0, le=100000000)
    hypothetical_energy_mwh_per_1000m3: Decimal = Field(gt=0, le=100)

    @field_validator("*", mode="before")
    @classmethod
    def no_boolean_quantities(cls, value):
        if isinstance(value, bool):
            raise ValueError("BOOLEAN_NOT_A_WATER_OR_ENERGY_QUANTITY")
        return value

    @model_validator(mode="after")
    def feasible_bounds(self):
        if not self.minimum_1000m3 <= self.initial_1000m3 <= self.maximum_1000m3:
            raise ValueError("INVALID_INITIAL_RESERVOIR_BOUNDS")
        if self.max_turbine_1000m3_per_hour > self.max_total_release_1000m3_per_hour:
            raise ValueError("TURBINE_LIMIT_EXCEEDS_TOTAL_RELEASE_LIMIT")
        return self


class HourlyPlan(Contract):
    hour_utc: datetime
    upper_local_inflow_1000m3: Decimal = Field(ge=0, le=100000000)
    lower_lateral_inflow_1000m3: Decimal = Field(ge=0, le=100000000)
    upper_turbine_1000m3: Decimal = Field(ge=0, le=100000000)
    upper_spill_1000m3: Decimal = Field(ge=0, le=100000000)
    lower_turbine_1000m3: Decimal = Field(ge=0, le=100000000)
    lower_spill_1000m3: Decimal = Field(ge=0, le=100000000)
    hydro_only_demand_mwh: Decimal = Field(ge=0, le=100000000)

    @field_validator("hour_utc")
    @classmethod
    def require_exact_utc_hour(cls, v):
        if (v.tzinfo is None or v.utcoffset() != timedelta(0)
                or v.minute or v.second or v.microsecond):
            raise ValueError("REQUIRE_EXACT_UTC_HOUR")
        return v

    @field_validator("upper_local_inflow_1000m3", "lower_lateral_inflow_1000m3",
                     "upper_turbine_1000m3", "upper_spill_1000m3",
                     "lower_turbine_1000m3", "lower_spill_1000m3",
                     "hydro_only_demand_mwh", mode="before")
    @classmethod
    def no_boolean_magnitudes(cls, v):
        if isinstance(v, bool):
            raise ValueError("BOOLEAN_NOT_A_WATER_OR_ENERGY_QUANTITY")
        return v


class SyntheticCascade(Contract):
    mode: Literal["SYNTHETIC_RESEARCH_ONLY"]
    source_ref: str = Field(pattern=SOURCE_PATTERN)
    scenario_id: str = Field(pattern=SOURCE_PATTERN)
    actual_operational_data_accepted: Literal[False]
    real_source_rights_verified: Literal[False]
    independently_certified_n1: Literal[False]
    upper: Reservoir
    lower: Reservoir
    routing_delay_hours: int = Field(ge=0, le=12)
    # Oldest water reaches the lower reservoir first. This is a *measured*
    # state in real systems, but here only a fabricated initial condition.
    historical_in_transit_1000m3: list[Decimal] = Field(max_length=12)
    hours: list[HourlyPlan] = Field(min_length=2, max_length=168)

    @field_validator("routing_delay_hours", mode="before")
    @classmethod
    def no_boolean_delay(cls, v):
        if isinstance(v, bool):
            raise ValueError("BOOLEAN_NOT_A_TRAVEL_TIME")
        return v

    @field_validator("historical_in_transit_1000m3", mode="before")
    @classmethod
    def no_boolean_history(cls, v):
        if isinstance(v, list) and any(isinstance(x, bool) for x in v):
            raise ValueError("BOOLEAN_NOT_PRIOR_WATER_VOLUME")
        return v

    @model_validator(mode="after")
    def chronological_contract(self):
        if len(self.historical_in_transit_1000m3) != self.routing_delay_hours:
            raise ValueError("PRIOR_PIPELINE_STATE_LENGTH_MISMATCH")
        if any(not (ZERO <= x <= Decimal("100000000"))
               for x in self.historical_in_transit_1000m3):
            raise ValueError("INVALID_PRIOR_PIPELINE_STATE")
        start = self.hours[0].hour_utc
        if not 2020 <= start.year <= 2100:
            raise ValueError("OUT_OF_SYNTHETIC_TIME_RANGE")
        for i, hour in enumerate(self.hours):
            if hour.hour_utc != start + i * HOUR:
                raise ValueError("MISSING_DUPLICATE_OR_UNORDERED_UTC_HOUR")
        return self


def _str(number: Decimal) -> str:
    return format(number, "f")


def simulate_synthetic_cascade(plan: SyntheticCascade) -> dict:
    """Evaluate a fixed fictional release plan; never generate dispatch advice.

    On any infeasible mass/volume/release schedule, raise ValueError before
    returning any potentially misleading energy or capacity assessment.
    """
    # Validation can otherwise be bypassed by mutating a Pydantic nested list.
    plan = SyntheticCascade.model_validate(plan.model_dump(mode="python"))
    signature = sha256(json.dumps(plan.model_dump(mode="json"), sort_keys=True,
                                  separators=(",", ":")).encode("utf-8")).hexdigest()
    up, down = plan.upper.initial_1000m3, plan.lower.initial_1000m3
    pipe = deque(plan.historical_in_transit_1000m3)
    initial_total = up + down + sum(pipe, ZERO)
    external = down_exits = gen_total = demand_total = short_total = ZERO
    late_short_hours = 0
    rows = []
    for index, hour in enumerate(plan.hours):
        u_out = hour.upper_turbine_1000m3 + hour.upper_spill_1000m3
        d_out = hour.lower_turbine_1000m3 + hour.lower_spill_1000m3
        if (hour.upper_turbine_1000m3 > plan.upper.max_turbine_1000m3_per_hour
                or u_out > plan.upper.max_total_release_1000m3_per_hour):
            raise ValueError("UPPER_RELEASE_CONSTRAINT_VIOLATED")
        if (hour.lower_turbine_1000m3 > plan.lower.max_turbine_1000m3_per_hour
                or d_out > plan.lower.max_total_release_1000m3_per_hour):
            raise ValueError("LOWER_RELEASE_CONSTRAINT_VIOLATED")
        arrival = (pipe.popleft() if plan.routing_delay_hours else u_out)
        if plan.routing_delay_hours:
            pipe.append(u_out)
        up_end = up + hour.upper_local_inflow_1000m3 - u_out
        down_end = down + hour.lower_lateral_inflow_1000m3 + arrival - d_out
        if not plan.upper.minimum_1000m3 <= up_end <= plan.upper.maximum_1000m3:
            raise ValueError("UPPER_STORAGE_BOUND_VIOLATED")
        if not plan.lower.minimum_1000m3 <= down_end <= plan.lower.maximum_1000m3:
            raise ValueError("LOWER_STORAGE_BOUND_VIOLATED_OR_FUTURE_WATER_USED")
        generated = (hour.upper_turbine_1000m3
                     * plan.upper.hypothetical_energy_mwh_per_1000m3
                     + hour.lower_turbine_1000m3
                     * plan.lower.hypothetical_energy_mwh_per_1000m3)
        shortage = max(ZERO, hour.hydro_only_demand_mwh - generated)
        rows.append({
            "hour_utc": hour.hour_utc.isoformat(),
            "upper_storage_end_1000m3": _str(up_end),
            "lower_storage_end_1000m3": _str(down_end),
            "upstream_arrival_lower_1000m3": _str(arrival),
            "hydro_only_generation_mwh_assumed": _str(generated),
            "hydro_only_demand_mwh_assumed": _str(hour.hydro_only_demand_mwh),
            "hydro_only_deterministic_shortfall_mwh": _str(shortage),
        })
        up, down = up_end, down_end
        external += hour.upper_local_inflow_1000m3 + hour.lower_lateral_inflow_1000m3
        down_exits += d_out
        gen_total += generated
        demand_total += hour.hydro_only_demand_mwh
        short_total += shortage
        late_short_hours += int(shortage > ZERO)
    outstanding = sum(pipe, ZERO)
    residual = initial_total + external - down_exits - up - down - outstanding
    if residual != ZERO:
        raise ValueError("NONZERO_CASCADE_MASS_BALANCE_RESIDUAL")
    return {
        "engine": ENGINE, "scenario_id": plan.scenario_id, "input_sha256": signature,
        "routing_delay_hours_synthetic": plan.routing_delay_hours,
        "hour_count": len(rows),
        "water_initial_including_pipeline_1000m3": _str(initial_total),
        "water_external_inflow_1000m3": _str(external),
        "water_exiting_lower_1000m3": _str(down_exits),
        "water_remaining_upper_1000m3": _str(up),
        "water_remaining_lower_1000m3": _str(down),
        "water_remaining_in_pipeline_1000m3": _str(outstanding),
        "mass_balance_residual_1000m3": _str(residual),
        "hypothetical_generated_mwh": _str(gen_total),
        "hypothetical_hydro_only_demand_mwh": _str(demand_total),
        "hypothetical_hydro_only_unserved_mwh": _str(short_total),
        "hypothetical_hydro_only_shortfall_hours": late_short_hours,
        "hours": rows,
        "synthetic_plan_mass_feasible": True,
        "hydraulic_head_and_efficiency_validated": False,
        "real_travel_time_calibrated": False,
        "network_deliverability_verified": False,
        "probabilistic_lole_or_eens_calculated": False,
        "independently_certified_n1": False,
        "real_source_rights_verified": False,
        "real_available_capacity_mw": None,
        "investment_decision": "HOLD",
        "production_ready": False,
    }


def compare_synthetic_travel_delays(instant: SyntheticCascade,
                                    delayed: SyntheticCascade) -> dict:
    """Different delay, identical exogenous data and total turbine water.

    This is an identifiability counterexample, not evidence that an actual
    hydraulic wave travels between real reservoirs in one hour.
    """
    instant = SyntheticCascade.model_validate(instant.model_dump(mode="python"))
    delayed = SyntheticCascade.model_validate(delayed.model_dump(mode="python"))
    if instant.routing_delay_hours != 0 or delayed.routing_delay_hours < 1:
        raise ValueError("ZERO_AND_POSITIVE_SYNTHETIC_DELAYS_REQUIRED")
    if instant.upper != delayed.upper or instant.lower != delayed.lower:
        raise ValueError("RESERVOIR_CONTRACTS_DIFFER")
    if len(instant.hours) != len(delayed.hours):
        raise ValueError("DIFFERENT_HORIZONS")
    for a, b in zip(instant.hours, delayed.hours):
        for field in ("hour_utc", "upper_local_inflow_1000m3",
                      "lower_lateral_inflow_1000m3", "upper_turbine_1000m3",
                      "upper_spill_1000m3", "hydro_only_demand_mwh"):
            if getattr(a, field) != getattr(b, field):
                raise ValueError("EXOGENOUS_SERIES_OR_UPSTREAM_PLAN_CHANGED")
    for field in ("lower_turbine_1000m3", "lower_spill_1000m3"):
        if sum((getattr(h, field) for h in instant.hours), ZERO) != sum(
            (getattr(h, field) for h in delayed.hours), ZERO
        ):
            raise ValueError("TOTAL_DOWNSTREAM_RELEASE_CHANGED")
    if delayed.historical_in_transit_1000m3 != [ZERO] * delayed.routing_delay_hours:
        raise ValueError("COUNTEREXAMPLE_REQUIRES_EMPTY_INITIAL_PIPELINE")
    a = simulate_synthetic_cascade(instant)
    b = simulate_synthetic_cascade(delayed)
    if (a["hypothetical_generated_mwh"] != b["hypothetical_generated_mwh"]
            or a["hypothetical_hydro_only_demand_mwh"] != b["hypothetical_hydro_only_demand_mwh"]):
        raise ValueError("ENERGY_OR_DEMAND_MARGINALS_DIFFER")
    return {
        "status": "SYNTHETIC_TRAVEL_DELAY_TIMING_COUNTEREXAMPLE_ONLY",
        "same_horizon_total_generation_and_demand": True,
        "absolute_unserved_difference_mwh": _str(abs(
            Decimal(a["hypothetical_hydro_only_unserved_mwh"])
            - Decimal(b["hypothetical_hydro_only_unserved_mwh"]))),
        "instant": a, "delayed": b,
        "real_travel_time_calibrated": False,
        "independently_certified_n1": False,
        "real_available_capacity_mw": None,
        "investment_decision": "HOLD",
        "production_ready": False,
    }

