"""Rolling-origin бэктест месячного стока на реальных рядах (V9.2).

Первая верификация HydroForecast на измерительных данных (не синтетике):
месячный сток R-ArcticNET v4.0, створ Колыма — Усть-Среднекан (PointID 5858,
код Росгидромета 1010), 67 полных лет 1933-1999.

Прогноз — климатологический ансамбль по расширяющемуся окну СТРОГО из
прошлых лет (контроль утечки будущего — фирменный инвариант проекта):

    ensemble(y, m) = { Q(y', m) : y' < y,  y - y' <= window или все y' },
    |ensemble| >= min_history, иначе случай пропускается (fail-closed:
    прогноз не выдаётся без достаточной истории)

Базовые линии для сравнения:
    persistence:  Q(y, m) = Q(y-1, m)  (детерминированный)
    climatology-median: медиана того же окна

Метрики — существующие проверенные модули V9:
    mean_crps, pit_value, interval_coverage, rank_histogram
    (probabilistic_verification_v9), decompose_crps (crps_decomposition_v9).

Репозиторная культура fail-closed: модуль не сглаживает и не удаляет
пропуски молча; верифицируемая модель — базовая климатология, поэтому
результат подписывается benchmark_model="climatology", а зрелость
HydroForecast отдельно не повышается (см. docs/V92_REAL_DATA_BACKTEST_RU.md).
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from hydro_api.crps_decomposition_v9 import decompose_crps
from hydro_api.probabilistic_verification_v9 import (
    interval_coverage,
    mean_crps,
    pit_value,
    rank_histogram,
)

ENGINE_ID = "V9-MONTHLY-DISCHARGE-BACKTEST-1"

MonthlySeries = Dict[Tuple[int, int], float]  # (year, month) -> discharge m3/s


class BacktestCase(BaseModel):
    """Один прогноз-факт месячного стока."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    year: int
    month: int = Field(ge=1, le=12)
    obs_m3s: float = Field(ge=0)
    ensemble_m3s: List[float]
    persistence_m3s: float = Field(ge=0)


class BacktestReport(BaseModel):
    """Сводная верификация бэктеста."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    benchmark_model: str = "climatology"
    station: str
    years_backtested: List[int]
    n_cases: int
    min_history: int
    window_years: int  # 0 = расширяющееся окно (все прошлые годы)
    crps_climatology: float
    crps_persistence: float
    crps_skill_vs_persistence: float  # 1 - CRPS_clim/CRPS_pers; >0 = климатология лучше
    mae_climatology_median: float
    mae_persistence: float
    coverage_80: float
    coverage_95: float
    rank_histogram: List[int]
    pit_mean: float
    decomposition_reliability: float
    decomposition_resolution: float
    decomposition_uncertainty: float
    production_ready: bool = False


def climatology_ensemble(
    series: MonthlySeries,
    year: int,
    month: int,
    min_history: int = 10,
    window_years: int = 0,
) -> List[float]:
    """Ансамбль из прошлых значений того же месяца (строго year' < year).

    window_years > 0 ограничивает окно последними window_years годами.
    Недостаток истории — ValueError (fail-closed), а не тихий прогноз.
    """
    if not 1 <= month <= 12:
        raise ValueError(f"BACKTEST_MONTH_RANGE: месяц {month} вне 1..12")
    if min_history < 2:
        raise ValueError("BACKTEST_MIN_HISTORY: нужно хотя бы 2 члена ансамбля")
    hist = sorted(
        series[(y, month)]
        for y in range(year - 1, 0, -1)
        if (y, month) in series and (window_years <= 0 or year - y <= window_years)
    )
    if len(hist) < min_history:
        raise ValueError(
            f"BACKTEST_INSUFFICIENT_HISTORY: для {year}-{month:02d} доступно "
            f"{len(hist)} лет < min_history={min_history}")
    return hist


def run_monthly_backtest(
    series: MonthlySeries,
    station: str,
    year_start: int,
    year_end: int,
    min_history: int = 10,
    window_years: int = 0,
) -> BacktestReport:
    """Бэктест климатологического ансамбля на ряде месячного стока.

    Случаи с недостатком истории или без persistence-года пропускаются
    с подсчётом; пустой результат — ошибка.
    """
    if year_end < year_start:
        raise ValueError("BACKTEST_YEAR_RANGE: year_end < year_start")
    cases: List[BacktestCase] = []
    skipped_history = skipped_persistence = 0
    for y in range(year_start, year_end + 1):
        for m in range(1, 13):
            if (y, m) not in series:
                continue
            if (y - 1, m) not in series:
                skipped_persistence += 1
                continue
            try:
                ens = climatology_ensemble(series, y, m, min_history, window_years)
            except ValueError:
                skipped_history += 1
                continue
            cases.append(BacktestCase(
                year=y, month=m, obs_m3s=series[(y, m)],
                ensemble_m3s=ens, persistence_m3s=series[(y - 1, m)]))
    if not cases:
        raise ValueError(
            f"BACKTEST_NO_CASES: ни одного валидного случая "
            f"(skipped_history={skipped_history}, skipped_persistence={skipped_persistence})")
    sizes = {len(c.ensemble_m3s) for c in cases}
    if len(sizes) != 1:
        raise ValueError(
            f"BACKTEST_NONUNIFORM_ENSEMBLE: размеры ансамблей {sorted(sizes)} различаются; "
            "rank histogram и декомпозиция CRPS требуют единого m — "
            "задайте window_years == min_history (скользящее окно фиксированной длины)")

    ensembles = [c.ensemble_m3s for c in cases]
    obs = [c.obs_m3s for c in cases]
    pers = [c.persistence_m3s for c in cases]
    medians = [sorted(e)[len(e) // 2] if len(e) % 2 else
               0.5 * (sorted(e)[len(e) // 2 - 1] + sorted(e)[len(e) // 2])
               for e in ensembles]

    crps_clim = mean_crps(ensembles, obs)
    # детерминированный прогноз — вырожденный ансамбль из одного члена
    crps_pers = mean_crps([[p] for p in pers], obs)
    mae_med = sum(abs(m - o) for m, o in zip(medians, obs)) / len(cases)
    mae_pers = mean_crps([[p] for p in pers], obs)  # CRPS вырожденного = |ошибка|

    cov80 = interval_coverage(ensembles, obs, alpha=0.2)["empirical_coverage"]
    cov95 = interval_coverage(ensembles, obs, alpha=0.05)["empirical_coverage"]
    rh = rank_histogram(ensembles, obs)
    pit_mean = sum(pit_value(e, o) for e, o in zip(ensembles, obs)) / len(cases)
    dec = decompose_crps(ensembles, obs)

    return BacktestReport(
        station=station,
        years_backtested=sorted({c.year for c in cases}),
        n_cases=len(cases),
        min_history=min_history,
        window_years=window_years,
        crps_climatology=crps_clim,
        crps_persistence=crps_pers,
        crps_skill_vs_persistence=1.0 - crps_clim / crps_pers if crps_pers > 0 else 0.0,
        mae_climatology_median=mae_med,
        mae_persistence=mae_pers,
        coverage_80=cov80,
        coverage_95=cov95,
        rank_histogram=list(rh),
        pit_mean=pit_mean,
        decomposition_reliability=dec.reliability,
        decomposition_resolution=dec.resolution,
        decomposition_uncertainty=dec.uncertainty,
    )
