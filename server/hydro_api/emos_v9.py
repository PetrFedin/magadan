"""EMOS-постобработка климатологического ансамбля стока (V9.3).

ENGINE_ID: V9-EMOS-LOGNORMAL-CALIBRATION-1

Мотивация — результат бэктеста V9.2 на реальном ряде R-ArcticNET (створ 5858):
климатологический ансамбль дал хороший точечный скилл (+0,437 против
persistence), но систематически узкие интервалы (покрытие 80% = 0,614).
Классическое лекарство — EMOS (Ensemble Model Output Statistics,
Gneiting et al. 2005, 10.1175/MWR2904.1): диагностическая калибровка
предиктивного распределения по прошлым парам «ансамбль-наблюдение».

Модель: обмениваемые члены (климатология) => NGR-форма
    log Q ~ N(a + b * mean(log ens), sigma^2),  sigma^2 = c + d * var(log ens),
    c = exp(g0) > 0, d = exp(g1) > 0  (положительность конструктивно).
Логарифмирование — потому что сток положителен и правоскошен. Подгонка
минимизирует средний CRPS по обучающим парам в одной из двух постановок:
objective="log" (классический EMOS: замкнутая форма CRPS нормали в
лог-шкале) или objective="original_scale" (CRPS квантильного ансамбля
в м³/с — оптимизируется ровно метрика верификации; в V9.2 показано, что
лог-школьная цель может ухудшать CRPS исходной шкалы, поэтому обе
постановки верифицируются и отчитываются раздельно).
Предиктивный «ансамбль» — m квантилей логнормального
распределения на уровнях (i+0.5)/m: размер фиксирован, что сохраняет
совместимость с rank histogram и декомпозицией CRPS.

Причинность: fit_emos_log получает только пары прошлых лет (формирует
вызывающий код); внутри модуля обращения к «будущему» нет по построению.
Оптимизатор — собственный детерминированный Nelder-Mead (фиксированный
стартовый симплекс, коэффициенты 1/2/0.5/0.5): одинаковый вход даёт
бит-в-бит одинаковый результат; несходимость за лимит итераций —
fail-closed (EMOS_FIT_NOT_CONVERGED), а не тихий субоптимум.

Границы: EMOS исправляет калибровку, но не добавляет физики; это
постобработка базовой климатологии — зрелость HydroForecast не повышается.
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import List, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

ENGINE_ID = "V9-EMOS-LOGNORMAL-CALIBRATION-1"

_SQRT2PI = math.sqrt(2.0 * math.pi)
_INV_SQRT_PI = 1.0 / math.sqrt(math.pi)
_STD_NORMAL = NormalDist()

_MAX_ITER = 4000
_FTOL = 1e-10
_XTOL = 1e-8
_SIGMA_FLOOR = 1e-6  # защита от вырождения в лог-шкале


class EMOSFit(BaseModel):
    """Параметры EMOS (лог-нормальная NGR) с квитанцией подгонки."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    objective: str  # "log" (стандарт EMOS, CRPS в лог-шкале) | "original_scale"
    a: float
    b: float
    c: float = Field(gt=0)  # sigma^2 = c + d * var(log ens)
    d: float = Field(gt=0)
    n_pairs: int = Field(ge=2)
    train_mean_crps: float = Field(ge=0)  # средний CRPS в шкале цели
    converged: bool
    n_iterations: int = Field(ge=1)
    production_ready: bool = False


def gaussian_crps(mu: float, sigma: float, y: float) -> float:
    """Замкнутая форма CRPS нормального распределения (Gneiting et al. 2005).

    CRPS(N(mu, sigma^2), y) = sigma * [w (2 Phi(w) - 1) + 2 phi(w) - 1/sqrt(pi)],
    w = (y - mu) / sigma.
    """
    if not (math.isfinite(mu) and math.isfinite(y)):
        raise ValueError("EMOS_CRPS_NONFINITE")
    if not math.isfinite(sigma) or sigma <= 0.0:
        raise ValueError("EMOS_SIGMA_NONPOSITIVE")
    w = (y - mu) / sigma
    phi = math.exp(-0.5 * w * w) / _SQRT2PI
    return sigma * (w * (2.0 * _STD_NORMAL.cdf(w) - 1.0) + 2.0 * phi - _INV_SQRT_PI)


