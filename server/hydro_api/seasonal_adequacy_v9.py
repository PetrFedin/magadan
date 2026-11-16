"""Сезонная адекватность: зимнее ограничение ГЭС гарантированной мощностью (V9.6).

ENGINE_ID: V9-SEASONAL-ADEQUACY-1

Продолжение V9.5 (system_adequacy_v9). Там все агрегаты каскада считались
доступными на полной установленной мощности круглый год — это годовая
(безразмерно-летняя) оценка. Но в низководный зимний период гидрологически
обеспеченная мощность ГЭС — ГАРАНТИРОВАННАЯ мощность: Колымская 224 МВт
из 900, Усть-Среднеканская 132 МВт из 570 (source_ref в
data/reference/kolyma_magadan_open_sources.json). Для изолированной
системы с зимним пиком нагрузки это может качественно изменить выводы.

Модель (планировочное ПРИБЛИЖЕНИЕ, все допущения помечены):
  * гарантированная мощность ГЭС распределяется пропорционально по всем
    агрегатам станции (дерейтинг unit_capacity *= guaranteed/installed);
    COPT-свёртка adequacy_v9 сохраняет структуру (двухсостоятельные
    агрегаты с EFORd-приором GADS hydro 5,43 %);
  * это НЕ оперативная модель: энергетические ограничения (запас
    водохранилища) COPT не учитывает; гарантированная мощность —
    долговременная низководная планировочная характеристика, а не
    суточная доступность агрегатов;
  * нагрузка — константа на уровне пика (консервативная верхняя оценка
    LOLE/EENS, как в V9.5);
  * натурной статистики отказов нет => for_is_assumption=True => HOLD.

Fail-closed: дерейтинг вне (0; installed] — ArithmeticError; пустые
группы/неверный сезон — ArithmeticError. production_ready=False всегда.
"""
from __future__ import annotations

from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from hydro_api.system_adequacy_v9 import (
    UnitGroupSpec,
    evaluate_system,
)

ENGINE_ID = "V9-SEASONAL-ADEQUACY-1"

SEASONS = ("annual_full_capacity", "winter_guaranteed_capacity")


class SeasonalScenarioResult(BaseModel):
    """Квитанция сезонного сценария адекватности."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    scenario: str = Field(min_length=1)
    season: str = Field(min_length=1)
    hydro_available_mw: float = Field(ge=0.0)
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


def derate_group(spec: UnitGroupSpec, available_capacity_mw: float) -> UnitGroupSpec:
    """Дерейтинг группы агрегатов до гарантированной мощности станции.

    available_capacity_mw — гарантированная мощность СТАНЦИИ (суммарная по
    группе), МВт. Каждый агрегат масштабируется пропорционально:
    unit_capacity *= available / installed. EFORd и прочие поля сохраняются.
    """
    installed = spec.n_units * spec.unit_capacity_mw
    if available_capacity_mw <= 0:
        raise ArithmeticError(
            f"SEASONAL_DERATE_RANGE: available={available_capacity_mw} <= 0")
    if available_capacity_mw > installed + 1e-9:
        raise ArithmeticError(
            f"SEASONAL_DERATE_ABOVE_INSTALLED: available={available_capacity_mw} "
            f"> installed={installed}")
    scale = available_capacity_mw / installed
    return spec.model_copy(update={
        "name_prefix": spec.name_prefix + "-winter",
        "unit_capacity_mw": spec.unit_capacity_mw * scale,
    })


def evaluate_season(
    scenario: str,
    season: str,
    groups: Sequence[UnitGroupSpec],
    peak_load_mw: float,
    *,
    hours_per_year: float = 8760.0,
) -> SeasonalScenarioResult:
    """LOLE/EENS/N-1 сезонного сценария при постоянной нагрузке на пике."""
    if season not in SEASONS:
        raise ArithmeticError(f"SEASONAL_UNKNOWN_SEASON: {season!r}")
    res = evaluate_system(scenario, groups, peak_load_mw,
                          hours_per_year=hours_per_year)
    hydro_available = sum(
        g.n_units * g.unit_capacity_mw for g in groups
        if g.name_prefix.startswith(("KolymskayaHPP", "UstSrednekanHPP")))
    return SeasonalScenarioResult(
        scenario=res.scenario,
        season=season,
        hydro_available_mw=hydro_available,
        units_count=res.units_count,
        installed_capacity_mw=res.installed_capacity_mw,
        peak_load_mw=res.peak_load_mw,
        lole_hours_per_year=res.lole_hours_per_year,
        eens_mwh_per_year=res.eens_mwh_per_year,
        lolp_at_peak=res.lolp_at_peak,
        n_minus_1_secure=res.n_minus_1_secure,
        n_minus_1_margin_mw=res.n_minus_1_margin_mw,
        for_assumption=res.for_assumption,
        decision=res.decision,
    )
