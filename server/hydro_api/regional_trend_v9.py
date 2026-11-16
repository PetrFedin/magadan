"""Региональный тренд-анализ стока: Манн—Кендалл + Тейл—Сен (V9.5).

ENGINE_ID: V9-REGIONAL-TREND-ANALYSIS-1

Мотивация — честная оговорка V9.4: наклоны скользящего окна на одном
створе (5858, Усть-Среднекан) нельзя обобщать на бассейн. V9.5 переносит
тренд-диагностику на все створы Колымы из R-ArcticNET v4.0 с длинными
полными рядами и разделяет две гипотезы зимнего роста стока:

  H1 (климат): рост зимнего базового стока в криолитозоне — тогда
      положительный зимний тренд должен виден и на НЕрегулируемых
      притоках;
  H2 (регулирование): створы 5858/5951 ниже Колымской ГЭС (первый
      постоянный агрегат — июнь 1982, наполнение водохранилища с
      октября 1980; source_ref в data/reference) получают зимние
      попуски ГЭС — «тренд» может быть антропогенным.

Различение: сравнение знака/значимости трендов по группам створов
(regulated_below_dam / not_below_dam) и по подпериоду до 1982 г.

Методы (всё непараметрическое, детерминированное, без сторонних библиотек):
  * тест Манна—Кендалла (Kendall 1975): S, tie-corrected
    Var(S) = [n(n-1)(2n+5) - sum_g t_g(t_g-1)(2t_g+5)] / 18,
    Z с поправкой на непрерывность, двусторонний p из N(0,1);
  * наклон Тейла—Сена + ДИ Сена (1968) — через публичный
    trend_adaptive_v9.theil_sen_ci (лог-шкала; наклон в %/год — 100*(exp(b)-1)).

Fail-closed: малый ряд (n < MIN_YEARS), вырожденные данные, нулевая
дисперсия S — ArithmeticError; тихих оценок нет.
"""
from __future__ import annotations

import math
from collections import Counter
from statistics import NormalDist
from typing import Dict, List, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from hydro_api.trend_adaptive_v9 import theil_sen_ci

ENGINE_ID = "V9-REGIONAL-TREND-ANALYSIS-1"

MIN_YEARS = 20          # минимальная длина ряда для тренд-оценки
WINTER_MONTHS = (12, 1, 2, 3)   # зимняя межень: декабрь—март

_STD = NormalDist()

# Год начала регулирующего влияния Колымской ГЭС на нижние створы:
# наполнение водохранилища с 18.10.1980, первый постоянный агрегат — июнь
# 1982 (повторный пуск; формальный пуск 24.02.1981 аннулирован).
# Источник: SRC-WIKIPEDIA-KOLYMA-HPP / SRC-HYDROPOWER-RU
# (data/reference/kolyma_magadan_open_sources.json).
KOLYMSKY_HPP_REGULATION_ONSET_YEAR = 1982

MonthlySeries = Dict[Tuple[int, int], float]  # (year, month) -> discharge m3/s


class MannKendallResult(BaseModel):
    """Квитанция теста Манна—Кендалла."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    n: int = Field(ge=MIN_YEARS)
    s: int                          # статистика Кендалла S
    var_s: float = Field(gt=0)      # tie-corrected Var(S)
    z: float                        # с поправкой на непрерывность
    p_two_sided: float = Field(ge=0.0, le=1.0)
    tie_groups: int = Field(ge=0)
    significant_5pct: bool
    production_ready: bool = False


class StationTrend(BaseModel):
    """Тренд-оценка одного ряда (одного створа, одной цели)."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    target: str = Field(min_length=1)       # 'annual' | 'winter_dec_mar' | ...
    year_from: int
    year_to: int
    n_years: int = Field(ge=MIN_YEARS)
    slope_log_per_year: float               # наклон Тейла—Сена, log(м³/с)/год
    slope_pct_per_year: float               # 100*(exp(b)-1)
    slope_ci95_lo_pct: float
    slope_ci95_hi_pct: float
    mk_z: float
    mk_p_two_sided: float = Field(ge=0.0, le=1.0)
    mk_significant_5pct: bool
    production_ready: bool = False


