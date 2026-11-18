"""Зимний энергетический баланс каскада Колымских ГЭС (V9.7).

ENGINE_ID: V9-WINTER-ENERGY-BALANCE-1

Мост «низководный сток -> гарантированная энергия», закрывающий
ограничение V9.6: там гарантированная мощность (Колымская 224 МВт,
Усть-Среднеканская 132 МВт) входила в COPT как мощностной дерейтинг,
без энергетики водохранилищ. Но зимний приток Колымы ничтожен
(rarcticnet_lowflow_v9.json, створ 5858: Q95 зимней межени после 1982 г.
~6 м³/с), поэтому зимняя выработка каскада питается ЗАПАСОМ
водохранилищ, а не притоком. V9.7 переводит это в месячный
энергетический баланс:

  * физика: энергия запаса E = rho * g * H * V * eta;
    константы rho=1000 кг/м³, g=9.80665 м/с² (физические константы,
    не данные); eta (КПД) в открытых источниках НЕ опубликован =>
    только явно помеченный сценарный диапазон (ASSUMPTION), см. скрипт;
  * каскадный эффект: вода Колымской ГЭС вторично работает на
    Усть-Среднеканской (напоры 108 + 58,4 м) — энергия на км³ выше;
  * приток в зимние месяцы: помесячные квантили низких расходов
    из R-ArcticNET (створ 5858, ЕСТЕСТВЕННЫЙ период 1933-1981, n=49 на
    месяц) — те же данные и функция квантилей, что в lowflow_v9;
    боковая приточность между плотинами (4,5 км³/год, источник в
    data/reference/kolyma_cascade_energy_v97.json) вычитается из
    притока Колымской ГЭС и добавляется Усть-Среднеканской;
  * диспетчеризация (упрощённая thermal-first): ТЭС покрывают спрос первыми
    в пределах принятой доступности; ГЭС покрывают остаток в пределах
    гарантированной мощности и запасов; если запас исчерпан,
    выработка ГЭС ограничивается водой, дефицит фиксируется в ГВт·ч;
  * нагрузка — константа на пике (консервативно, как в V9.5/V9.6).

Границы честности:
  * напор принят постоянным = расчётному (опубликованному); зависимость
    напора от уровня водохранилища не опубликована => не моделируется;
  * помесячное распределение боковой приточности не опубликовано =>
    годовая доля применяется к каждому месяцу (ASSUMPTION);
  * это НЕ оперативная модель и НЕ production-допуск
    (production_ready=False всегда).

Fail-closed: нефинитные/отрицательные значения, eta вне (0;1],
пустые ряды, неизвестный месяц => ArithmeticError.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from hydro_api.lowflow_v9 import _quantile_sorted

ENGINE_ID = "V9-WINTER-ENERGY-BALANCE-1"

RHO_WATER_KG_M3 = 1000.0
G_STANDARD_M_S2 = 9.80665
GWH_PER_JOULE = 1.0 / 3.6e12
SECONDS_PER_HOUR = 3600.0
DEFICIT_EPS_GWH = 1e-9  # допуск критерия бездефицитности (машинная пыль)

# Низководный зимний полугодовой период Колымы (ледостав): ноя—апр.
WINTER_MONTHS: Tuple[int, ...] = (11, 12, 1, 2, 3, 4)
MONTH_HOURS: Dict[int, int] = {  # невисокосный год, детерминированно
    1: 744, 2: 672, 3: 744, 4: 720, 5: 744, 6: 720,
    7: 744, 8: 744, 9: 720, 10: 744, 11: 720, 12: 744,
}

MonthlySeries = Dict[Tuple[int, int], float]  # (year, month) -> м³/с


def _check_finite_nonnegative(value: float, name: str) -> None:
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ArithmeticError(f"WEB_BAD_VALUE: {name}={value!r}")


def storage_energy_gwh(volume_km3: float, head_m: float, eta: float) -> float:
    """Энергетический эквивалент запаса воды, ГВт·ч (E = rho*g*H*V*eta)."""
    _check_finite_nonnegative(volume_km3, "volume_km3")
    _check_finite_nonnegative(head_m, "head_m")
    if not (0.0 < eta <= 1.0):
        raise ArithmeticError(f"WEB_ETA_RANGE: {eta!r}")
    return RHO_WATER_KG_M3 * G_STANDARD_M_S2 * head_m * volume_km3 * 1e9 * eta * GWH_PER_JOULE


def flow_to_power_mw(q_m3s: float, head_m: float, eta: float) -> float:
    """Мощность потока, МВт (P = rho*g*H*Q*eta)."""
    _check_finite_nonnegative(q_m3s, "q_m3s")
    _check_finite_nonnegative(head_m, "head_m")
    if not (0.0 < eta <= 1.0):
        raise ArithmeticError(f"WEB_ETA_RANGE: {eta!r}")
    return RHO_WATER_KG_M3 * G_STANDARD_M_S2 * head_m * q_m3s * eta / 1e6


def power_to_release_km3(power_mw: float, hours: float, head_m: float, eta: float) -> float:
    """Объём воды (км³) для выработки power_mw в течение hours часов."""
    _check_finite_nonnegative(power_mw, "power_mw")
    _check_finite_nonnegative(hours, "hours")
    _check_finite_nonnegative(head_m, "head_m")
    if not (0.0 < eta <= 1.0):
        raise ArithmeticError(f"WEB_ETA_RANGE: {eta!r}")
    if power_mw == 0.0 or hours == 0.0:
        return 0.0
    q_m3s = power_mw * 1e6 / (RHO_WATER_KG_M3 * G_STANDARD_M_S2 * head_m * eta)
    return q_m3s * hours * SECONDS_PER_HOUR / 1e9


def monthly_inflow_quantiles(
    series: MonthlySeries,
    *,
    months: Sequence[int] = WINTER_MONTHS,
    year_from: int,
    year_to: int,
    quantile_levels: Sequence[float] = (0.05, 0.10, 0.20, 0.50),
) -> Dict[int, Dict[float, float]]:
    """Помесячные квантили низкого стока за [year_from; year_to].

    Та же линейная квантиль, что в lowflow_v9 (V9.6), — единый метод
    во всей линии V9. Годы с пропуском месяца исключаются из этого
    месяца (не интерполируются).
    """
    if not months:
        raise ArithmeticError("WEB_EMPTY_MONTHS")
    if year_from > year_to:
        raise ArithmeticError("WEB_YEAR_RANGE")
    out: Dict[int, Dict[float, float]] = {}
    for m in months:
        if m not in MONTH_HOURS:
            raise ArithmeticError(f"WEB_MONTH_RANGE: {m}")
        vals = sorted(
            v for (y, mm), v in series.items()
            if mm == m and year_from <= y <= year_to)
        if not vals:
            raise ArithmeticError(f"WEB_EMPTY_SAMPLE: month={m}")
        for v in vals:
            _check_finite_nonnegative(v, f"series[{m}]")
        out[m] = {q: _quantile_sorted(vals, q) for q in quantile_levels}
    return out


class ReservoirSpec(BaseModel):
    """Водохранилище ГЭС: опорные опубликованные параметры."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    name_ru: str = Field(min_length=1)
    usable_volume_km3: float = Field(gt=0)
    head_m: float = Field(gt=0)
    guaranteed_capacity_mw: float = Field(gt=0)
    source_ref: str = Field(min_length=1)


