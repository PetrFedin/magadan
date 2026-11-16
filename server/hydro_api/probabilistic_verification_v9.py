"""Вероятностная верификация ансамблевых прогнозов стока (V9, P0-2).

Закрывает пробел из аудита: точечные метрики (NSE/KGE по WMO-1364) уже
есть, но для вероятностных прогнозов (split-conformal, ансамбли) нужны
собственные метрики:

  * CRPS (continuous ranked probability score) — строгий proper score
    для ансамбля (форма энергетического скора):
        CRPS = (1/m) Σ|x_i - y| - 1/(2m²) ΣΣ|x_i - x_j|
  * PIT (probability integral transform) — значение эмпирической CDF
    ансамбля в точке наблюдения; у калиброванного прогноза PIT ~ U(0,1);
  * покрытие интервалов (empirical coverage vs nominal);
  * rank histogram — гистограмма рангов наблюдения среди членов ансамбля
    (n+1 корзин для n членов); плоская гистограмма = калиброванность.

Ссылки: Gneiting & Raftery (2007) JASA 102:359-378; Hersbach (2000)
MWR 128:2636-2648 (декомпозиция CRPS для ансамбля); WMO-1364 (2021).

Все функции — чистые, без IO; fail-closed на пустые/нефинитные входы.
"""
from __future__ import annotations

import math
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

ENGINE_ID = "V9-PROBABILISTIC-VERIFICATION-1"


def _validate_ensemble(ensemble: Sequence[float]) -> list[float]:
    members = [float(v) for v in ensemble]
    if not members:
        raise ValueError("ENSEMBLE_EMPTY")
    if any(not math.isfinite(v) for v in members):
        raise ValueError("ENSEMBLE_NONFINITE")
    return members


def _validate_obs(obs: float) -> float:
    y = float(obs)
    if not math.isfinite(y):
        raise ValueError("OBSERVATION_NONFINITE")
    return y


def crps_ensemble(ensemble: Sequence[float], obs: float) -> float:
    """CRPS ансамбля относительно наблюдения (эд. форма, точная).

    CRPS = E|X - y| - 1/2 E|X - X'|  (Gneiting & Raftery 2007, eq. 21)
    Для m членов: mean|x_i - y| - (1/(2m^2)) sum_{i,j}|x_i - x_j|.
    """
    members = _validate_ensemble(ensemble)
    y = _validate_obs(obs)
    m = len(members)
    term1 = sum(abs(x - y) for x in members) / m
    term2 = 0.0
    for xi in members:
        for xj in members:
            term2 += abs(xi - xj)
    term2 /= 2.0 * m * m
    return term1 - term2


def pit_value(ensemble: Sequence[float], obs: float) -> float:
    """PIT-значение: эмпирическая CDF ансамбля в точке наблюдения.

    Используется randomization-free вариант Hersbach (2000):
    доля членов < y, плюс половина доли равных y. Область [0, 1].
    """
    members = _validate_ensemble(ensemble)
    y = _validate_obs(obs)
    m = len(members)
    below = sum(1 for x in members if x < y)
    equal = sum(1 for x in members if x == y)
    return (below + 0.5 * equal) / m


