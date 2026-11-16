"""Muskingum / Muskingum-Cunge flood routing (V9, P0-3).

Русловая трансформация стока методом Маскингама и его физически
обоснованной вариацией Маскингама-Кунджа (Cunge, 1969; Ponce, 1989).

Уравнение водного баланса пруда/участка:
    dS/dt = I - O,   S = K * (X*I + (1-X)*O)

Рекуррентная схема:
    O_t = C0*I_t + C1*I_{t-1} + C2*O_{t-1}
    C0 = (dt - 2KX) / D
    C1 = (dt + 2KX) / D
    C2 = (2K(1-X) - dt) / D
    D  = 2K(1-X) + dt

Классическая область неотрицательных коэффициентов:
    2KX <= dt <= 2K(1-X)

Метод Маскингама-Кунджа задаёт K и X из гидравлики канала (Понс):
    K = dx / c_k
    X = 0.5 * (1 - Q / (B * S0 * c_k * dx))
где c_k = (5/3) * V — кинематическая скорость (Мэннинг), B — ширина
по верху, S0 — уклон дна, dx — длина участка, Q — реперный расход.

Репозиторная культура fail-closed: отрицательные коэффициенты и
нарушение баланса массы выше допуска — ошибка, а не предупреждение.
Модуль не верифицирован на натурных паводках (production_ready=False);
все данные, проходящие через него, должны быть SYNTHETIC-*.
"""
from __future__ import annotations

import math
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ENGINE_ID = "V9-MUSKINGUM-CUNGE-ROUTING-1"
COEF_SUM_TOL = 1e-9
MASS_BALANCE_REL_TOL = 1e-9


