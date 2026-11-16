"""Degree-day модель снегонакопления и снеготаяния (V9, углубление P1).

Генератор притока талых вод для HydroForecast: преобразует ряды
температуры и осадков (например, ERA5-Land после загрузки владельцем)
в высвобождение воды из снежного покрова. Классическая схема
degree-day (HBV; Hock, 2003; Martinec & Rango, 1986):

    Фаза осадков (линейный переход в полосе 2h вокруг t0):
        f_snow = clip((t0 + h - T) / (2h), 0, 1)
    Таяние:
        M = DDF * max(0, T - T_melt),  ограничено запасом SWE
    Жидкая влага в покрове (ведёрко с удерживающей способностью):
        L += rain + M
        release = max(0, L - f_hold * SWE)
        L -= release
    Обратное замерзание при T < T_melt:
        F = min(L, c_refreeze * DDF * (T_melt - T))
        SWE += F;  L -= F

Баланс воды по каждому прогону:
    sum(P) == sum(release) + SWE_end + L_end   (с допуском 1e-9)

Репозиторная культура fail-closed: параметры по умолчанию являются
литературным стартовым диапазоном, НЕ калибровкой по створам Колымы
(calibrated=False => decision=HOLD). Климатические якоря Магадана
см. data/reference/kolyma_magadan_open_sources.json
(класс OPEN-PUBLISHED-REFERENCE).
"""
from __future__ import annotations

from typing import List, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENGINE_ID = "V9-DEGREE-DAY-SNOWMELT-1"
WATER_BALANCE_TOL = 1e-9


class SnowmeltParams(BaseModel):
    """Параметры degree-day модели снежного покрова."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    ddf_mm_per_deg_day: float = Field(
        gt=0, le=20.0,
        description="Degree-day фактор таяния, мм/(°C·сут). Литературный диапазон для открытой тайги ~2-6.")
    melt_threshold_c: float = Field(
        default=0.0, ge=-5.0, le=5.0,
        description="Порог начала таяния, °C")
    partition_threshold_c: float = Field(
        default=0.0, ge=-5.0, le=5.0,
        description="Центр полосы разделения дождь/снег, °C")
    partition_halfwidth_c: float = Field(
        default=1.0, gt=0, le=5.0,
        description="Полуширина линейного перехода дождь/снег, °C")
    liquid_holding_fraction: float = Field(
        default=0.1, ge=0.0, le=0.5,
        description="Удерживающая способность покрова, доля от SWE")
    refreeze_coeff: float = Field(
        default=0.05, ge=0.0, le=1.0,
        description="Доля потенциального degree-day холода, идущая на обратное замерзание жидкой влаги")
    calibrated: bool = Field(
        default=False,
        description="True только после калибровки на натурных створах; по умолчанию False => HOLD")
    params_source: str = Field(
        default="SYNTHETIC-LITERATURE-DEFAULT",
        min_length=10,
        description="Источник параметров: SYNTHETIC-* либо ссылка на OPEN-PUBLISHED-*")


class SnowmeltResult(BaseModel):
    """Результат прогона снежной модели."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    n_steps: int
    swe_mm: List[float]
    liquid_mm: List[float]
    melt_mm: List[float]
    release_mm: List[float]
    total_precip_mm: float
    total_release_mm: float
    water_balance_residual_mm: float
    calibrated: bool
    decision: str  # HOLD, если параметры не калиброваны
    production_ready: bool = False


def snow_fraction(t_air_c: float, t0_c: float, halfwidth_c: float) -> float:
    """Доля снега в осадках при температуре T (линейный переход)."""
    if halfwidth_c <= 0:
        raise ValueError("SNOWMELT_PARTITION_WIDTH: полуширина перехода должна быть > 0")
    frac = (t0_c + halfwidth_c - t_air_c) / (2.0 * halfwidth_c)
    return min(1.0, max(0.0, frac))


def run_snowmelt(
    temp_c: Sequence[float],
    precip_mm: Sequence[float],
    params: SnowmeltParams,
    initial_swe_mm: float = 0.0,
    initial_liquid_mm: float = 0.0,
) -> SnowmeltResult:
    """Посуточный (или пошаговый) прогон degree-day модели.

    Входы: ряды температуры (°C) и осадков (мм/шаг) одинаковой длины.
    Выход: ряды SWE, жидкой влаги, таяния и высвобождения воды.
    """
    n = len(temp_c)
    if n == 0:
        raise ValueError("SNOWMELT_EMPTY_INPUT: пустой ряд температуры")
    if len(precip_mm) != n:
        raise ValueError(
            f"SNOWMELT_LENGTH_MISMATCH: temp={n}, precip={len(precip_mm)}")
    if initial_swe_mm < 0 or initial_liquid_mm < 0:
        raise ValueError("SNOWMELT_NEGATIVE_INITIAL: начальные запасы не могут быть отрицательными")

    swe = float(initial_swe_mm)
    liquid = float(initial_liquid_mm)
    swe_out: List[float] = []
    liquid_out: List[float] = []
    melt_out: List[float] = []
    release_out: List[float] = []
    total_p = 0.0
    total_release = 0.0

    for t, p in zip(temp_c, precip_mm):
        if p < 0:
            raise ValueError(f"SNOWMELT_NEGATIVE_PRECIP: осадки {p} мм < 0")
        total_p += p

        f_snow = snow_fraction(t, params.partition_threshold_c, params.partition_halfwidth_c)
        snowfall = f_snow * p
        rainfall = p - snowfall
        swe += snowfall

        melt = min(params.ddf_mm_per_deg_day * max(0.0, t - params.melt_threshold_c), swe)
        swe -= melt

        liquid += rainfall + melt
        capacity = params.liquid_holding_fraction * swe
        release = max(0.0, liquid - capacity)
        liquid -= release

        if t < params.melt_threshold_c and liquid > 0.0:
            cold_content = params.refreeze_coeff * params.ddf_mm_per_deg_day * (params.melt_threshold_c - t)
            frozen = min(liquid, cold_content)
            swe += frozen
            liquid -= frozen

        total_release += release
        swe_out.append(swe)
        liquid_out.append(liquid)
        melt_out.append(melt)
        release_out.append(release)

    residual = total_p + initial_swe_mm + initial_liquid_mm - total_release - swe - liquid
    if abs(residual) > WATER_BALANCE_TOL * max(1.0, total_p):
        raise ArithmeticError(
            f"SNOWMELT_WATER_BALANCE_VIOLATION: residual={residual:.6g} мм")

    return SnowmeltResult(
        n_steps=n,
        swe_mm=swe_out,
        liquid_mm=liquid_out,
        melt_mm=melt_out,
        release_mm=release_out,
        total_precip_mm=total_p,
        total_release_mm=total_release,
        water_balance_residual_mm=residual,
        calibrated=params.calibrated,
        decision="CALIBRATED-REVIEW" if params.calibrated else "HOLD",
    )
