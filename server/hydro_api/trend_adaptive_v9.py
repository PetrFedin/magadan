"""Тренд-адаптивный климатологический ансамбль стока (V9.4).

ENGINE_ID: V9-TREND-ADAPTIVE-CLIMATOLOGY-1

Мотивация — диагноз V9.3 на реальном ряде R-ArcticNET (створ 5858):
EMOS-калибровка устранила смещение положения (PIT 0,657 -> 0,482), но не
смогла довести покрытие до номинала: скользящее 20-летнее окно в условиях
нестационарного стока структурно отстаёт от текущего уровня. Дисперсионная
калибровка информацию о тренде добавить не может — нужен ансамбль,
который сам переносит уровень.

Модель (всё в лог-шкале, сток положителен и правоскошен):

1. В окне лет [Y-W, Y-1] месяца m оценивается тренд log Q по году
   Тейлом—Сеном (медиана попарных наклонов): робастно к выбросам,
   без распределительных предположений, полностью детерминировано.
2. Уровень переносится на целевой год: level_Y = b0 + b1*(Y - y_bar),
   где b0 — медиана (logQ_i - b1*(y_i - y_bar)).
3. Аномалии a_i = logQ_i - (b0 + b1*(y_i - y_bar)) сохраняются как
   непараметрическая часть ансамбля (форма распределения — из данных).
4. Инфляция дисперсии от неопределённости переноса тренда: доверительный
   интервал Сена (1968) для наклона через дисперсию статистики Кендалла
   S: Var(S) = n(n-1)(2n+5)/18; полуширина ДИ -> se(b1);
   v = (se(b1) * (Y - y_bar))^2 — чем дальше перенос за центр окна,
   тем шире предиктивное распределение. Это принципиально отличает модель
   от «детрендированной климатологии»: дисперсия растёт с горизонтом
   экстраполяции, что и требуется для покрытия на нестационарном ряде.
5. Предиктивное распределение — смесь N(level_Y + a_i, v) по i;
   ансамбль — m равновероятных квантилей смеси (уровни (i+0.5)/m),
   детерминированная бисекция. Фиксированный размер сохраняет
   совместимость с rank histogram и декомпозицией CRPS.

Причинность: используются только годы < Y (формирует вызывающий код и
окно внутри функции); утечки будущего нет по построению.

Fail-closed: недостаток истории, неположительные данные, вырожденные
параметры — ArithmeticError, тихого прогноза нет.

Граница честности: это всё ещё климатология (без физического драйвера);
если тренд в окне ломается, перенос уровня ошибается вместе с ним —
поэтому модуль верифицируется строгим бэктестом (scripts/
trend_adaptive_backtest_rarcticnet.py), а не декларируется.
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import Dict, List, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

ENGINE_ID = "V9-TREND-ADAPTIVE-CLIMATOLOGY-1"

MonthlySeries = Dict[Tuple[int, int], float]  # (year, month) -> discharge m3/s

_STD = NormalDist()
_Z_975 = 1.959963984540054  # квантиль 0.975 N(0,1) — для ДИ Сена 95%
_BISECT_ITERS = 80          # 2^-80 от стартового интервала — избыточно точно


class TrendFit(BaseModel):
    """Квитанция тренд-адаптивного переноса для одного (year, month)."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    year: int
    month: int = Field(ge=1, le=12)
    window_years: int = Field(ge=2)
    n_years: int = Field(ge=2)
    slope_log_per_year: float          # наклон Тейла—Сена, log(м³/с)/год
    slope_ci95_lo: float
    slope_ci95_hi: float
    level_at_target: float             # перенесённый уровень в лог-шкале
    pred_var_log: float = Field(ge=0)  # инфляция от неопределённости тренда
    production_ready: bool = False


