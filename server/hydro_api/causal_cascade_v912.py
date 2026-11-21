"""V9.12 deterministic two-reservoir, delayed multi-period numerical laboratory.

DO NOT USE FOR REAL HYDRO DISPATCH. Real stage-volume and tailwater curves,
efficiency/transport calibration, lawful operating zones and owner telemetry
are missing. Field mode is permanently fail-closed until a separately
reviewed source admission workflow is implemented.

A synthetic, physically dimensional test harness distinguishes:
- INFEASIBLE_DISPATCH: a demonstrable water, power or selected cold-rule breach
- DATA_INSUFFICIENT: missing operational evidence, including unresolved cold
- SYNTHETIC_CONSISTENT: algebraically consistent in *synthetic* assumptions
- DETERMINISTIC_SHORTFALL: a SEPARATE energy adequacy outcome

No silent water clipping, invented spill, same-step downstream reuse of
upstream discharge at delay>0, or implied certified available MW.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import Any

RHO_G = 9.80665 * 1000
KM3 = 1_000_000_000
MASS_TOL = 1e-9
ENERGY_TOL = 1e-8
COLD_MONTHS = frozenset((10, 11, 12, 1, 2, 3, 4))
MODEL = "V912-CAUSAL-TWO-RESERVOIR-SYNTHETIC-LAB-1"


class InvalidInput(ValueError):
    pass


class UnavailableEvidence(RuntimeError):
    pass


class Infeasible(RuntimeError):
    pass


def _numeric(value: Any, label: str, minimum: float = 0.0) -> float:
    if (isinstance(value, bool) or not isinstance(value, (float, int))
            or not isfinite(value) or value < minimum):
        raise InvalidInput("V912_INVALID_" + label)
    return float(value)


@dataclass(frozen=True)
class MonotoneCurve:
    """Points are x -> y, strictly increasing and research-only."""
    points: tuple[tuple[float, float], ...]
    x_unit: str
    y_unit: str
    provenance: str = "SYNTHETIC_ONLY"

    def __post_init__(self):
        if self.provenance != "SYNTHETIC_ONLY":
            raise UnavailableEvidence("V912_UNVERIFIED_REAL_CURVE")
        if len(self.points) < 2:
            raise InvalidInput("V912_CURVE_REQUIRES_MULTIPLE_KNOTS")
        if any(len(p) != 2 for p in self.points):
            raise InvalidInput("V912_BAD_CURVE_POINT")
        last_x = last_y = None
        for x, y in self.points:
            _numeric(x, "CURVE_X")
            _numeric(y, "CURVE_Y")
            if last_x is not None and not (x > last_x and y > last_y):
                raise InvalidInput("V912_CURVE_NOT_STRICTLY_MONOTONIC")
            last_x, last_y = x, y

    def at(self, x: float) -> float:
        _numeric(x, "CURVE_EVALUATION")
        if x < self.points[0][0] - 1e-12 or x > self.points[-1][0] + 1e-12:
            raise Infeasible("V912_CURVE_EXTRAPOLATION_FORBIDDEN")
        for (x0, y0), (x1, y1) in zip(self.points, self.points[1:]):
            if x0 - 1e-12 <= x <= x1 + 1e-12:
                return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        raise Infeasible("V912_CURVE_COVERAGE_GAP")


@dataclass(frozen=True)
class ReservoirModel:
    name: str
    stage_from_total_volume: MonotoneCurve  # km3 -> metres (synthetic)
    tailwater_from_release: MonotoneCurve  # m3/s -> metres (synthetic)
    minimum_total_km3: float
    maximum_total_km3: float
    max_turbine_release_m3_s: float
    installed_mw: float
    efficiency_assumption: float
    hydraulic_loss_m: float
    minimum_net_head_m: float
    maximum_net_head_m: float

    def __post_init__(self):
        for f in (
            "minimum_total_km3", "maximum_total_km3",
            "max_turbine_release_m3_s", "installed_mw",
            "efficiency_assumption", "hydraulic_loss_m",
            "minimum_net_head_m", "maximum_net_head_m"
        ):
            _numeric(getattr(self, f), f)
        if (not self.name or
                self.stage_from_total_volume.x_unit != "km3"
                or self.stage_from_total_volume.y_unit != "m_synthetic_datum"
                or self.tailwater_from_release.x_unit != "m3/s"
                or self.tailwater_from_release.y_unit != "m_synthetic_datum"
                or not self.minimum_total_km3 < self.maximum_total_km3
                or not 0 < self.efficiency_assumption <= 1
                or not 0 < self.minimum_net_head_m < self.maximum_net_head_m
                or self.maximum_total_km3 > self.stage_from_total_volume.points[-1][0]
                or self.minimum_total_km3 < self.stage_from_total_volume.points[0][0]
                or self.max_turbine_release_m3_s > self.tailwater_from_release.points[-1][0]):
            raise InvalidInput("V912_INCONSISTENT_SYNTHETIC_RESERVOIR")


@dataclass(frozen=True)
class Step:
    start: str  # Offset-aware ISO 8601, no local ambiguous dates.
    duration_hours: float
    upstream_inflow_m3_s: float
    lateral_inflow_m3_s: float
    upper_turbine_m3_s: float
    upper_bypass_m3_s: float
    lower_turbine_m3_s: float
    lower_bypass_m3_s: float
    demand_mw: float
    thermal_available_mw: float
    stable_negative_temperatures: bool | None

    def __post_init__(self):
        for name in ("duration_hours", "upstream_inflow_m3_s",
                     "lateral_inflow_m3_s", "upper_turbine_m3_s",
                     "upper_bypass_m3_s", "lower_turbine_m3_s",
                     "lower_bypass_m3_s", "demand_mw", "thermal_available_mw"):
            _numeric(getattr(self, name), name)
        if not 0 < self.duration_hours <= 744:
            raise InvalidInput("V912_INVALID_STEP_DURATION")
        try:
            dt = datetime.fromisoformat(self.start)
        except (TypeError, ValueError) as exc:
            raise InvalidInput("V912_BAD_DATETIME") from exc
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise InvalidInput("V912_DATETIME_WITHOUT_OFFSET")
        if (self.stable_negative_temperatures is not None
                and type(self.stable_negative_temperatures) is not bool):
            raise InvalidInput("V912_UNSUPPORTED_COLDNESS_EVIDENCE")


def _power_mw(spec: ReservoirModel, turbine_q: float, bypass_q: float,
              start_storage: float, end_storage: float) -> tuple[float, float]:
    if turbine_q > spec.max_turbine_release_m3_s + 1e-10:
        raise Infeasible("V912_TURBINE_FLOW_ABOVE_SYNTHETIC_LIMIT:" + spec.name)
    mean_volume = (start_storage + end_storage) / 2
    forebay = spec.stage_from_total_volume.at(mean_volume)
    tailwater = spec.tailwater_from_release.at(turbine_q + bypass_q)
    head = forebay - tailwater - spec.hydraulic_loss_m
    if not spec.minimum_net_head_m <= head <= spec.maximum_net_head_m:
        raise Infeasible("V912_HEAD_OUTSIDE_SYNTHETIC_EQUIPMENT_RANGE:" + spec.name)
    power = RHO_G * turbine_q * head * spec.efficiency_assumption / 1_000_000
    if power > spec.installed_mw + 1e-9:
        raise Infeasible("V912_POWER_OVER_SYNTHETIC_NAMEPLATE:" + spec.name)
    return power, head


def _no_approval(base: dict) -> dict:
    return {
        **base,
        "research_engine": MODEL,
        "water_rule_certification": False,
        "actual_stage_volume_curves_present": False,
        "actual_unit_efficiency_curves_present": False,
        "operator_calibrated_routing": False,
        "real_available_capacity_mw": None,
        "network_n_minus_one_verified": False,
        "probabilistic_lole_eens_computed": False,
        "investment_decision": "HOLD",
        "production_ready": False,
    }


def simulate_multiperiod(
    *, upper: ReservoirModel, lower: ReservoirModel,
    steps: tuple[Step, ...], initial_upper_km3: float,
    initial_lower_km3: float, transit_delay_steps: int,
    mode: str = "synthetic",
) -> dict:
    """Explicit causal pipeline, no clipping and no operational approvals.

    If a planned action violates physical/synthetic constraints, STOP at
    that step, do not infer future served energy or fabricate spill.
    For unverified real inputs, return DATA_INSUFFICIENT with NO numbers.
    """
    if mode not in ("synthetic", "field"):
        raise InvalidInput("V912_UNKNOWN_EXECUTION_MODE")
    if mode == "field":
        return _no_approval({
            "status": "DATA_INSUFFICIENT",
            "energy_status": "NOT_EVALUATED",
            "reason": "V912_REAL_CURVES_ZONES_WEATHER_RIGHTS_NOT_AUTHENTICATED",
            "steps": [],
            "total_unserved_gwh": None,
        })
    if (isinstance(transit_delay_steps, bool) or
            not isinstance(transit_delay_steps, int) or
            not 1 <= transit_delay_steps <= 30):
        raise InvalidInput("V912_DELAY_NOT_POSITIVE_VERIFIED_STEP_COUNT")
    _numeric(initial_upper_km3, "INITIAL_UPPER_VOLUME")
    _numeric(initial_lower_km3, "INITIAL_LOWER_VOLUME")
    if not steps or len(steps) > 400:
        raise InvalidInput("V912_EMPTY_OR_OVERSIZED_HORIZON")
    if not upper.minimum_total_km3 <= initial_upper_km3 <= upper.maximum_total_km3:
        raise InvalidInput("V912_UPPER_INITIAL_OUT_OF_RANGE")
    if not lower.minimum_total_km3 <= initial_lower_km3 <= lower.maximum_total_km3:
        raise InvalidInput("V912_LOWER_INITIAL_OUT_OF_RANGE")
    if any(not isinstance(s, Step) for s in steps):
        raise InvalidInput("V912_INVALID_STEP")
    for previous, current in zip(steps, steps[1:]):
        if (datetime.fromisoformat(current.start) !=
            datetime.fromisoformat(previous.start) +
                timedelta(hours=previous.duration_hours)):
            raise InvalidInput("V912_HORIZON_HAS_GAP_OR_OVERLAP")
        if abs(current.duration_hours - previous.duration_hours) > 1e-12:
            raise InvalidInput("V912_UNEQUAL_STEPS_FOR_DISCRETE_DELAY")
    initial = initial_upper_km3 + initial_lower_km3
    u, l = float(initial_upper_km3), float(initial_lower_km3)
    queue = [0.0 for _ in range(transit_delay_steps)]
    total_in = total_out = total_unserved = total_demand = 0.0
    total_hydro = total_thermal = 0.0
    records = []
    for index, step in enumerate(steps):
        time = datetime.fromisoformat(step.start)
        q = (step.upper_turbine_m3_s, step.upper_bypass_m3_s,
             step.lower_turbine_m3_s, step.lower_bypass_m3_s)
        upper_release = q[0] + q[1]
        lower_release = q[2] + q[3]
        factor = step.duration_hours * 3600 / KM3
        inflow_u = step.upstream_inflow_m3_s * factor
        inflow_l = step.lateral_inflow_m3_s * factor
        outgoing_u = upper_release * factor
        outgoing_l = lower_release * factor
        arriving = queue[0]
        u_next = u + inflow_u - outgoing_u
        l_next = l + inflow_l + arriving - outgoing_l
        violation = None
        unknown = None
        if time.month in COLD_MONTHS and (q[1] > 1e-12 or q[3] > 1e-12):
            if step.stable_negative_temperatures is True:
                violation = "V912_COLD_PERIOD_BYPASS_CONFLICT_VIII_52"
            elif step.stable_negative_temperatures is None:
                unknown = "V912_COLDNESS_UNKNOWN_BYPASS_POSSIBLY_FORBIDDEN"
        if not violation and not unknown:
            if not (upper.minimum_total_km3 - MASS_TOL <= u_next
                    <= upper.maximum_total_km3 + MASS_TOL):
                violation = "V912_UPPER_INVENTORY_OVERFLOW_OR_UNDERFLOW"
            elif not (lower.minimum_total_km3 - MASS_TOL <= l_next
                      <= lower.maximum_total_km3 + MASS_TOL):
                violation = "V912_LOWER_INVENTORY_OVERFLOW_OR_UNDERFLOW"
        if unknown or violation:
            return _no_approval({
                "status": "DATA_INSUFFICIENT" if unknown else "INFEASIBLE_DISPATCH",
                "energy_status": "NOT_EVALUATED",
                "reason": unknown or violation,
                "failing_step": index,
                "steps": records,
                "total_unserved_gwh": None,
                "initial_pipeline_km3": 0.0,
            })
        try:
            power_u, head_u = _power_mw(upper, q[0], q[1], u, u_next)
            power_l, head_l = _power_mw(lower, q[2], q[3], l, l_next)
        except Infeasible as exc:
            return _no_approval({
                "status": "INFEASIBLE_DISPATCH",
                "energy_status": "NOT_EVALUATED",
                "reason": str(exc),
                "failing_step": index,
                "steps": records,
                "total_unserved_gwh": None,
            })
        hydro_gwh = (power_u + power_l) * step.duration_hours / 1000
        load_gwh = step.demand_mw * step.duration_hours / 1000
        if hydro_gwh > load_gwh + ENERGY_TOL:
            return _no_approval({
                "status": "INFEASIBLE_DISPATCH",
                "energy_status": "NOT_EVALUATED",
                "reason": "V912_NO_DEMAND_OR_EXPORT_SINK_FOR_SCHEDULED_HYDRO",
                "failing_step": index,
                "steps": records,
                "total_unserved_gwh": None,
            })
        thermal_gwh = min(max(0.0, load_gwh - hydro_gwh),
                          step.thermal_available_mw * step.duration_hours / 1000)
        deficit_gwh = max(0.0, load_gwh - hydro_gwh - thermal_gwh)
        next_queue = queue[1:] + [outgoing_u]
        total_in += inflow_u + inflow_l
        total_out += outgoing_l
        stock = u_next + l_next + sum(next_queue)
        residual = initial + total_in - total_out - stock
        if abs(residual) > MASS_TOL or abs(
            load_gwh - hydro_gwh - thermal_gwh - deficit_gwh
        ) > ENERGY_TOL:
            raise ArithmeticError("V912_MASS_OR_ENERGY_NOT_CONSERVED")
        records.append({
            "step": index, "start": step.start,
            "upstream_in_km3": round(inflow_u, 12),
            "lateral_in_km3": round(inflow_l, 12),
            "delayed_arrival_km3": round(arriving, 12),
            "upper_release_to_transit_km3": round(outgoing_u, 12),
            "lower_release_out_of_system_km3": round(outgoing_l, 12),
            "water_in_flight_end_km3": round(sum(next_queue), 12),
            "upper_storage_end_km3": round(u_next, 12),
            "lower_storage_end_km3": round(l_next, 12),
            "upper_net_head_assumed_m": round(head_u, 9),
            "lower_net_head_assumed_m": round(head_l, 9),
            "hydro_gwh": round(hydro_gwh, 9),
            "thermal_gwh": round(thermal_gwh, 9),
            "load_gwh": round(load_gwh, 9),
            "deterministic_unserved_gwh": round(deficit_gwh, 9),
            "full_system_mass_residual_km3": residual,
        })
        u, l, queue = u_next, l_next, next_queue
        total_unserved += deficit_gwh
        total_demand += load_gwh
        total_hydro += hydro_gwh
        total_thermal += thermal_gwh
    return _no_approval({
        "status": "SYNTHETIC_CONSISTENT",
        "energy_status": ("DETERMINISTIC_SHORTFALL" if total_unserved > 1e-8
                          else "NO_CALCULATED_SHORTFALL"),
        "reason": "SYNTHETIC_PHYSICS_ONLY_NO_STATUTORY_DISPATCH_AUTHORITY",
        "steps": records,
        "period_count": len(records),
        "routing_delay_steps_assumed": transit_delay_steps,
        "initial_system_stock_km3": initial,
        "terminal_upstream_km3": round(u, 12),
        "terminal_downstream_km3": round(l, 12),
        "terminal_water_in_flight_km3": round(sum(queue), 12),
        "cumulative_exogenous_inflow_km3": round(total_in, 12),
        "cumulative_outlet_flow_km3": round(total_out, 12),
        "total_demand_gwh": round(total_demand, 9),
        "total_hydro_gwh": round(total_hydro, 9),
        "total_thermal_gwh": round(total_thermal, 9),
        "total_unserved_gwh": round(total_unserved, 9),
        "season_mass_residual_km3": initial + total_in - total_out
                                   - u - l - sum(queue),
    })


def synthetic_demo(steps: tuple[Step, ...] | None = None,
                   mode: str = "synthetic") -> dict:
    """Entirely fabricated two-reservoir curves; NOT Kolyma hydro parameters."""
    upper = ReservoirModel(
        name="SYNTHETIC_UPPER",
        stage_from_total_volume=MonotoneCurve(
            ((1.0, 100.0), (2.0, 120.0), (3.0, 135.0)),
            "km3", "m_synthetic_datum"),
        tailwater_from_release=MonotoneCurve(
            ((0.0, 20.0), (100.0, 20.5), (500.0, 23.0)),
            "m3/s", "m_synthetic_datum"),
        minimum_total_km3=1.0, maximum_total_km3=3.0,
        max_turbine_release_m3_s=450.0, installed_mw=400.0,
        efficiency_assumption=0.9, hydraulic_loss_m=1.0,
        minimum_net_head_m=70.0, maximum_net_head_m=130.0,
    )
    lower = ReservoirModel(
        name="SYNTHETIC_LOWER",
        stage_from_total_volume=MonotoneCurve(
            ((0.8, 50.0), (1.5, 61.0), (2.5, 75.0)),
            "km3", "m_synthetic_datum"),
        tailwater_from_release=MonotoneCurve(
            ((0.0, 25.0), (100.0, 25.5), (500.0, 27.0)),
            "m3/s", "m_synthetic_datum"),
        minimum_total_km3=0.8, maximum_total_km3=2.5,
        max_turbine_release_m3_s=450.0, installed_mw=210.0,
        efficiency_assumption=0.9, hydraulic_loss_m=0.4,
        minimum_net_head_m=20.0, maximum_net_head_m=50.0,
    )
    if steps is None:
        begin = datetime.fromisoformat("2026-11-01T00:00:00+03:00")
        steps = tuple(Step(
            start=(begin + timedelta(days=i)).isoformat(),
            duration_hours=24.0,
            upstream_inflow_m3_s=100.0, lateral_inflow_m3_s=30.0,
            upper_turbine_m3_s=80.0, upper_bypass_m3_s=0.0,
            lower_turbine_m3_s=75.0, lower_bypass_m3_s=0.0,
            demand_mw=120.0, thermal_available_mw=100.0,
            stable_negative_temperatures=True,
        ) for i in range(8))
    return simulate_multiperiod(
        upper=upper, lower=lower, steps=steps,
        initial_upper_km3=2.3, initial_lower_km3=1.7,
        transit_delay_steps=2, mode=mode,
    )
