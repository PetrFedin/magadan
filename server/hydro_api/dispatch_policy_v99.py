"""V9.9: synthetic hydro/thermal scheduling-priority sensitivity only.

Compares two transparent sequential heuristics on EXACTLY the same inputs.
This is not an optimum, N-1 study, capacity certificate, operational policy
or probabilistic adequacy result; both heuristics omit water-rule constraints.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from hydro_api.winter_energy_balance_v9 import (
    DEFICIT_EPS_GWH,
    WINTER_MONTHS,
    ReservoirSpec,
    simulate_winter_balance,
)

MASS_TOLERANCE_KM3 = 1e-9
ENERGY_TOLERANCE_GWH = 1e-8
MODEL_NAME = "V99-SYNTHETIC-HYDROTHERMAL-PRIORITY-COMPARISON-1"


def _round(x: float) -> float:
    return round(x, 9)


def _verify_balance(result: Any) -> None:
    if abs(result.cascade_mass_residual_km3) > MASS_TOLERANCE_KM3:
        raise ArithmeticError("V99_SEASON_MASS_BALANCE_FAILURE")
    for step in result.months:
        if abs(step.cascade_mass_residual_km3) > MASS_TOLERANCE_KM3:
            raise ArithmeticError("V99_MONTH_MASS_BALANCE_FAILURE")
        if abs(step.load_energy_gwh - step.hydro_energy_gwh
               - step.thermal_energy_gwh - step.deficit_gwh) > ENERGY_TOLERANCE_GWH:
            raise ArithmeticError("V99_MONTH_ENERGY_BALANCE_FAILURE")
        if step.hydro_energy_gwh < -ENERGY_TOLERANCE_GWH:
            raise ArithmeticError("V99_NEGATIVE_HYDRO")
        if step.thermal_energy_gwh < -ENERGY_TOLERANCE_GWH:
            raise ArithmeticError("V99_NEGATIVE_THERMAL")
        if step.deficit_gwh < -ENERGY_TOLERANCE_GWH:
            raise ArithmeticError("V99_NEGATIVE_DEFICIT")


def _brief(result: Any, policy: str) -> dict:
    _verify_balance(result)
    return {
        "policy_assumption": policy,
        "month_count": len(result.months),
        "load_total_gwh": _round(result.load_total_gwh),
        "hydro_total_gwh": _round(result.hydro_total_gwh),
        "thermal_total_gwh": _round(result.thermal_total_gwh),
        "deterministic_unserved_total_gwh": _round(result.deficit_total_gwh),
        "unserved_month_count": sum(
            x.deficit_gwh > DEFICIT_EPS_GWH for x in result.months
        ),
        "upper_non_generating_spill_km3": _round(
            sum(x.kolyma_spill_km3 for x in result.months)
        ),
        "lower_non_generating_spill_km3": _round(
            sum(x.ust_spill_km3 for x in result.months)
        ),
        "upper_storage_end_km3": _round(result.months[-1].kolyma_storage_end_km3),
        "lower_storage_end_km3": _round(result.months[-1].ust_storage_end_km3),
        "max_abs_mass_residual_km3": max(
            abs(result.cascade_mass_residual_km3),
            *(abs(x.cascade_mass_residual_km3) for x in result.months),
        ),
        "monthly": [
            {
                "month": x.month,
                "hydro_gwh": _round(x.hydro_energy_gwh),
                "thermal_gwh": _round(x.thermal_energy_gwh),
                "deterministic_unserved_gwh": _round(x.deficit_gwh),
                "lower_spill_km3": _round(x.ust_spill_km3),
                "upper_spill_km3": _round(x.kolyma_spill_km3),
                "upper_storage_end_km3": _round(x.kolyma_storage_end_km3),
                "lower_storage_end_km3": _round(x.ust_storage_end_km3),
            }
            for x in result.months
        ],
    }


def compare_hydrothermal_policies(
    scenario: str,
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
    initial_storage_fraction: float = 1.0,
    months: tuple[int, ...] = WINTER_MONTHS,
) -> dict:
    """Compare two fixed, non-optimal heuristics with one immutable input set.

    Conserves water at both steps and records season totals, *not* a
    probability of failure. Missing physically valid operating rules remain
    excluded; no real firm available capacity is derived.
    """
    months = tuple(months)
    if not months or len(set(months)) != len(months):
        raise ValueError("V99_EMPTY_OR_REPEATED_MONTHS")
    if not set(months).issubset(set(WINTER_MONTHS)):
        raise ValueError("V99_OUTSIDE_WINTER_MONTHS")
    kwargs = {
        "kolyma": kolyma,
        "ust_srednekan": ust_srednekan,
        "peak_load_mw": peak_load_mw,
        "eta": eta,
        "thermal_available_mw": thermal_available_mw,
        "inflow_quantile": inflow_quantile,
        "inflow_by_month_m3s": dict(inflow_by_month_m3s),
        "side_inflow_annual_km3": side_inflow_annual_km3,
        "mean_annual_flow_m3s": mean_annual_flow_m3s,
        "initial_storage_fraction": initial_storage_fraction,
        "months": months,
    }
    source_payload = {
        key: (
            value.model_dump(mode="json") if isinstance(value, ReservoirSpec)
            else {str(k): v for k, v in sorted(value.items())}
                 if isinstance(value, dict)
            else list(value) if isinstance(value, tuple)
            else value
        )
        for key, value in kwargs.items()
    }
    source_payload["case_id"] = scenario
    content = json.dumps(source_payload, sort_keys=True,
                         ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    hash_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    thermal = simulate_winter_balance(
        scenario + "-THERMAL-FIRST", **kwargs, dispatch_policy="thermal_first"
    )
    hydro = simulate_winter_balance(
        scenario + "-HYDRO-FIRST", **kwargs, dispatch_policy="hydro_first"
    )
    thermal_view = _brief(thermal, "thermal_first")
    hydro_view = _brief(hydro, "hydro_first")
    if abs(thermal.load_total_gwh - hydro.load_total_gwh) > ENERGY_TOLERANCE_GWH:
        raise ArithmeticError("V99_UNMATCHED_DEMAND")
    if any(
        abs(a.kolyma_inflow_km3 - b.kolyma_inflow_km3) > MASS_TOLERANCE_KM3
        for a, b in zip(thermal.months, hydro.months)
    ):
        raise ArithmeticError("V99_UNMATCHED_INFLOW")
    return {
        "engine": MODEL_NAME,
        "case_id": scenario,
        "input_sha256": hash_sha,
        "same_assumed_input_series": True,
        "policy_comparison_not_a_dispatch_optimization": True,
        "policies": {
            "thermal_first": thermal_view,
            "hydro_first": hydro_view,
        },
        "hydro_minus_thermal": {
            "deterministic_unserved_gwh": _round(
                hydro.deficit_total_gwh - thermal.deficit_total_gwh
            ),
            "hydro_generation_gwh": _round(
                hydro.hydro_total_gwh - thermal.hydro_total_gwh
            ),
            "thermal_generation_gwh": _round(
                hydro.thermal_total_gwh - thermal.thermal_total_gwh
            ),
            "lower_spill_km3": _round(
                hydro_view["lower_non_generating_spill_km3"]
                - thermal_view["lower_non_generating_spill_km3"]
            ),
            "terminal_total_water_km3": _round(
                hydro.months[-1].kolyma_storage_end_km3
                + hydro.months[-1].ust_storage_end_km3
                - thermal.months[-1].kolyma_storage_end_km3
                - thermal.months[-1].ust_storage_end_km3
            ),
        },
        "physical_hydro_rules_validated": False,
        "real_operator_telemetry_used": False,
        "grid_n_minus_one_verified": False,
        "probabilistic_lole_eens_computed": False,
        "real_available_capacity_mw": None,
        "investment_decision": "HOLD",
        "production_ready": False,
    }
