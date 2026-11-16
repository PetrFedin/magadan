"""V9.2 — ретроспективная проверка (бэктест) месячных прогнозов стока.

ENGINE_ID: V9-MONTHLY-DISCHARGE-BACKTEST-1

Методология: rolling-origin evaluation со строго причинной (causal) информацией.
Для каждого года Y и месяца M ансамбль строится только по годам < Y
(климатология в скользящем окне либо по всей доступной истории). Базовый
прогноз (baseline) — персистентность: значение того же месяца годом ранее.

Инварианты и ограничения:
  - утечка будущего запрещена: climatology_ensemble() использует только годы < year;
  - размер ансамбля обязан быть одинаковым для всех случаев бэктеста
    (иначе ранговая гистограмма и декомпозиция CRPS некорректны) —
    гарантируется соглашением window_years == min_history;
  - разрывы ряда не интерполируются: случаи без значения или без истории
    пропускаются; если случаев нет вовсе — fail-closed (BACKTEST_NO_CASES);
  - метрики — только верифицированные модули V9 (ensemble_crps,
    interval_coverage, rank_histogram, Murphy-декомпозиция V9.1).

Класс данных: FIELD-OBSERVED-PUBLISHED (публичные наблюдённые ряды, не
телеметрия владельца). Результаты бэктеста — исследовательские, статус
production_ready платформы не меняется.
"""

from __future__ import annotations

import bisect
from typing import Dict, List, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from hydro_api.ensemble_v9 import ensemble_crps, interval_coverage, rank_histogram
from hydro_api.crps_decomposition_v9 import decompose_crps

ENGINE_ID = "V9-MONTHLY-DISCHARGE-BACKTEST-1"


class BacktestCase(BaseModel):
    """Один случай ретроспективного прогноза."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    year: int
    month: int = Field(ge=1, le=12)
    observation: float = Field(ge=0.0)
    ensemble: List[float]
    persistence: float = Field(ge=0.0)


class BacktestReport(BaseModel):
    """Сводный отчёт бэктеста. Все метрики — только по реально оценённым случаям."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine_id: str = ENGINE_ID
    station: str
    year_start: int
    year_end: int
    cases_evaluated: int = Field(ge=0)
    cases_skipped_no_data: int = Field(ge=0)
    cases_skipped_no_history: int = Field(ge=0)
    ensemble_size: int = Field(ge=1)
    crps_climatology: float
    crps_persistence: float
    crps_skill_vs_persistence: float  # 1 - CRPS_clim/CRPS_pers; >0 — клим. лучше
    mae_climatology: float  # MAE медианы ансамбля
    mae_persistence: float
    coverage_80: float  # эмпирическое покрытие 80% ПИ (номинал 0.80)
    coverage_95: float  # эмпирическое покрытие 95% ПИ (номинал 0.95)
    rank_histogram: List[int]
    pit_mean: float  # среднее ранг/(m+1); для калиброванного ансамбля ~0.5
    decomposition: Dict[str, float]  # reliability / resolution / uncertainty / mean_crps
    production_ready: bool = False


def climatology_ensemble(
    series: Dict[Tuple[int, int], float],
    year: int,
    month: int,
    *,
    min_history: int = 10,
    window_years: int = 0,
) -> List[float]:
    """Климатологический ансамбль для (year, month) строго по годам < year.

    series: {(год, месяц): расход}. window_years=0 — вся доступная история,
    иначе скользящее окно из window_years лет, непосредственно предшествующих
    году прогноза. Требуется не менее min_history членов.
    """
    if month < 1 or month > 12:
        raise ValueError("BACKTEST_MONTH_RANGE: месяц вне 1..12")
    if min_history < 2:
        raise ValueError("BACKTEST_MIN_HISTORY: min_history должен быть >= 2")
    if window_years < 0:
        raise ValueError("BACKTEST_WINDOW_RANGE: window_years должен быть >= 0")

    members: List[float] = []
    y = year - 1
    while y >= 1 and (window_years == 0 or y >= year - window_years):
        v = series.get((y, month))
        if v is not None:
            members.append(v)
        y -= 1

    if len(members) < min_history:
        raise ValueError(
            "BACKTEST_INSUFFICIENT_HISTORY: членов %d < min_history %d"
            % (len(members), min_history)
        )
    return members


