"""Гидравлика и теплопотери участка теплосети (V9, HeatNet Economics).

Постановка: прямой изолированный трубопровод в грунте, заданы длина,
диаметр, изоляция, массовый расход, температура подачи и грунта.

Тепловая часть (стационарная, доминирующее сопротивление изоляции):
    R'  = ln(D_ins / D_pipe) / (2 * pi * lambda_ins)   [м·K/Вт, на 1 м]
    T(x) = T_g + (T_in - T_g) * exp(-x / (m_dot * c_p * R'))
    Q_loss = m_dot * c_p * (T_in - T_out)

Гидравлическая часть (Дарси-Вейсбах):
    v = m_dot / (rho * A)
    f: ламинарно 64/Re; турбулентно — Свами-Джейн (Swamee-Jain, 1976);
       переходная зона 2300 < Re < 4000 помечается regime=transitional
       и НЕ экстраполируется молча (fail-closed: результат невалиден
       для проектных решений, decision=HOLD всегда при uncalibrated)
    dp = f * (L/D) * rho * v^2 / 2

Репозиторная культура fail-closed: коэффициенты теплопередачи стенки,
конвекции и грунта НЕ включены (натурных данных нет) — потери занижены
относительно реальной трубы, о чём честно говорит поле
model_limitations. Климатический якорь температуры грунта/воздуха
Магадана см. data/reference/kolyma_magadan_open_sources.json.
"""
from __future__ import annotations

import math
from typing import List

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENGINE_ID = "V9-HEATNET-PIPE-1"
RE_LAMINAR_MAX = 2300.0
RE_TURBULENT_MIN = 4000.0


class PipeSegment(BaseModel):
    """Параметры изолированного участка теплосети."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    length_m: float = Field(gt=0)
    inner_diameter_m: float = Field(gt=0)
    insulation_outer_diameter_m: float = Field(gt=0)
    insulation_conductivity_w_mk: float = Field(gt=0, description="lambda изоляции, Вт/(м·K)")
    roughness_m: float = Field(default=4.5e-5, ge=0.0, description="Абсолютная шероховатость, м (сталь ~0.045 мм)")
    mass_flow_kg_s: float = Field(gt=0)
    supply_temp_c: float
    ground_temp_c: float
    rho_kg_m3: float = Field(default=1000.0, gt=0)
    cp_j_kg_k: float = Field(default=4190.0, gt=0)
    calibrated: bool = Field(default=False, description="True только после калибровки на натурных потерях")

    @model_validator(mode="after")
    def _insulation_covers_pipe(self) -> "PipeSegment":
        if self.insulation_outer_diameter_m <= self.inner_diameter_m:
            raise ValueError(
                "HEATNET_INSULATION_DIAMETER: наружный диаметр изоляции "
                "должен быть больше внутреннего диаметра трубы")
        return self


class PipeResult(BaseModel):
    """Тепловые и гидравлические характеристики участка."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    outlet_temp_c: float
    heat_loss_w: float
    heat_loss_w_per_m: float
    velocity_m_s: float
    reynolds: float
    friction_factor: float
    flow_regime: str  # laminar / transitional / turbulent
    pressure_drop_pa: float
    head_drop_m: float
    decision: str
    model_limitations: List[str]
    production_ready: bool = False


def friction_factor_swamee_jain(reynolds: float, rel_roughness: float) -> float:
    """Явная аппроксимация Свами-Джейна (1976), Re > 4000."""
    if reynolds <= 0:
        raise ValueError("HEATNET_FRICTION_RE: Re должен быть > 0")
    a = rel_roughness / 3.7 + 5.74 / reynolds ** 0.9
    return 0.25 / (math.log10(a) ** 2)


def friction_factor_haaland(reynolds: float, rel_roughness: float) -> float:
    """Явная аппроксимация Хааланда (1983) — независимая перекрёстная проверка."""
    if reynolds <= 0:
        raise ValueError("HEATNET_FRICTION_RE: Re должен быть > 0")
    a = (rel_roughness / 3.7) ** 1.11 + 6.9 / reynolds
    return 1.0 / (-1.8 * math.log10(a)) ** 2


def evaluate_pipe(seg: PipeSegment) -> PipeResult:
    """Тепловой и гидравлический расчёт участка."""
    d = seg.inner_diameter_m
    area = math.pi * d * d / 4.0
    v = seg.mass_flow_kg_s / (seg.rho_kg_m3 * area)

    # --- тепловая часть
    r_prime = math.log(seg.insulation_outer_diameter_m / d) / (
        2.0 * math.pi * seg.insulation_conductivity_w_mk)
    decay = seg.mass_flow_kg_s * seg.cp_j_kg_k * r_prime  # м: характерная длина остывания
    t_out = seg.ground_temp_c + (seg.supply_temp_c - seg.ground_temp_c) * math.exp(
        -seg.length_m / decay)
    q_loss = seg.mass_flow_kg_s * seg.cp_j_kg_k * (seg.supply_temp_c - t_out)

    # --- гидравлическая часть
    nu = _water_viscosity_default(seg.supply_temp_c)
    re = v * d / nu
    if re < RE_LAMINAR_MAX:
        f = 64.0 / re
        regime = "laminar"
    elif re >= RE_TURBULENT_MIN:
        f = friction_factor_swamee_jain(re, seg.roughness_m / d)
        regime = "turbulent"
    else:
        # fail-closed: переходная зона не моделируется, используем худший
        # (больший) из граничных f и честно помечаем режим
        f_lam = 64.0 / RE_LAMINAR_MAX
        f_turb = friction_factor_swamee_jain(RE_TURBULENT_MIN, seg.roughness_m / d)
        f = max(f_lam, f_turb)
        regime = "transitional"
    dp = f * (seg.length_m / d) * seg.rho_kg_m3 * v * v / 2.0
    head = dp / (seg.rho_kg_m3 * 9.80665)

    return PipeResult(
        outlet_temp_c=t_out,
        heat_loss_w=q_loss,
        heat_loss_w_per_m=q_loss / seg.length_m,
        velocity_m_s=v,
        reynolds=re,
        friction_factor=f,
        flow_regime=regime,
        pressure_drop_pa=dp,
        head_drop_m=head,
        decision="CALIBRATED-REVIEW" if seg.calibrated else "HOLD",
        model_limitations=[
            "учтено только сопротивление изоляции (стенка, конвекция, грунт — нет): потери занижены",
            "вязкость воды — линейная интерполяция между справочными точками, не точная функция",
            "переходный режим 2300<Re<4000 не моделируется, берётся худший из граничных f",
        ],
    )


# Справочные точки кинематической вязкости воды (м²/с), линейная интерполяция
_VISCOSITY_TABLE = [
    (0.0, 1.79e-6), (20.0, 1.00e-6), (40.0, 0.66e-6),
    (60.0, 0.47e-6), (80.0, 0.36e-6), (100.0, 0.29e-6),
]


def _water_viscosity_default(temp_c: float) -> float:
    """Кинематическая вязкость воды, м²/с — линейная интерполяция между
    справочными точками _VISCOSITY_TABLE (вне 0..100 °C — краевая точка).
    Не точная справочная функция — см. model_limitations.
    """
    t = min(100.0, max(0.0, temp_c))
    for (t0, nu0), (t1, nu1) in zip(_VISCOSITY_TABLE[:-1], _VISCOSITY_TABLE[1:]):
        if t0 <= t <= t1:
            return nu0 + (nu1 - nu0) * (t - t0) / (t1 - t0)
    return _VISCOSITY_TABLE[-1][1]  # unreachable при зажатии t выше
