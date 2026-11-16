"""Низководный (меженный) анализ стока: Q90/Q95 и тренды минимумов (V9.6).

ENGINE_ID: V9-LOWFLOW-FREQUENCY-1

Мотивация: гарантированная мощность ГЭС (Колымская 224 МВт,
Усть-Среднеканская 132 МВт — data/reference/kolyma_magadan_open_sources.json)
определяется низководным периодом. V9.5 показал, что зимний сток ниже
Колымской ГЭС сильно меняется после 1982 г. (регулирование). V9.6
количественно оценивает саму меженную гидрологию:

  * годовой минимум месячного стока (только полные годы, 12 месяцев);
  * минимум месячного стока зимней межени (дек—мар, только полные сезоны);
  * обеспеченные расходы Q80/Q90/Q95 (обеспеченность P% = расход,
    превышаемый в P% лет => квантиль непревышения 1-P/100 годового ряда
    минимумов) — ДВУМЯ независимыми оценками, без молчаливого усреднения:
      - эмпирическая квантиль (линейная интерполяция) + 95% ДИ
        непараметрическим бутстрепом по годам (B=2000, фиксированный seed,
        детерминированно и воспроизводимо);
      - логнормальная модель (MLE: mu, sigma по логарифмам, ddof=0),
        только если ВСЕ значения > 0; при нулевых расходах (замерзание)
        модель неприменима — поле None, а не тихая подмена;
  * тренды тех же рядов — через regional_trend_v9.trend_stats (V9.5);
  * разделение до/после 1982 г. для зарегулированных створов — в скрипте.

Fail-closed: n < MIN_YEARS_QUANTILE — ArithmeticError; 10 <= n < 20 —
оценка допускается с флагом small_sample=True (тренд при этом всё ещё
требует MIN_YEARS=20 из regional_trend_v9). Нефинитные значения —
ArithmeticError. production_ready=False всегда.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field
from statistics import NormalDist

ENGINE_ID = "V9-LOWFLOW-FREQUENCY-1"

MIN_YEARS_QUANTILE = 10     # минимум лет для эмпирической обеспеченности
SMALL_SAMPLE_YEARS = 20     # ниже — флаг small_sample (тренды запрещены)
BOOTSTRAP_REPS = 2000
BOOTSTRAP_SEED = 20261117   # фиксированный: воспроизводимость бит-в-бит

_STD = NormalDist()

MonthlySeries = Dict[Tuple[int, int], float]  # (year, month) -> м³/с


class LowFlowQuantileResult(BaseModel):
    """Квитанция одной обеспеченной оценки низководного ряда."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    target: str = Field(min_length=1)        # annual_min_monthly | winter_min_dec_mar
    exceedance_pct: float = Field(gt=0.0, lt=100.0)   # 80 | 90 | 95
    n_years: int = Field(ge=MIN_YEARS_QUANTILE)
    year_from: int
    year_to: int
    q_empirical_m3s: float = Field(ge=0.0)
    q_empirical_ci95_lo_m3s: float = Field(ge=0.0)
    q_empirical_ci95_hi_m3s: float = Field(ge=0.0)
    q_lognormal_m3s: Optional[float] = None   # None, если есть нули (модель неприменима)
    lognormal_applicable: bool
    small_sample: bool
    production_ready: bool = False


def annual_min_monthly(
    series: MonthlySeries,
    months: Optional[Sequence[int]] = None,
) -> Dict[int, float]:
    """Минимум месячного стока за год; учитываются только ПОЛНЫЕ годы.

    months=None — календарный год (12 месяцев); иначе заданный сезон
    (например, зимняя межень (12, 1, 2, 3)). Год с неполным набором месяцев
    отбрасывается целиком (никакой интерполяции пропусков).
    """
    use = tuple(range(1, 13)) if months is None else tuple(months)
    if not use:
        raise ArithmeticError("LOWFLOW_EMPTY_MONTHS")
    for m in use:
        if not (1 <= m <= 12):
            raise ArithmeticError(f"LOWFLOW_MONTH_RANGE: {m}")
    by_year: Dict[int, List[float]] = {}
    for (y, m), v in series.items():
        if m in use:
            if not math.isfinite(v) or v < 0:
                raise ArithmeticError(f"LOWFLOW_BAD_VALUE: {(y, m)}={v!r}")
            by_year.setdefault(y, []).append(v)
    return {y: min(vs) for y, vs in by_year.items() if len(vs) == len(use)}