class MuskingumParams(BaseModel):
    """Классические параметры Маскингама."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    k_hours: float = Field(gt=0, description="Время добегания участка, ч")
    x: float = Field(ge=0.0, le=0.5, description="Весовой коэффициент (0..0.5)")
    dt_hours: float = Field(gt=0, description="Шаг расчёта, ч")

    @model_validator(mode="after")
    def _nonnegative_coefficients(self) -> "MuskingumParams":
        c0, c1, c2 = muskingum_coefficients(self.k_hours, self.x, self.dt_hours)
        if min(c0, c1, c2) < -COEF_SUM_TOL:
            dt_lo = 2.0 * self.k_hours * self.x
            dt_hi = 2.0 * self.k_hours * (1.0 - self.x)
            raise ValueError(
                "MUSKINGUM_NEGATIVE_COEFFICIENT: dt вне классической области "
                "неотрицательных коэффициентов "
                f"[2KX; 2K(1-X)] = [{dt_lo:.4g}; {dt_hi:.4g}] ч "
                f"(C0={c0:.6g}, C1={c1:.6g}, C2={c2:.6g}); "
                "измените dt в допустимый диапазон или пересчитайте K/X"
            )
        return self


def muskingum_coefficients(k_hours: float, x: float, dt_hours: float) -> tuple[float, float, float]:
    """C0, C1, C2 рекуррентной схемы Маскингама."""
    d = 2.0 * k_hours * (1.0 - x) + dt_hours
    c0 = (dt_hours - 2.0 * k_hours * x) / d
    c1 = (dt_hours + 2.0 * k_hours * x) / d
    c2 = (2.0 * k_hours * (1.0 - x) - dt_hours) / d
    return c0, c1, c2


def muskingum_cunge_params(
    *,
    reach_length_m: float,
    reference_discharge_m3s: float,
    channel_width_m: float,
    bed_slope: float,
    manning_n: float,
    dt_hours: float,
) -> MuskingumParams:
    """Вывод K и X из гидравлики канала (Cunge 1969, параметризация Понса).

    Глубина и скорость по Мэннингу для широкого канала (h << B):
        Q = (1/n) * B * h^(5/3) * S0^(1/2)
        V = Q / (B*h),   c_k = (5/3)*V
        K = dx / c_k
        X = 0.5 * (1 - Q / (B * S0 * c_k * dx))
    """
    if reach_length_m <= 0 or channel_width_m <= 0 or manning_n <= 0:
        raise ValueError("MC_POSITIVE_GEOMETRY_REQUIRED")
    if bed_slope <= 0:
        raise ValueError("MC_POSITIVE_SLOPE_REQUIRED")
    if reference_discharge_m3s <= 0:
        raise ValueError("MC_POSITIVE_REFERENCE_DISCHARGE_REQUIRED")

    # h из формулы Мэннинга (широкий канал): h = (Q*n / (B*sqrt(S0)))^(3/5)
    h = (reference_discharge_m3s * manning_n / (channel_width_m * math.sqrt(bed_slope))) ** (3.0 / 5.0)
    v = reference_discharge_m3s / (channel_width_m * h)
    c_k = (5.0 / 3.0) * v
    k_hours = reach_length_m / c_k / 3600.0
    x = 0.5 * (1.0 - reference_discharge_m3s / (channel_width_m * bed_slope * c_k * reach_length_m))
    x = min(max(x, 0.0), 0.5)  # физическая область Маскингама
    dt_lo = 2.0 * k_hours * x
    dt_hi = 2.0 * k_hours * (1.0 - x)
    if not (dt_lo - 1e-12 <= dt_hours <= dt_hi + 1e-12):
        raise ValueError(
            "MC_DT_OUTSIDE_CLASSICAL_BAND: для выведенных "
            f"K={k_hours:.4g} ч и X={x:.4g} классическая область "
            f"dt in [{dt_lo:.4g}; {dt_hi:.4g}] ч; передан dt={dt_hours:.4g} ч. "
            "Возьмите dt из диапазона или разбейте участок на подучастки "
            "(уменьшение reach_length_m сдвигает диапазон вниз)"
        )
    return MuskingumParams(k_hours=k_hours, x=x, dt_hours=dt_hours)


class RoutingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    outflow_m3s: list[float]
    coefficients: dict[str, float]
    inflow_volume_m3: float
    outflow_volume_m3: float
    mass_balance_rel_error: float
    peak_inflow_m3s: float
    peak_outflow_m3s: float
    peak_lag_steps: int
    source_id: str = "SYNTHETIC-ROUTING-V9"
    benchmarked_against_reference_solution: bool = False
    production_ready: bool = False


def route_muskingum(
    inflow_m3s: Sequence[float],
    params: MuskingumParams,
    *,
    initial_outflow_m3s: float | None = None,
) -> RoutingResult:
    """Трансформация входного гидрографа по рекуррентной схеме.

    initial_outflow_m3s=None => стационарное начало O_0 = I_0.
    """
    if len(inflow_m3s) < 2:
        raise ValueError("ROUTING_MIN_LENGTH_2")
    inflow = [float(v) for v in inflow_m3s]
    if any((not math.isfinite(v)) or v < 0 for v in inflow):
        raise ValueError("ROUTING_INFLOW_MUST_BE_FINITE_NONNEGATIVE")

    c0, c1, c2 = muskingum_coefficients(params.k_hours, params.x, params.dt_hours)
    if abs(c0 + c1 + c2 - 1.0) > COEF_SUM_TOL:
        raise ArithmeticError("MUSKINGUM_COEFFICIENT_SUM_NOT_1")

    out = [float(initial_outflow_m3s) if initial_outflow_m3s is not None else inflow[0]]
    for t in range(1, len(inflow)):
        out.append(c0 * inflow[t] + c1 * inflow[t - 1] + c2 * out[t - 1])

    dt_s = params.dt_hours * 3600.0
    # Баланс массы по трапециям
    vin = sum(0.5 * (inflow[t] + inflow[t - 1]) for t in range(1, len(inflow))) * dt_s
    vout = sum(0.5 * (out[t] + out[t - 1]) for t in range(1, len(out))) * dt_s
    denom = max(vin, 1e-12)
    rel_err = abs(vin - vout) / denom
    # В конце гидрографа вода ещё может быть "в пути" (S_end != S_start) —
    # допускаем расхождение, пропорциональное запасу в створе.
    stored_rel = abs(params.k_hours * 3600.0 *
                     ((params.x * inflow[-1] + (1 - params.x) * out[-1])
                      - (params.x * inflow[0] + (1 - params.x) * out[0]))) / denom
    if rel_err - stored_rel > MASS_BALANCE_REL_TOL:
        raise ArithmeticError(
            f"ROUTING_MASS_BALANCE_VIOLATION: rel_err={rel_err:.3e}, "
            f"storage_term={stored_rel:.3e}"
        )

    peak_in = max(range(len(inflow)), key=lambda i: inflow[i])
    peak_out = max(range(len(out)), key=lambda i: out[i])
    return RoutingResult(
        outflow_m3s=out,
        coefficients={"C0": c0, "C1": c1, "C2": c2},
        inflow_volume_m3=vin,
        outflow_volume_m3=vout,
        mass_balance_rel_error=rel_err,
        peak_inflow_m3s=inflow[peak_in],
        peak_outflow_m3s=out[peak_out],
        peak_lag_steps=peak_out - peak_in,
    )
