"""Адекватность энергосистемы с EFORd-приорами из открытой статистики (V9.5).

ENGINE_ID: V9-SYSTEM-ADEQUACY-EFORD-1

Мост между двумя существующими модулями:
  * forced_outage_v9 (V9.4): EFORd по IEEE 762 / GADS / PJM M22 и
    пуллинг малой истории к классовому среднему;
  * adequacy_v9 (V9.1): COPT свёртка, LOLE/EENS, критерий N-1.

Назначение: оценить адекватность изолированной энергосистемы Магаданской
области на ОТКРЫТЫХ опорных данных (data/reference/
kolyma_magadan_open_sources.json: ГЭС 5x180 + 4x142,5 МВт, ТЭС 320 МВт,
пик 460 МВт (2023), прогноз 564-574 МВт на 2025-2030; все числа со
source_ref) с классовым EFORd-приором GADS hydro (5,43 %,
data/reference/hydro_for_open_stats.json).

Границы честности (всё зафиксировано в отчёте):
  * классовая статистика GADS — североамериканский флот; перенос на
    Колымский каскад — только априорный класс (см. ограничения V9.4);
  * состав ТЭС по агрегатам в открытых источниках не опубликован —
    сценарное сканирование по разбиению 320 МВт (ASSUMPTION, не данные);
  * хронологическая кривая нагрузки не опубликована — нагрузка берётся
    КОНСТАНТНОЙ на уровне пика (консервативная верхняя оценка LOLE/EENS);
  * натурной статистики отказов нет => for_is_assumption=True =>
    decision=HOLD (наследуется из adequacy_v9).
"""
from __future__ import annotations

from typing import Dict, List, Sequence

from pydantic import BaseModel, ConfigDict, Field

from hydro_api.adequacy_v9 import GeneratingUnit, evaluate_adequacy

ENGINE_ID = "V9-SYSTEM-ADEQUACY-EFORD-1"


class UnitGroupSpec(BaseModel):
    """Группа одинаковых агрегатов с общим EFORd."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    name_prefix: str = Field(min_length=1, max_length=80)
    n_units: int = Field(ge=1)
    unit_capacity_mw: float = Field(gt=0)
    eford_d: float = Field(ge=0.0, lt=1.0)
    source_ref: str = Field(min_length=1)
    eford_source_ref: str = Field(min_length=1)
    for_is_assumption: bool = True


class SystemScenarioResult(BaseModel):
    """Квитанция одного сценария адекватности."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    scenario: str = Field(min_length=1)
    units_count: int = Field(ge=1)
    installed_capacity_mw: float = Field(gt=0)
    peak_load_mw: float = Field(gt=0)
    lole_hours_per_year: float = Field(ge=0)
    eens_mwh_per_year: float = Field(ge=0)
    lolp_at_peak: float = Field(ge=0.0, le=1.0)
    n_minus_1_secure: bool
    n_minus_1_margin_mw: float
    for_assumption: bool
    decision: str
    production_ready: bool = False


def build_units(spec: UnitGroupSpec) -> List[GeneratingUnit]:
    """Разворачивает группу в список двухсостоятельных агрегатов."""
    return [
        GeneratingUnit(
            name=f"{spec.name_prefix}-{i + 1}",
            capacity_mw=spec.unit_capacity_mw,
            forced_outage_rate=spec.eford_d,
            for_is_assumption=spec.for_is_assumption,
        )
        for i in range(spec.n_units)
    ]


def evaluate_system(
    scenario: str,
    groups: Sequence[UnitGroupSpec],
    peak_load_mw: float,
    *,
    hours_per_year: float = 8760.0,
) -> SystemScenarioResult:
    """LOLE/EENS/N-1 для постоянной нагрузки на уровне пика (консервативно)."""
    if not scenario:
        raise ArithmeticError("SYSADQ_NO_SCENARIO_NAME")
    if peak_load_mw <= 0:
        raise ArithmeticError(f"SYSADQ_PEAK_RANGE: {peak_load_mw} <= 0")
    if hours_per_year <= 0:
        raise ArithmeticError(f"SYSADQ_HOURS_RANGE: {hours_per_year} <= 0")
    if not groups:
        raise ArithmeticError("SYSADQ_NO_GROUPS")
    units: List[GeneratingUnit] = []
    for g in groups:
        units.extend(build_units(g))
    # постоянная нагрузка на пике: LOLE в ч/год = LOLP_peak * 8760 (верхняя
    # оценка против хронологической кривой, где нагрузка ниже пика)
    res = evaluate_adequacy(units, [peak_load_mw], step_hours=hours_per_year)
    return SystemScenarioResult(
        scenario=scenario,
        units_count=res.units_count,
        installed_capacity_mw=res.installed_capacity_mw,
        peak_load_mw=peak_load_mw,
        lole_hours_per_year=res.lole_hours,
        eens_mwh_per_year=res.eens_mwh,
        lolp_at_peak=res.loss_of_load_probability_peak,
        n_minus_1_secure=res.n_minus_1_secure,
        n_minus_1_margin_mw=res.n_minus_1_margin_mw,
        for_assumption=res.for_assumption,
        decision=res.decision,
    )


def thermal_split_scenarios(
    total_mw: float,
    splits: Sequence[int],
    eford_d: float,
    source_ref: str,
    eford_source_ref: str,
) -> Dict[str, UnitGroupSpec]:
    """Сценарии разбиения ТЭС (состав агрегатов не опубликован — ASSUMPTION)."""
    if total_mw <= 0:
        raise ArithmeticError(f"SYSADQ_THERMAL_RANGE: {total_mw} <= 0")
    out: Dict[str, UnitGroupSpec] = {}
    for k in splits:
        if k < 1:
            raise ArithmeticError(f"SYSADQ_SPLIT_RANGE: {k} < 1")
        if total_mw / k <= 0:
            raise ArithmeticError("SYSADQ_SPLIT_CAPACITY")
        out[f"thermal_{k}x{total_mw / k:g}MW"] = UnitGroupSpec(
            name_prefix=f"TES-{k}u",
            n_units=k,
            unit_capacity_mw=total_mw / k,
            eford_d=eford_d,
            source_ref=source_ref,
            eford_source_ref=eford_source_ref,
            for_is_assumption=True,  # состав ТЭС не опубликован — всегда допущение
        )
    return out