def run_monthly_backtest(
    series: Dict[Tuple[int, int], float],
    *,
    station: str,
    year_start: int,
    year_end: int,
    min_history: int = 10,
    window_years: int = 0,
) -> BacktestReport:
    """Rolling-origin бэктест месячного стока за годы [year_start, year_end].

    Fail-closed:
      - BACKTEST_NONUNIFORM_ENSEMBLE — если размер ансамбля не одинаков
        для всех оценённых случаев (ранговая верификация невозможна);
      - BACKTEST_NO_CASES — если ни одного оценённого случая.
    """
    if year_end < year_start:
        raise ValueError("BACKTEST_YEAR_RANGE: year_end < year_start")

    cases: List[BacktestCase] = []
    skipped_no_data = 0
    skipped_no_history = 0

    for year in range(year_start, year_end + 1):
        for month in range(1, 13):
            obs = series.get((year, month))
            pers = series.get((year - 1, month))
            if obs is None or pers is None:
                skipped_no_data += 1
                continue
            try:
                ens = climatology_ensemble(
                    series, year, month,
                    min_history=min_history, window_years=window_years,
                )
            except ValueError:
                skipped_no_history += 1
                continue
            cases.append(
                BacktestCase(
                    year=year, month=month, observation=obs,
                    ensemble=ens, persistence=pers,
                )
            )

    if not cases:
        raise ArithmeticError(
            "BACKTEST_NO_CASES: ни одного случая с наблюдением, персистентностью "
            "и достаточной историей"
        )

    sizes = {len(c.ensemble) for c in cases}
    if len(sizes) != 1:
        raise ArithmeticError(
            "BACKTEST_NONUNIFORM_ENSEMBLE: размер ансамбля различается между "
            "случаями (%s); задайте window_years == min_history" % sorted(sizes)
        )
    m = sizes.pop()

    ensembles = [c.ensemble for c in cases]
    observations = [c.observation for c in cases]
    persist_members = [[c.persistence] for c in cases]

    crps_clim = ensemble_crps(ensembles, observations)
    crps_pers = ensemble_crps(persist_members, observations)

    med = [sorted(e)[len(e) // 2] if len(e) % 2 == 1 else
           0.5 * (sorted(e)[len(e) // 2 - 1] + sorted(e)[len(e) // 2])
           for e in ensembles]
    mae_clim = sum(abs(a - b) for a, b in zip(med, observations)) / len(cases)
    mae_pers = sum(abs(c.persistence - c.observation) for c in cases) / len(cases)

    cov80 = interval_coverage(ensembles, observations, alpha=0.2)["empirical_coverage"]
    cov95 = interval_coverage(ensembles, observations, alpha=0.05)["empirical_coverage"]

    ranks = rank_histogram(ensembles, observations)
    pit_mean = sum(
        (bisect.bisect_left(sorted(c.ensemble), c.observation)) / (m + 1)
        for c in cases
    ) / len(cases)

    dec = decompose_crps(ensembles, observations)

    return BacktestReport(
        station=station,
        year_start=year_start,
        year_end=year_end,
        cases_evaluated=len(cases),
        cases_skipped_no_data=skipped_no_data,
        cases_skipped_no_history=skipped_no_history,
        ensemble_size=m,
        crps_climatology=crps_clim["mean_crps"],
        crps_persistence=crps_pers["mean_crps"],
        crps_skill_vs_persistence=1.0 - crps_clim["mean_crps"] / crps_pers["mean_crps"],
        mae_climatology=mae_clim,
        mae_persistence=mae_pers,
        coverage_80=cov80,
        coverage_95=cov95,
        rank_histogram=list(ranks["bin_counts"]),
        pit_mean=pit_mean,
        decomposition={
            "reliability": dec["reliability"],
            "resolution": dec["resolution"],
            "uncertainty": dec["uncertainty"],
            "mean_crps": dec["mean_crps"],
        },
    )