class MonthStepResult(BaseModel):
    """Квитанция одного месяца каскадного баланса."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    month: int
    hours: int = Field(gt=0)
    load_energy_gwh: float = Field(ge=0)
    hydro_energy_gwh: float = Field(ge=0)
    thermal_energy_gwh: float = Field(ge=0)
    deficit_gwh: float = Field(ge=0)
    kolyma_inflow_km3: float = Field(ge=0)
    kolyma_release_km3: float = Field(ge=0)
    kolyma_storage_end_km3: float = Field(ge=0)
    ust_inflow_km3: float = Field(ge=0)
    ust_release_km3: float = Field(ge=0)
    ust_storage_end_km3: float = Field(ge=0)
    kolyma_spill_km3: float = Field(ge=0, default=0.0)
    ust_spill_km3: float = Field(ge=0, default=0.0)
    cascade_mass_residual_km3: float = 0.0


class WinterBalanceResult(BaseModel):
    """Квитанция одного зимнего сценария."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    scenario: str = Field(min_length=1)
    peak_load_mw: float = Field(gt=0)
    eta: float = Field(gt=0, le=1)
    eta_is_assumption: bool = True
    thermal_available_mw: float = Field(ge=0)
    inflow_quantile: float = Field(gt=0, lt=1)
    initial_storage_fraction: float = Field(gt=0, le=1)
    months: List[MonthStepResult]
    load_total_gwh: float = Field(ge=0)
    hydro_total_gwh: float = Field(ge=0)
    thermal_total_gwh: float = Field(ge=0)
    deficit_total_gwh: float = Field(ge=0)
    kolyma_storage_min_km3: float = Field(ge=0)
    ust_storage_min_km3: float = Field(ge=0)
    feasible_no_deficit: bool
    cascade_mass_residual_km3: float = 0.0
    production_ready: bool = False


