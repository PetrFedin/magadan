"""Надёжность гидроагрегатов: ISO 20816-5 зоны вибрации, Вейбулл MLE,
ожидаемые потери от отказа (V9, P1-4).

Три блока:

1. ISO 20816-5 (машинные установки гидроэлектростанций): классификация
   зон вибрации A/B/C/D по размаху (или СКЗ) вибрации с конфигурируемыми
   границами. Зоны: A — новый агрегат, B — длительная эксплуатация,
   C — ограниченная эксплуатация, D — опасность повреждения.
   Границы по умолчанию НЕ заданы числами из стандарта (стандарт
   платный, числа зависят от типа машины и точки измерения) — их
   обязан задать пользователь из сертифицированных таблиц ISO 20816-5
   для конкретного типа агрегата. fail-closed: без границ модуль
   отказывается классифицировать.

2. Weibull 2-параметрический MLE с правым цензурированием:
   f(t) = (β/η)(t/η)^(β-1) exp(-(t/η)^β)
   LogLik = Σ_events [ln β - β ln η + (β-1) ln t] - Σ_all (t/η)^β
   Профильный метод: η̂(β) в замкнутом виде, скалярное score-уравнение
   по β решается Ньютоном с бисекционной страховкой; g'(β) ≤ 0
   (Коши-Буняковский) — корень единствен, сходимость гарантирована.

3. E[C] = P(fail in horizon) * Loss + C_preventive — ожидаемые затраты
   стратегии. P(fail) считается из подогнанного Вейбулла. Пока модель
   не откалибрована на натурных отказах (probability_calibrated=False),
   инвестиционное решение принудительно HOLD (культура репозитория).

Ссылки: ISO 20816-5:2018; Abernethy, "The New Weibull Handbook" (2006);
IEC 62023 (структурирование надёжности ГЭС как ориентир).
"""
from __future__ import annotations

import math
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ENGINE_ID = "V9-TURBINE-RELIABILITY-1"