def mann_kendall(values: Sequence[float]) -> MannKendallResult:
    """Тест Манна—Кендалла с поправкой на связки (Kendall 1975)."""
    x = [float(v) for v in values]
    n = len(x)
    if n < MIN_YEARS:
        raise ArithmeticError(
            f"MK_INSUFFICIENT_YEARS: n={n} < {MIN_YEARS}")
    for v in x:
        if not math.isfinite(v):
            raise ArithmeticError(f"MK_NONFINITE_VALUE: {v!r}")
    s = 0
    for i in range(n):
        for j in range(i + 1, n):
            d = x[j] - x[i]
            if d > 0:
                s += 1
            elif d < 0:
                s -= 1
    counts = Counter(x)
    tie_groups = sum(1 for c in counts.values() if c > 1)
    var_s = (n * (n - 1) * (2 * n + 5)
             - sum(c * (c - 1) * (2 * c + 5) for c in counts.values() if c > 1)) / 18.0
    if var_s <= 0:
        raise ArithmeticError("MK_ZERO_VARIANCE: ряд вырожден (все значения равны)")
    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0
    p = 2.0 * (1.0 - _STD.cdf(abs(z)))
    return MannKendallResult(
        n=n, s=s, var_s=var_s, z=z, p_two_sided=p,
        tie_groups=tie_groups, significant_5pct=p < 0.05)


def seasonal_annual_means(
    series: MonthlySeries,
    months: Sequence[int],
) -> Dict[int, float]:
    """Среднее по заданным месяцам для каждого года, где ВСЕ месяцы есть."""
    if not months:
        raise ArithmeticError("SEASON_EMPTY_MONTHS")
    for m in months:
        if not (1 <= m <= 12):
            raise ArithmeticError(f"SEASON_MONTH_RANGE: {m}")
    by_year: Dict[int, List[float]] = {}
    for (y, m), v in series.items():
        if m in months:
            by_year.setdefault(y, []).append(v)
    return {y: sum(vs) / len(vs) for y, vs in by_year.items()
            if len(vs) == len(months)}


def trend_stats(
    values_by_year: Dict[int, float],
    *,
    target: str,
    year_from: int | None = None,
    year_to: int | None = None,
    min_years: int = MIN_YEARS,
) -> StationTrend:
    """Тренд-оценка (Тейл—Сен в лог-шкале + Манн—Кендалл) одного ряда."""
    if min_years < MIN_YEARS:
        raise ArithmeticError(
            f"TREND_STATS_MIN_YEARS: min_years={min_years} < {MIN_YEARS}")
    pairs = sorted(
        (y, v) for y, v in values_by_year.items()
        if (year_from is None or y >= year_from)
        and (year_to is None or y <= year_to)
        and v > 0 and math.isfinite(v))
    if len(pairs) < min_years:
        raise ArithmeticError(
            f"TREND_STATS_INSUFFICIENT: {len(pairs)} лет < {min_years} "
            f"(target={target})")
    years = [float(y) for y, _ in pairs]
    logs = [math.log(v) for _, v in pairs]
    slope, ci_lo, ci_hi, _ = theil_sen_ci(years, logs)
    mk = mann_kendall([v for _, v in pairs])
    return StationTrend(
        target=target,
        year_from=int(pairs[0][0]), year_to=int(pairs[-1][0]),
        n_years=len(pairs),
        slope_log_per_year=slope,
        slope_pct_per_year=100.0 * (math.exp(slope) - 1.0),
        slope_ci95_lo_pct=100.0 * (math.exp(ci_lo) - 1.0),
        slope_ci95_hi_pct=100.0 * (math.exp(ci_hi) - 1.0),
        mk_z=mk.z, mk_p_two_sided=mk.p_two_sided,
        mk_significant_5pct=mk.significant_5pct)