def _log_stats(ensemble: Sequence[float]) -> Tuple[float, float]:
    """Среднее и выборочная дисперсия логарифмов членов (все члены > 0)."""
    if len(ensemble) < 2:
        raise ValueError("EMOS_ENSEMBLE_TOO_SMALL: нужно >= 2 членов")
    logs = []
    for v in ensemble:
        if not math.isfinite(v) or v <= 0.0:
            raise ValueError("EMOS_NONPOSITIVE_DATA: лог-модель требует строго > 0")
        logs.append(math.log(v))
    m_bar = sum(logs) / len(logs)
    s2 = sum((x - m_bar) ** 2 for x in logs) / (len(logs) - 1)
    return m_bar, s2


def _nelder_mead(f, x0: List[float], max_iter: int = _MAX_ITER) -> Tuple[List[float], float, bool, int]:
    """Детерминированный Nelder-Mead (минимизация).

    Стартовый симплекс — координатный с шагом 5% от |x0| (или 0.05 для нуля).
    Стоп: разброс значений < FTOL и диаметр симплекса < XTOL, либо max_iter.
    """
    n = len(x0)
    simplex = [list(x0)]
    for i in range(n):
        p = list(x0)
        p[i] = p[i] + (0.05 * abs(p[i]) if p[i] != 0.0 else 0.05)
        simplex.append(p)
    vals = [f(p) for p in simplex]
    n_iter = 0
    converged = False
    while n_iter < max_iter:
        order = sorted(range(n + 1), key=lambda i: (vals[i], i))
        simplex = [simplex[i] for i in order]
        vals = [vals[i] for i in order]
        n_iter += 1
        spread_f = vals[-1] - vals[0]
        spread_x = max(
            abs(simplex[i][j] - simplex[0][j])
            for i in range(1, n + 1) for j in range(n)
        )
        if spread_f < _FTOL and spread_x < _XTOL:
            converged = True
            break
        centroid = [sum(simplex[i][j] for i in range(n)) / n for j in range(n)]
        worst = simplex[-1]
        reflected = [centroid[j] + (centroid[j] - worst[j]) for j in range(n)]
        f_ref = f(reflected)
        if vals[0] <= f_ref < vals[-2]:
            simplex[-1], vals[-1] = reflected, f_ref
            continue
        if f_ref < vals[0]:
            expanded = [centroid[j] + 2.0 * (reflected[j] - centroid[j]) for j in range(n)]
            f_exp = f(expanded)
            if f_exp < f_ref:
                simplex[-1], vals[-1] = expanded, f_exp
            else:
                simplex[-1], vals[-1] = reflected, f_ref
            continue
        contracted = [centroid[j] + 0.5 * (worst[j] - centroid[j]) for j in range(n)]
        f_con = f(contracted)
        if f_con < vals[-1]:
            simplex[-1], vals[-1] = contracted, f_con
            continue
        best = simplex[0]
        simplex = [best] + [
            [best[j] + 0.5 * (simplex[i][j] - best[j]) for j in range(n)]
            for i in range(1, n + 1)
        ]
        vals = [vals[0]] + [f(p) for p in simplex[1:]]
    return simplex[0], vals[0], converged, n_iter


def _quantiles_from_theta(theta: List[float], mb: float, s2: float, m: int) -> List[float]:
    """m равновероятных квантилей логнормали на исходной шкале (м³/с)."""
    a, b, g0, g1 = theta
    mu = a + b * mb
    sigma = math.sqrt(math.exp(g0) + math.exp(g1) * s2)
    dist = NormalDist(mu=mu, sigma=sigma)
    return [math.exp(dist.inv_cdf((i + 0.5) / m)) for i in range(m)]