def _theil_sen_ci(x: Sequence[float], y: Sequence[float]) -> Tuple[float, float, float, int]:
    """Наклон Тейла—Сена и ДИ 95% Сена (1968) через статистику Кендалла S.

    Возвращает (slope, ci_lo, ci_hi, n_pairs). ДИ — из порядковых
    статистик попарных наклонов: M1 = (N - C)/2, M2 = (N + C)/2,
    C = z_0.975 * sqrt(Var(S)), Var(S) = n(n-1)(2n+5)/18 (без связок;
    месячный сток — непрерывная величина, связки не ожидаются, а при
    вырождении N_pairs == 0 — fail-closed снаружи).
    """
    n = len(x)
    slopes: List[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            dx = x[j] - x[i]
            if dx != 0.0:
                slopes.append((y[j] - y[i]) / dx)
    if not slopes:
        raise ArithmeticError("TREND_NO_PAIRWISE_SLOPES: все x совпадают")
    slopes.sort()
    n_pairs = len(slopes)
    slope = slopes[n_pairs // 2] if n_pairs % 2 else 0.5 * (slopes[n_pairs // 2 - 1] + slopes[n_pairs // 2])
    var_s = n * (n - 1) * (2 * n + 5) / 18.0
    c = _Z_975 * math.sqrt(var_s)
    m1 = max(0, int(math.floor((n_pairs - c) / 2.0)))
    m2 = min(n_pairs - 1, int(math.ceil((n_pairs + c) / 2.0)) - 1)
    if m1 > m2:
        m1, m2 = 0, n_pairs - 1  # вырожденный малый n: ДИ = весь размах наклонов
    return slope, slopes[m1], slopes[m2], n_pairs


def theil_sen_ci(x: Sequence[float], y: Sequence[float]) -> Tuple[float, float, float, int]:
    """Публичная обёртка ДИ Тейла—Сена (для регионального анализа V9.5).

    Семантика и детерминизм идентичны _theil_sen_ci; вынесена в публичный
    API, чтобы модули-«потребители» не импортировали приватное имя.
    """
    return _theil_sen_ci(x, y)


def _mixture_cdf(z: float, means: Sequence[float], sd: float) -> float:
    return sum(_STD.cdf((z - mu) / sd) for mu in means) / len(means)


def _empirical_quantile(sorted_vals: Sequence[float], p: float) -> float:
    """Квантиль эмпирического распределения (линейная интерполяция, тип 7)."""
    n = len(sorted_vals)
    h = p * (n - 1)
    lo = int(math.floor(h))
    hi = min(lo + 1, n - 1)
    frac = h - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def trend_adaptive_ensemble(
    series: MonthlySeries,
    year: int,
    month: int,
    *,
    min_history: int = 20,
    window_years: int = 20,
    m: int = 20,
) -> Tuple[List[float], TrendFit]:
    """Тренд-адаптивный ансамбль для (year, month) из окна строго прошлых лет.

    Возвращает (ансамбль из m членов, м³/с, отсортированный; квитанцию).
    """
    if not 1 <= month <= 12:
        raise ArithmeticError(f"TREND_MONTH_RANGE: месяц {month} вне 1..12")
    if window_years < 2 or min_history < 2 or min_history > window_years:
        raise ArithmeticError("TREND_WINDOW_CONFIG: нужно 2 <= min_history <= window_years")
    if m < 2:
        raise ArithmeticError("TREND_ENSEMBLE_SIZE: нужно m >= 2")
    ys = [y for y in range(year - window_years, year) if (y, month) in series]
    if len(ys) < min_history:
        raise ArithmeticError(
            f"TREND_INSUFFICIENT_HISTORY: для {year}-{month:02d} доступно "
            f"{len(ys)} лет окна < min_history={min_history}")
    vals = []
    for y in ys:
        v = series[(y, month)]
        if not math.isfinite(v) or v <= 0.0:
            raise ArithmeticError(f"TREND_NONPOSITIVE_DATA: Q({y},{month})={v}")
        vals.append(math.log(v))
    x = [float(y) for y in ys]
    x_bar = sum(x) / len(x)
    xc = [v - x_bar for v in x]

    slope, ci_lo, ci_hi, _ = _theil_sen_ci(x, vals)
    srt = sorted(vals[i] - slope * xc[i] for i in range(len(ys)))
    n_ = len(srt)
    b0 = srt[n_ // 2] if n_ % 2 else 0.5 * (srt[n_ // 2 - 1] + srt[n_ // 2])
    offset = float(year) - x_bar  # перенос за центр окна
    level_y = b0 + slope * offset
    anomalies = sorted(vals[i] - (b0 + slope * xc[i]) for i in range(len(ys)))

    se_slope = (ci_hi - ci_lo) / (2.0 * _Z_975)
    pred_var = (se_slope * offset) ** 2
    means = [level_y + a for a in anomalies]

    ens: List[float] = []
    if pred_var <= 0.0:
        # вырожденная неопределённость тренда: чистая детрендированная климатология
        ens = [math.exp(_empirical_quantile(means, (i + 0.5) / m)) for i in range(m)]
    else:
        sd = math.sqrt(pred_var)
        lo = means[0] - 12.0 * sd
        hi = means[-1] + 12.0 * sd
        for i in range(m):
            p = (i + 0.5) / m
            a_, b_ = lo, hi
            for _ in range(_BISECT_ITERS):
                mid = 0.5 * (a_ + b_)
                if _mixture_cdf(mid, means, sd) < p:
                    a_ = mid
                else:
                    b_ = mid
            ens.append(math.exp(0.5 * (a_ + b_)))
    if any(not math.isfinite(v) or v <= 0.0 for v in ens):
        raise ArithmeticError("TREND_ENSEMBLE_DEGENERATE: неположительный член ансамбля")
    return ens, TrendFit(
        year=year, month=month, window_years=window_years, n_years=len(ys),
        slope_log_per_year=slope, slope_ci95_lo=ci_lo, slope_ci95_hi=ci_hi,
        level_at_target=level_y, pred_var_log=pred_var)