def simulate_winter_balance(
    scenario: str,
    *,
    kolyma: ReservoirSpec,
    ust_srednekan: ReservoirSpec,
    peak_load_mw: float,
    eta: float,
    thermal_available_mw: float,
    inflow_quantile: float,
    inflow_by_month_m3s: Dict[int, float],
    side_inflow_annual_km3: float,
    mean_annual_flow_m3s: float,
    initial_storage_fraction: float = 1.0,
    months: Sequence[int] = WINTER_MONTHS,
    dispatch_policy: str = "thermal_first",
    minimum_upper_storage_fraction: float = 0.0,
    minimum_lower_storage_fraction: float = 0.0,
) -> WinterBalanceResult:
    """Месячный каскадный баланс низководной зимы.

    Приток Колымской ГЭС = сток створa 5858 x (1 - доля боковой
    приточности); боковая приточность добавляется Усть-Среднеканской.
    Доля боковой приточности выводится из двух опубликованных чисел
    (годовой объём боковой приточности / среднемноголетний сток) и
    применяется помесячно (ASSUMPTION — помесячное распределение не
    опубликовано). ТЭС покрывают нагрузку первыми в пределах сценарной доступности;
    ГЭС закрывают остаток при достаточном запасе; нагрузка постоянна.
    """
    if not scenario:
        raise ArithmeticError("WEB_NO_SCENARIO")
    if dispatch_policy not in ("thermal_first", "hydro_first"):
        raise ArithmeticError("WEB_UNKNOWN_DISPATCH_POLICY")
    _check_finite_nonnegative(peak_load_mw, "peak_load_mw")
    if peak_load_mw <= 0:
        raise ArithmeticError("WEB_ZERO_LOAD")
    if not (0.0 < eta <= 1.0):
        raise ArithmeticError(f"WEB_ETA_RANGE: {eta!r}")
    _check_finite_nonnegative(thermal_available_mw, "thermal_available_mw")
    if not (0.0 < inflow_quantile < 1.0):
        raise ArithmeticError(f"WEB_QUANTILE_RANGE: {inflow_quantile!r}")
    if not (0.0 < initial_storage_fraction <= 1.0):
        raise ArithmeticError(f"WEB_STORAGE_FRACTION: {initial_storage_fraction!r}")
    # Synthetic V9.10 continuous operating floors, NOT legal minimum levels.
    # A monthly floor is stricter than a terminal-only April constraint.
    for name, floor in (
        ("upper", minimum_upper_storage_fraction),
        ("lower", minimum_lower_storage_fraction),
    ):
        if (isinstance(floor, bool) or not isinstance(floor, (float, int))
                or not math.isfinite(floor) or not 0.0 <= floor <= 1.0):
            raise ArithmeticError(f"WEB_INVALID_SYNTHETIC_FLOOR_{name.upper()}")
        if floor > initial_storage_fraction:
            raise ArithmeticError(f"WEB_FLOOR_EXCEEDS_INITIAL_{name.upper()}")
    _check_finite_nonnegative(side_inflow_annual_km3, "side_inflow_annual_km3")
    _check_finite_nonnegative(mean_annual_flow_m3s, "mean_annual_flow_m3s")
    if mean_annual_flow_m3s <= 0:
        raise ArithmeticError("WEB_ZERO_MEAN_FLOW")
    side_share = side_inflow_annual_km3 / (mean_annual_flow_m3s * 31.536e6 / 1e9)
    if not (0.0 <= side_share < 1.0):
        raise ArithmeticError(f"WEB_SIDE_SHARE_RANGE: {side_share!r}")

    kol_storage = kolyma.usable_volume_km3 * initial_storage_fraction
    ust_storage = ust_srednekan.usable_volume_km3 * initial_storage_fraction
    kol_floor = kolyma.usable_volume_km3 * minimum_upper_storage_fraction
    ust_floor = ust_srednekan.usable_volume_km3 * minimum_lower_storage_fraction
    kol_min, ust_min = kol_storage, ust_storage
    steps: List[MonthStepResult] = []
    initial_water_km3 = kol_storage + ust_storage
    external_water_km3 = 0.0
    downstream_exit_km3 = 0.0
    totals = {"load": 0.0, "hydro": 0.0, "thermal": 0.0, "deficit": 0.0}

    for m in months:
        if m not in MONTH_HOURS:
            raise ArithmeticError(f"WEB_MONTH_RANGE: {m}")
        if m not in inflow_by_month_m3s:
            raise ArithmeticError(f"WEB_NO_INFLOW: month={m}")
        hours = MONTH_HOURS[m]
        q5858 = inflow_by_month_m3s[m]
        _check_finite_nonnegative(q5858, f"inflow[{m}]")
        month_volume_km3 = q5858 * hours * SECONDS_PER_HOUR / 1e9
        kol_inflow = month_volume_km3 * (1.0 - side_share)
        side_inflow = month_volume_km3 * side_share

        load_gwh = peak_load_mw * hours / 1000.0
        # Both policies use exactly the SAME data, mass conservation and
        # per-generator limits; only the priority of scheduling changes.
        # Neither heuristic is a physically validated operator dispatch.
        thermal_cap_gwh = thermal_available_mw * hours / 1000.0
        thermal_gwh = (min(load_gwh, thermal_cap_gwh)
                       if dispatch_policy == "thermal_first" else 0.0)
        hydro_need_gwh = max(0.0, load_gwh - thermal_gwh)

        # Колымская: целевая выработка = гарантированная мощность,
        # ограниченная потребностью системы и запасом воды.
        kol_target_gwh = min(kolyma.guaranteed_capacity_mw * hours / 1000.0,
                             hydro_need_gwh)
        kol_release_need = power_to_release_km3(
            kol_target_gwh * 1000.0 / hours, hours, kolyma.head_m, eta)
        kol_begin = kol_storage
        ust_begin = ust_storage
        kol_release = min(kol_release_need, max(
            0.0, kol_begin + kol_inflow - kol_floor))
        kol_energy = storage_energy_gwh(kol_release, kolyma.head_m, eta)
        # Explicit overflow: disappearing water would break mass conservation.
        # Upper spill is non-generating but still enters the lower reservoir.
        kol_spill = max(0.0, kol_begin + kol_inflow - kol_release
                        - kolyma.usable_volume_km3)
        kol_storage = kol_begin + kol_inflow - kol_release - kol_spill

        # Lower receives BOTH upper turbine discharge and non-generating spill.
        # No travel-time/hydraulic constraints are inferred at monthly grain.
        ust_inflow = kol_release + kol_spill + side_inflow
        ust_target_gwh = min(
            ust_srednekan.guaranteed_capacity_mw * hours / 1000.0,
            max(0.0, hydro_need_gwh - kol_energy))
        ust_release_need = power_to_release_km3(
            ust_target_gwh * 1000.0 / hours, hours, ust_srednekan.head_m, eta)
        ust_release = min(ust_release_need, max(
            0.0, ust_begin + ust_inflow - ust_floor))
        ust_energy = storage_energy_gwh(ust_release, ust_srednekan.head_m, eta)
        ust_spill = max(0.0, ust_begin + ust_inflow - ust_release
                        - ust_srednekan.usable_volume_km3)
        ust_storage = ust_begin + ust_inflow - ust_release - ust_spill

        # Upper turbine release/spill is internal transfer and must not be
        # deducted from the total two-reservoir system a second time.
        external_water_km3 += kol_inflow + side_inflow
        downstream_exit_km3 += ust_release + ust_spill
        monthly_residual = (kol_begin + ust_begin + kol_inflow + side_inflow
                            - ust_release - ust_spill - kol_storage - ust_storage)
        if abs(monthly_residual) > 1e-9:
            raise ArithmeticError("WEB_MONTHLY_CASCADE_MASS_CONSERVATION_FAILED")
        if (kol_storage < kol_floor - 1e-9
                or ust_storage < ust_floor - 1e-9
                or kol_storage > kolyma.usable_volume_km3 + 1e-9
                or ust_storage > ust_srednekan.usable_volume_km3 + 1e-9):
            raise ArithmeticError("WEB_RESERVOIR_STORAGE_OUTSIDE_BOUNDS")

        hydro_gwh = kol_energy + ust_energy
        if dispatch_policy == "hydro_first":
            # Thermal is the *residual* source after feasible hydro generation.
            thermal_gwh = min(thermal_cap_gwh, max(0.0, load_gwh - hydro_gwh))
        deficit = max(0.0, load_gwh - thermal_gwh - hydro_gwh)
        # Strict budget: scenario generation cannot materially exceed demand.
        if hydro_gwh + thermal_gwh > load_gwh + 1e-8:
            raise ArithmeticError("WEB_ENERGY_GENERATED_ABOVE_DEMAND")
        if abs(load_gwh - thermal_gwh - hydro_gwh - deficit) > 1e-8:
            raise ArithmeticError("WEB_MONTH_ENERGY_RESIDUAL")

        kol_min = min(kol_min, kol_storage)
        ust_min = min(ust_min, ust_storage)
        totals["load"] += load_gwh
        totals["hydro"] += hydro_gwh
        totals["thermal"] += thermal_gwh
        totals["deficit"] += deficit
        steps.append(MonthStepResult(
            month=m, hours=hours,
            load_energy_gwh=load_gwh, hydro_energy_gwh=hydro_gwh,
            thermal_energy_gwh=thermal_gwh, deficit_gwh=deficit,
            kolyma_inflow_km3=kol_inflow, kolyma_release_km3=kol_release,
            kolyma_storage_end_km3=kol_storage,
            ust_inflow_km3=ust_inflow, ust_release_km3=ust_release,
            ust_storage_end_km3=ust_storage,
            kolyma_spill_km3=kol_spill,
            ust_spill_km3=ust_spill,
            cascade_mass_residual_km3=monthly_residual))

    season_mass_residual = (initial_water_km3 + external_water_km3
                            - downstream_exit_km3 - kol_storage - ust_storage)
    if abs(season_mass_residual) > 1e-9:
        raise ArithmeticError("WEB_SEASON_CASCADE_MASS_CONSERVATION_FAILED")

    return WinterBalanceResult(
        scenario=scenario,
        peak_load_mw=peak_load_mw,
        eta=eta,
        thermal_available_mw=thermal_available_mw,
        inflow_quantile=inflow_quantile,
        initial_storage_fraction=initial_storage_fraction,
        months=steps,
        load_total_gwh=totals["load"],
        hydro_total_gwh=totals["hydro"],
        thermal_total_gwh=totals["thermal"],
        deficit_total_gwh=totals["deficit"],
        kolyma_storage_min_km3=kol_min,
        ust_storage_min_km3=ust_min,
        feasible_no_deficit=totals["deficit"] < DEFICIT_EPS_GWH,
        cascade_mass_residual_km3=season_mass_residual,
    )