def interval_coverage(
    ensembles: Sequence[Sequence[float]],
    observations: Sequence[float],
    *,
    alpha: float = 0.1,
) -> dict:
    """Эмпирическое покрытие центрального (1-alpha)-интервала.

    Интервал — перцентили ансамбля [alpha/2, 1-alpha/2].
    Возвращает номинал, факт, дефицит и число случаев.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("ALPHA_MUST_BE_IN_(0,1)")
    if len(ensembles) != len(observations):
        raise ValueError("ENSEMBLES_OBS_LENGTH_MISMATCH")
    if not ensembles:
        raise ValueError("ENSEMBLES_EMPTY")

    hits = 0
    for ens, obs in zip(ensembles, observations):
        members = sorted(_validate_ensemble(ens))
        y = _validate_obs(obs)
        lo = _percentile(members, 100.0 * alpha / 2.0)
        hi = _percentile(members, 100.0 * (1.0 - alpha / 2.0))
        if lo <= y <= hi:
            hits += 1
    n = len(ensembles)
    nominal = 1.0 - alpha
    empirical = hits / n
    return {
        "n_cases": n,
        "nominal_coverage": nominal,
        "empirical_coverage": empirical,
        "coverage_deficit": nominal - empirical,
    }


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    """Линейная интерполяция перцентиля по отсортированным значениям."""
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    rank = pct / 100.0 * (n - 1)
    lo = int(math.floor(rank))
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return float(sorted_values[lo]) * (1.0 - frac) + float(sorted_values[hi]) * frac


def rank_histogram(
    ensembles: Sequence[Sequence[float]],
    observations: Sequence[float],
) -> list[int]:
    """Гистограмма рангов наблюдения среди членов ансамбля (m+1 корзин).

    Корзина k = число случаев, где ровно k членов ансамбля < наблюдения.
    Плоская гистограмма — признак калиброванности; U-форма — недооценка
    дисперсии; купол — переоценка.
    """
    if len(ensembles) != len(observations):
        raise ValueError("ENSEMBLES_OBS_LENGTH_MISMATCH")
    if not ensembles:
        raise ValueError("ENSEMBLES_EMPTY")
    m = len(ensembles[0])
    if m == 0:
        raise ValueError("ENSEMBLE_EMPTY")
    counts = [0] * (m + 1)
    for ens, obs in zip(ensembles, observations):
        members = _validate_ensemble(ens)
        if len(members) != m:
            raise ValueError("ENSEMBLE_SIZE_INCONSISTENT")
        y = _validate_obs(obs)
        rank = sum(1 for x in members if x < y)
        counts[rank] += 1
    return counts


def mean_crps(ensembles: Sequence[Sequence[float]],
              observations: Sequence[float]) -> float:
    """Средний CRPS по выборке (скилл-метрика ансамбля)."""
    if len(ensembles) != len(observations):
        raise ValueError("ENSEMBLES_OBS_LENGTH_MISMATCH")
    if not ensembles:
        raise ValueError("ENSEMBLES_EMPTY")
    return sum(crps_ensemble(e, o) for e, o in zip(ensembles, observations)) / len(ensembles)


class VerificationReport(BaseModel):
    """Сводный отчёт вероятностной верификации (fail-closed по умолчанию)."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    n_cases: int = Field(ge=1)
    mean_crps: float = Field(ge=0)
    coverage_90: dict
    coverage_50: dict
    rank_histogram: list[int]
    pit_mean: float = Field(ge=0, le=1)
    pit_uniformity_note: str
    source_id: str = "SYNTHETIC-VERIFICATION-V9"
    verified_on_observed_data: bool = False
    production_ready: bool = False


def build_verification_report(
    ensembles: Sequence[Sequence[float]],
    observations: Sequence[float],
) -> VerificationReport:
    """Полный отчёт: CRPS, покрытие 50/90%, rank histogram, PIT."""
    if len(ensembles) != len(observations):
        raise ValueError("ENSEMBLES_OBS_LENGTH_MISMATCH")
    if not ensembles:
        raise ValueError("ENSEMBLES_EMPTY")
    pits = [pit_value(e, o) for e, o in zip(ensembles, observations)]
    pit_mean = sum(pits) / len(pits)
    note = (
        "PIT mean 0.5 при калиброванном ансамбле; смещение к 0/1 — "
        "систематическая ошибка; тест однородности (Anderson-Darling) "
        "рекомендуется на n >= 100 случаях"
    )
    return VerificationReport(
        n_cases=len(ensembles),
        mean_crps=mean_crps(ensembles, observations),
        coverage_90=interval_coverage(ensembles, observations, alpha=0.1),
        coverage_50=interval_coverage(ensembles, observations, alpha=0.5),
        rank_histogram=rank_histogram(ensembles, observations),
        pit_mean=pit_mean,
        pit_uniformity_note=note,
    )