def _quantile_sorted(xs: Sequence[float], q: float) -> float:
    """Линейная (numpy 'linear') квантиль отсортированного ряда, q in [0,1]."""
    if not xs:
        raise ArithmeticError("LOWFLOW_EMPTY_SAMPLE")
    if not (0.0 <= q <= 1.0):
        raise ArithmeticError(f"LOWFLOW_QUANTILE_RANGE: {q}")
    n = len(xs)
    if n == 1:
        return float(xs[0])
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    frac = pos - lo
    return float(xs[lo]) * (1.0 - frac) + float(xs[hi]) * frac


def _bootstrap_ci(
    vals: Sequence[float], q: float, reps: int, seed: int,
) -> Tuple[float, float]:
    """95% ДИ квантили непараметрическим бутстрепом по годам (детерминир.)."""
    rng = random.Random(seed)
    n = len(vals)
    estimates = []
    for _ in range(reps):
        sample = sorted(vals[rng.randrange(n)] for _ in range(n))
        estimates.append(_quantile_sorted(sample, q))
    estimates.sort()
    return (_quantile_sorted(estimates, 0.025),
            _quantile_sorted(estimates, 0.975))


def _lognormal_quantile(vals: Sequence[float], q: float) -> Optional[float]:
    """Q по логнормальной MLE-модели; None, если есть неположительные значения."""
    if any(v <= 0 for v in vals):
        return None
    logs = [math.log(v) for v in vals]
    n = len(logs)
    mu = sum(logs) / n
    var = sum((x - mu) ** 2 for x in logs) / n   # MLE, ddof=0
    if var == 0.0:
        raise ArithmeticError("LOWFLOW_LOGNORMAL_DEGENERATE: sigma=0")
    return math.exp(mu + _STD.inv_cdf(q) * math.sqrt(var))


def quantile_stats(
    values_by_year: Dict[int, float],
    *,
    target: str,
    exceedance_pct: float,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> LowFlowQuantileResult:
    """Обеспеченный расход Q(P%) с ДИ по ряду годовых минимумов.

    exceedance_pct=90 => квантиль непревышения 0,10 ряда минимумов.
    """
    if not target:
        raise ArithmeticError("LOWFLOW_NO_TARGET")
    if not (0.0 < exceedance_pct < 100.0):
        raise ArithmeticError(f"LOWFLOW_EXCEEDANCE_RANGE: {exceedance_pct}")
    pairs = sorted(
        (y, v) for y, v in values_by_year.items()
        if (year_from is None or y >= year_from)
        and (year_to is None or y <= year_to))
    n = len(pairs)
    if n < MIN_YEARS_QUANTILE:
        raise ArithmeticError(
            f"LOWFLOW_INSUFFICIENT_YEARS: n={n} < {MIN_YEARS_QUANTILE} "
            f"(target={target})")
    vals = [v for _, v in pairs]
    for v in vals:
        if not math.isfinite(v) or v < 0:
            raise ArithmeticError(f"LOWFLOW_BAD_VALUE: {v!r}")
    q = 1.0 - exceedance_pct / 100.0
    svals = sorted(vals)
    q_emp = _quantile_sorted(svals, q)
    ci_lo, ci_hi = _bootstrap_ci(vals, q, BOOTSTRAP_REPS, BOOTSTRAP_SEED)
    q_ln = _lognormal_quantile(vals, q)
    return LowFlowQuantileResult(
        target=target,
        exceedance_pct=exceedance_pct,
        n_years=n,
        year_from=int(pairs[0][0]), year_to=int(pairs[-1][0]),
        q_empirical_m3s=q_emp,
        q_empirical_ci95_lo_m3s=ci_lo,
        q_empirical_ci95_hi_m3s=ci_hi,
        q_lognormal_m3s=q_ln,
        lognormal_applicable=q_ln is not None,
        small_sample=n < SMALL_SAMPLE_YEARS,
    )
