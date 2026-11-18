"""V9.10 synthetic *minimum usable water stock* and incremental load research.

FRACTIONAL OPERATING FLOOR IS HYPOTHETICAL, NOT a legal dead pool.
This adapter exactly reserves a constant volume in each reservoir by
running the already-tested V9.9 model on *active* volume above the floor.
It does not change the validated V9.9 engine or its source-pinned artifact.
Not terminal-only optimization: minimum is enforced EVERY month, stronger.
No hydraulic head curve, mandatory releases, true turbine regimes, N-1,
asset-owner data or probabilistic LOLE/EENS are inferred.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from hydro_api.winter_energy_balance_v9 import (
    ReservoirSpec, WINTER_MONTHS, simulate_winter_balance,
)

ENGINE = "V910-SYNTHETIC-RESERVE-AND-LOAD-STRESS-1"
MASS_TOL = 1e-9
ENERGY_TOL = 1e-8


def _finite(value: object, name: str, *, minimum: float = 0.0) -> float:
    if (isinstance(value, bool) or not isinstance(value, (float, int))
            or not math.isfinite(value) or value < minimum):
        raise ValueError("V910_INVALID_" + name)
    return float(value)


def _hypothetical_floor_run(
    case_id: str,
    *,
    kolyma: ReservoirSpec,
    ust_srednekan: ReservoirSpec,
    peak_load_mw: float,
    eta: float,
    thermal_available_mw: float,
    inflow_quantile: float,
    inflow_by_month_m3s: dict[int, float],
    side_inflow_annual_km3: float,
    mean_annual_flow_m3s: float,
    initial_storage_fraction: float,
    minimum_usable_storage_fraction: float,
    dispatch_policy: str,
    months: tuple[int, ...],
) -> dict:
    floor = _finite(minimum_usable_storage_fraction, "FLOOR")
    initial = _finite(initial_storage_fraction, "INITIAL")
    if floor >= 1.0 or initial <= 0.0 or initial > 1.0 or floor > initial:
        raise ValueError("V910_RESERVE_ABOVE_INITIAL_OR_INVALID_CAPACITY")
    if dispatch_policy not in ("thermal_first", "hydro_first"):
        raise ValueError("V910_UNKNOWN_POLICY")
    # Effective usable water capacity = original capacity less hypothetical
    # constant reserve. Physical absolute stocks = active modeled stocks
    # plus the permanent reserve. Because constant offsets cancel,
    # the original two-reservoir water mass identity still holds exactly.
    active_fraction = (initial - floor) / (1.0 - floor)
    # The underlying V9.9 engine validates starting fraction > 0. A
    # physically permissible case initially AT floor is represented with
    # one tiny *positive* epsilon, whose error is bounded and reported.
    # Instead of pretending epsilon is exact, fail closed on equality.
    if active_fraction <= 0.0:
        raise ValueError("V910_INITIAL_AT_FLOOR_NOT_SUPPORTED")
    u_floor = kolyma.usable_volume_km3 * floor
    l_floor = ust_srednekan.usable_volume_km3 * floor
    u = kolyma.model_copy(update={
        "usable_volume_km3": kolyma.usable_volume_km3 * (1 - floor)})
    l = ust_srednekan.model_copy(update={
        "usable_volume_km3": ust_srednekan.usable_volume_km3 * (1 - floor)})
    raw = simulate_winter_balance(
        case_id,
        kolyma=u, ust_srednekan=l,
        peak_load_mw=peak_load_mw,
        eta=eta,
        thermal_available_mw=thermal_available_mw,
        inflow_quantile=inflow_quantile,
        inflow_by_month_m3s=dict(inflow_by_month_m3s),
        side_inflow_annual_km3=side_inflow_annual_km3,
        mean_annual_flow_m3s=mean_annual_flow_m3s,
        initial_storage_fraction=active_fraction,
        dispatch_policy=dispatch_policy,
        months=months,
    )
    if abs(raw.cascade_mass_residual_km3) > MASS_TOL:
        raise ArithmeticError("V910_SEASON_MASS_RESIDUAL")
    result_months = []
    for m in raw.months:
        upper_absolute = m.kolyma_storage_end_km3 + u_floor
        lower_absolute = m.ust_storage_end_km3 + l_floor
        if (abs(m.cascade_mass_residual_km3) > MASS_TOL
                or upper_absolute < u_floor - MASS_TOL
                or lower_absolute < l_floor - MASS_TOL
                or upper_absolute > kolyma.usable_volume_km3 + MASS_TOL
                or lower_absolute > ust_srednekan.usable_volume_km3 + MASS_TOL):
            raise ArithmeticError("V910_PHYSICAL_RESERVE_OR_MASS_VIOLATION")
        if abs(m.load_energy_gwh - m.thermal_energy_gwh
               - m.hydro_energy_gwh - m.deficit_gwh) > ENERGY_TOL:
            raise ArithmeticError("V910_MONTH_ENERGY_BUDGET_FAILED")
        result_months.append({
            "month": m.month,
            "demand_gwh": round(m.load_energy_gwh, 9),
            "hydro_gwh": round(m.hydro_energy_gwh, 9),
            "thermal_gwh": round(m.thermal_energy_gwh, 9),
            "unserved_gwh": round(m.deficit_gwh, 9),
            "upper_absolute_usable_stock_km3": round(upper_absolute, 9),
            "lower_absolute_usable_stock_km3": round(lower_absolute, 9),
            "upper_spill_km3": round(m.kolyma_spill_km3, 9),
            "lower_spill_km3": round(m.ust_spill_km3, 9),
        })
    return {
        "case_id": case_id,
        "policy": dispatch_policy,
        "minimum_usable_storage_fraction_assumption": floor,
        "initial_usable_storage_fraction_assumption": initial,
        "maximum_abs_water_residual_km3": max(
            abs(raw.cascade_mass_residual_km3),
            *(abs(m.cascade_mass_residual_km3) for m in raw.months),
        ),
        "total_demand_gwh": round(raw.load_total_gwh, 9),
        "total_hydro_gwh": round(raw.hydro_total_gwh, 9),
        "total_thermal_gwh": round(raw.thermal_total_gwh, 9),
        "total_deterministic_unserved_gwh": round(raw.deficit_total_gwh, 9),
        "unserved_month_count": sum(m.deficit_gwh > 1e-9 for m in raw.months),
        "upper_terminal_absolute_stock_km3": round(
            raw.months[-1].kolyma_storage_end_km3 + u_floor, 9),
        "lower_terminal_absolute_stock_km3": round(
            raw.months[-1].ust_storage_end_km3 + l_floor, 9),
        "upper_hypothetical_floor_km3": round(u_floor, 9),
        "lower_hypothetical_floor_km3": round(l_floor, 9),
        "lower_total_spill_km3": round(
            sum(m.ust_spill_km3 for m in raw.months), 9),
        "months": result_months,
        "production_ready": False,
    }


def compare_reserve_and_incremental_load(
    case_id: str,
    *,
    kolyma: ReservoirSpec,
    ust_srednekan: ReservoirSpec,
    baseline_peak_load_mw: float,
    extra_load_mw: float,
    eta: float,
    thermal_available_mw: float,
    inflow_quantile: float,
    inflow_by_month_m3s: dict[int, float],
    side_inflow_annual_km3: float,
    mean_annual_flow_m3s: float,
    initial_storage_fraction: float,
    minimum_usable_storage_fraction: float,
    dispatch_policy: str = "thermal_first",
    months: tuple[int, ...] = WINTER_MONTHS,
) -> dict:
    """Three controlled runs on the SAME input hydro/thermal settings.

    1) baseline demand + hypothetical monthly floor
    2) increased demand + same floor
    3) increased demand + NO floor
    Deltas are signed model-output contrasts, not customer allocations.
    """
    if not isinstance(case_id, str) or not case_id or len(case_id) > 160:
        raise ValueError("V910_BAD_CASE_ID")
    peak = _finite(baseline_peak_load_mw, "BASELINE_LOAD", minimum=1e-12)
    extra = _finite(extra_load_mw, "EXTRA_LOAD")
    if peak + extra > 100000:
        raise ValueError("V910_DEMAND_OUT_OF_SYNTHETIC_SCOPE")
    if not months or len(set(months)) != len(months) or any(
        m not in WINTER_MONTHS for m in months
    ):
        raise ValueError("V910_INVALID_MONTH_SEQUENCE")
    if tuple(months) != tuple(m for m in WINTER_MONTHS if m in months):
        raise ValueError("V910_NONCHRONOLOGICAL_MONTH_ORDER")
    inputs = dict(
        kolyma=kolyma, ust_srednekan=ust_srednekan,
        eta=eta, thermal_available_mw=thermal_available_mw,
        inflow_quantile=inflow_quantile,
        inflow_by_month_m3s=inflow_by_month_m3s,
        side_inflow_annual_km3=side_inflow_annual_km3,
        mean_annual_flow_m3s=mean_annual_flow_m3s,
        initial_storage_fraction=initial_storage_fraction,
        dispatch_policy=dispatch_policy,
        months=tuple(months),
    )
    source = {k: (v.model_dump(mode="json") if isinstance(v, ReservoirSpec)
                  else {str(x): y for x, y in sorted(v.items())}
                  if isinstance(v, dict)
                  else list(v) if isinstance(v, tuple)
                  else v) for k, v in inputs.items()}
    source.update({
        "case_id": case_id, "baseline_peak_load_mw": peak,
        "extra_load_mw": extra,
        "minimum_usable_storage_fraction": minimum_usable_storage_fraction,
    })
    receipt = sha256(json.dumps(source, sort_keys=True, allow_nan=False,
                                separators=(",", ":")).encode()).hexdigest()
    baseline = _hypothetical_floor_run(
        case_id + "-BASE", **inputs, peak_load_mw=peak,
        minimum_usable_storage_fraction=minimum_usable_storage_fraction)
    stress = _hypothetical_floor_run(
        case_id + "-STRESS", **inputs, peak_load_mw=peak+extra,
        minimum_usable_storage_fraction=minimum_usable_storage_fraction)
    nofloor = _hypothetical_floor_run(
        case_id + "-NOFLOOR", **inputs, peak_load_mw=peak+extra,
        minimum_usable_storage_fraction=0.0)
    return {
        "engine": ENGINE, "case_id": case_id,
        "input_sha256": receipt,
        "same_exogenous_hydrological_inputs": True,
        "baseline_with_floor": baseline,
        "stress_with_floor": stress,
        "stress_without_floor": nofloor,
        "delta_stress_minus_baseline_unserved_gwh": round(
            stress["total_deterministic_unserved_gwh"]
            - baseline["total_deterministic_unserved_gwh"], 9),
        "delta_floor_minus_no_floor_unserved_gwh": round(
            stress["total_deterministic_unserved_gwh"]
            - nofloor["total_deterministic_unserved_gwh"], 9),
        "delta_terminal_absolute_water_floor_minus_no_floor_km3": round(
            stress["upper_terminal_absolute_stock_km3"]
            + stress["lower_terminal_absolute_stock_km3"]
            - nofloor["upper_terminal_absolute_stock_km3"]
            - nofloor["lower_terminal_absolute_stock_km3"], 9),
        "model_deltas_are_not_consumer_shortfall_allocation": True,
        "source_data_are_historical_monthly_or_synthetic": True,
        "not_an_optimization_or_authorised_operation": True,
        "real_travel_time_calibrated": False,
        "normative_reservoir_floors_verified": False,
        "real_available_capacity_mw": None,
        "grid_n_minus_one_verified": False,
        "probabilistic_lole_or_eens_computed": False,
        "investment_decision": "HOLD",
        "production_ready": False,
    }