def fit_emos_log(
    train_ensembles: Sequence[Sequence[float]],
    train_obs: Sequence[float],
    *,
    min_pairs: int = 10,
    max_iter: int = _MAX_ITER,
    objective: str = "log",
) -> EMOSFit:
    """CRPS-оптимальная подгонка EMOS по прошлым парам.

    objective="log" — классический EMOS: CRPS нормали в лог-шкале (замкнутая
    форма). objective="original_scale" — CRPS квантильного ансамбля на
    исходной шкале (м³/с): оптимизируется ровно та метрика, по которой
    ведётся верификация (дороже, но без сдвига цели преобразованием).

    Fail-closed: EMOS_INSUFFICIENT_PAIRS, EMOS_NONPOSITIVE_DATA,
    EMOS_UNKNOWN_OBJECTIVE, EMOS_FIT_NOT_CONVERGED.
    """
    if objective not in ("log", "original_scale"):
        raise ValueError(f"EMOS_UNKNOWN_OBJECTIVE: {objective!r}")
    if len(train_ensembles) != len(train_obs):
        raise ValueError("EMOS_ENSEMBLES_OBS_LENGTH_MISMATCH")
    if len(train_obs) < min_pairs:
        raise ValueError(
            f"EMOS_INSUFFICIENT_PAIRS: {len(train_obs)} < {min_pairs}")
    stats = [_log_stats(e) for e in train_ensembles]
    for o in train_obs:
        if not math.isfinite(o) or o <= 0.0:
            raise ValueError("EMOS_NONPOSITIVE_DATA: наблюдение должно быть > 0")
    y_log = [math.log(o) for o in train_obs]

    resid = [y - mb for y, (mb, _s2) in zip(y_log, stats)]
    res_var = sum(r * r for r in resid) / max(len(resid) - 1, 1)
    mean_s2 = sum(s2 for _mb, s2 in stats) / len(stats)
    c0 = max(0.5 * res_var, 1e-4)
    d0 = max(0.5 * res_var / mean_s2, 1e-4) if mean_s2 > 0 else 1e-4

    if objective == "log":
        def objective_fn(theta: List[float]) -> float:
            a, b, g0, g1 = theta
            c, d = math.exp(g0), math.exp(g1)
            total = 0.0
            for y, (mb, s2) in zip(y_log, stats):
                sigma2 = c + d * s2
                total += gaussian_crps(a + b * mb, math.sqrt(sigma2), y)
            return total / len(y_log)
    else:
        from hydro_api.probabilistic_verification_v9 import crps_ensemble

        def objective_fn(theta: List[float]) -> float:
            total = 0.0
            for o, (mb, s2) in zip(train_obs, stats):
                total += crps_ensemble(
                    _quantiles_from_theta(theta, mb, s2, 20), o)
            return total / len(train_obs)

    theta0 = [0.0, 1.0, math.log(c0), math.log(d0)]
    best, f_best, converged, n_iter = _nelder_mead(objective_fn, theta0, max_iter)
    if not converged:
        raise ArithmeticError(
            f"EMOS_FIT_NOT_CONVERGED: симплекс не сошёлся за {n_iter} итераций "
            f"(объектив {f_best:.6g})")
    a, b, g0, g1 = best
    return EMOSFit(
        objective=objective,
        a=a, b=b, c=math.exp(g0), d=math.exp(g1),
        n_pairs=len(train_obs), train_mean_crps=f_best,
        converged=True, n_iterations=n_iter,
    )


def emos_predictive_quantiles(
    fit: EMOSFit,
    ensemble: Sequence[float],
    *,
    m: int = 20,
) -> List[float]:
    """Предиктивный ансамбль: m квантилей логнормального распределения.

    Квантили на уровнях (i+0.5)/m (равновероятные члены, фиксированный
    размер ансамбля — совместимость с rank histogram / декомпозицией).
    """
    if m < 2:
        raise ValueError("EMOS_QUANTILE_COUNT: нужно m >= 2")
    mb, s2 = _log_stats(ensemble)
    mu = fit.a + fit.b * mb
    sigma = math.sqrt(fit.c + fit.d * s2)
    if sigma < _SIGMA_FLOOR:
        raise ArithmeticError("EMOS_PREDICTIVE_SIGMA_COLLAPSE")
    dist = NormalDist(mu=mu, sigma=sigma)
    return [math.exp(dist.inv_cdf((i + 0.5) / m)) for i in range(m)]