# ---------------------------------------------------------------- ISO 20816
class VibrationZones(BaseModel):
    """Границы зон A/B, B/C, C/D (в единицах измерения сигнала).

    Числа обязан задать пользователь из ISO 20816-5 для конкретного
    типа машины/точки измерения — модуль принципиально не содержит
    "типовых" значений, чтобы исключить ложную сертификацию.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    ab: float = Field(gt=0)
    bc: float = Field(gt=0)
    cd: float = Field(gt=0)
    unit: str = Field(min_length=1, description="напр. mm/s RMS или mm peak-to-peak")

    @model_validator(mode="after")
    def _ordered(self) -> "VibrationZones":
        if not (self.ab < self.bc < self.cd):
            raise ValueError(
                "ZONE_BOUNDARIES_MUST_BE_STRICTLY_INCREASING: "
                f"A/B={self.ab}, B/C={self.bc}, C/D={self.cd}"
            )
        return self


def classify_vibration(value: float, zones: VibrationZones) -> str:
    """Классификация вибрации в зону A/B/C/D."""
    v = float(value)
    if not math.isfinite(v) or v < 0:
        raise ValueError("VIBRATION_VALUE_MUST_BE_FINITE_NONNEGATIVE")
    if v <= zones.ab:
        return "A"
    if v <= zones.bc:
        return "B"
    if v <= zones.cd:
        return "C"
    return "D"


ZONE_ACTION = {
    "A": "новый/переведённый агрегат; эксплуатация без ограничений",
    "B": "длительная эксплуатация допустима",
    "C": "эксплуатация ограниченное время; планировать ремонт",
    "D": "опасность повреждения; немедленная остановка по регламенту",
}


# ------------------------------------------------------------------ Weibull
class WeibullFit(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    beta: float = Field(gt=0, description="параметр формы")
    eta_hours: float = Field(gt=0, description="характеристическое время, ч")
    n_events: int = Field(ge=1)
    n_censored: int = Field(ge=0)
    log_likelihood: float
    mle_iterations: int = Field(ge=1)
    source_id: str = "SYNTHETIC-RELIABILITY-V9"
    calibrated_on_field_failures: bool = False
    production_ready: bool = False

    def cdf(self, t_hours: float) -> float:
        """F(t) = 1 - exp(-(t/η)^β)."""
        if t_hours <= 0:
            return 0.0
        return 1.0 - math.exp(-((t_hours / self.eta_hours) ** self.beta))

    def reliability(self, t_hours: float) -> float:
        """R(t) = 1 - F(t)."""
        return 1.0 - self.cdf(t_hours)


def fit_weibull_mle(
    durations_hours: Sequence[float],
    *,
    censored: Sequence[bool] | None = None,
    tol: float = 1e-10,
    max_iter: int = 200,
) -> WeibullFit:
    """2-параметрический Вейбулл MLE с правым цензурированием.

    Профильный метод: при фиксированном β масштаб имеет замкнутый вид
        η̂(β) = (Σ_all t^β / r)^(1/β),   r — число нецензурированных событий.
    Подстановка в score-уравнение по β даёт скалярное уравнение
        g(β) = 1/β + mean_e(ln t) − Σ t^β ln t / Σ t^β = 0,
    причём g'(β) = −1/β² − Var_w(ln t) ≤ 0 (Коши-Буняковский), т.е. g
    строго убывает и корень единствен. Решается Ньютоном с бисекционной
    страховкой — гарантированная сходимость в отличие от 2D-Ньютона.
    """
    times = [float(t) for t in durations_hours]
    if not times:
        raise ValueError("WEIBULL_NO_DATA")
    if any((not math.isfinite(t)) or t <= 0 for t in times):
        raise ValueError("WEIBULL_TIMES_MUST_BE_POSITIVE_FINITE")
    if censored is None:
        censored = [False] * len(times)
    censored = [bool(c) for c in censored]
    if len(censored) != len(times):
        raise ValueError("WEIBULL_CENSORING_LENGTH_MISMATCH")
    n = len(times)
    n_events = sum(1 for c in censored if not c)
    if n_events == 0:
        raise ValueError("WEIBULL_NO_UNCENSORED_EVENTS")
    # Масштабирование: g(β) инвариантна к замене t -> t/c, поэтому
    # считаем в единицах c = геометрическое среднее — защита от overflow
    # при больших β и от underflow при малых.
    ln_t_raw = [math.log(t) for t in times]
    ln_c = sum(ln_t_raw) / n
    scale = math.exp(ln_c)
    ln_t = [lt - ln_c for lt in ln_t_raw]
    mean_ln_events = sum(lt for lt, c in zip(ln_t, censored) if not c) / n_events

    def _g(beta: float):
        """g(beta), g'(beta) и ln S0 в отнормированных единицах.

        Веса w_i = t_i^β = exp(β ln t_i) считаются в лог-домене с
        вычитанием максимума — отношения S1/S0, S2/S0 инвариантны к
        общему множителю, а overflow исключён при любом β.
        ln S0 возвращается для восстановления η.
        """
        lw = [beta * lt for lt in ln_t]
        m = max(lw)
        w = [math.exp(v - m) for v in lw]
        s0 = sum(w)
        s1 = sum(wi * lt for wi, lt in zip(w, ln_t))
        s2 = sum(wi * lt * lt for wi, lt in zip(w, ln_t))
        g = 1.0 / beta + mean_ln_events - s1 / s0
        var_w = s2 / s0 - (s1 / s0) ** 2
        dg = -1.0 / (beta * beta) - var_w
        ln_s0 = m + math.log(s0)
        return g, dg, ln_s0

    # Старт: метод моментов по ln t нецензурированных
    ev_ln = [lt for lt, c in zip(ln_t, censored) if not c]
    var_ln = sum((v - mean_ln_events) ** 2 for v in ev_ln) / max(n_events - 1, 1)
    beta = max(math.pi / math.sqrt(6.0 * max(var_ln, 1e-6)), 0.05)

    # Бисекционный кронштейн с расширением: g(β->0) -> +inf, g(β->inf) < 0
    lo, hi = 1e-3, 1e3
    g_lo, _, _ = _g(lo)
    g_hi, _, _ = _g(hi)
    for _ in range(20):
        if g_lo > 0 and g_hi < 0:
            break
        if g_lo <= 0:
            hi = lo
            lo /= 10.0
            g_lo, _, _ = _g(lo)
        else:
            lo = hi
            hi *= 10.0
            g_hi, _, _ = _g(hi)
    else:
        raise ArithmeticError("WEIBULL_BRACKET_FAILED")

    it = 0
    for it in range(1, max_iter + 1):
        g, dg, _ = _g(beta)
        if abs(g) < tol:
            break
        # Ньютон со страховкой кронштейном
        candidate = beta - g / dg
        if not (lo < candidate < hi):
            candidate = 0.5 * (lo + hi)
        if g > 0:
            lo = beta
        else:
            hi = beta
        if abs(candidate - beta) < tol * max(beta, 1.0):
            beta = candidate
            break
        beta = candidate
    else:
        raise ArithmeticError(f"WEIBULL_MLE_NOT_CONVERGED in {max_iter} iterations")

    _, _, ln_s0 = _g(beta)
    eta = scale * math.exp((ln_s0 - math.log(n_events)) / beta)
    # Итоговый logLik в точке MLE
    log_lik = 0.0
    for t, c in zip(times, censored):
        z = (t / eta) ** beta
        if c:
            log_lik -= z
        else:
            log_lik += math.log(beta / eta) + (beta - 1.0) * math.log(t / eta) - z
    return WeibullFit(
        beta=beta,
        eta_hours=eta,
        n_events=n_events,
        n_censored=n - n_events,
        log_likelihood=log_lik,
        mle_iterations=it,
    )


# ------------------------------------------------------------------- E[C]
class MaintenanceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    horizon_hours: float = Field(gt=0)
    p_failure_in_horizon: float = Field(ge=0, le=1)
    expected_cost_run_to_failure: float = Field(ge=0)
    preventive_cost: float = Field(ge=0)
    decision: str
    probability_calibrated: bool = False
    production_ready: bool = False


def maintenance_economics(
    fit: WeibullFit,
    *,
    horizon_hours: float,
    failure_loss_rub: float,
    preventive_cost_rub: float,
) -> MaintenanceDecision:
    """E[C] стратегии 'работа до отказа' за горизонт против превентивной.

    E[C_run] = P(T < horizon) * Loss; решение PREVENTIVE, если
    E[C_run] > C_prev. Пока модель не калибрована на натурных отказах,
    решение принудительно HOLD (fail-closed).
    """
    if horizon_hours <= 0 or failure_loss_rub < 0 or preventive_cost_rub < 0:
        raise ValueError("ECON_ARGS_INVALID")
    p = fit.cdf(horizon_hours)
    e_run = p * failure_loss_rub
    if not fit.calibrated_on_field_failures:
        decision = "HOLD"
    else:
        decision = "PREVENTIVE" if e_run > preventive_cost_rub else "RUN_TO_FAILURE"
    return MaintenanceDecision(
        horizon_hours=horizon_hours,
        p_failure_in_horizon=p,
        expected_cost_run_to_failure=e_run,
        preventive_cost=preventive_cost_rub,
        decision=decision,
        probability_calibrated=fit.calibrated_on_field_failures,
    )
