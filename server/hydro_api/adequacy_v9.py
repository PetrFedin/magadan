"""Генерационная адекватность: LOLE / EENS свёрткой отказов (V9, issue #18).

Классическая теория надёжности генерирующей системы (Billinton & Allan,
«Reliability Evaluation of Power Systems»): таблица вероятностей отказов
мощности (COPT) строится рекуррентной свёрткой двоичных состояний
агрегатов (работает / в вынужденном простое с вероятностью FOR):

    P_0(c) = 1{c == C_1} * (1 - p_1) + 1{c == 0} * p_1
    P_k(c) = P_{k-1}(c) * (1 - p_k) + P_{k-1}(c - C_k) * p_k

По COPT и ряду нагрузки L_t:
    LOLP_t  = P(C < L_t)
    LOLE    = sum_t LOLP_t * dt                      [ч]
    EENS    = sum_t E[max(0, L_t - C)] * dt          [МВт·ч]

Критерий N-1: суммарная установленная мощность за вычетом наибольшего
агрегата покрывает максимум нагрузки.

Репозиторная культура fail-closed: FOR агрегатов — допущение, а не
статистика отказов (натурной статистики у проекта нет), поэтому
for_assumption=True => decision=HOLD. Опорные параметры энергосистемы
Магаданской области см. data/reference/kolyma_magadan_open_sources.json
(изолированная система, установленная 1790 МВт, ГЭС 1470 / ТЭС 320,
максимум нагрузки 460 МВт (2023) по материалам СО ЕЭС).
"""
from __future__ import annotations

from typing import Dict, List, Sequence

from pydantic import BaseModel, ConfigDict, Field

ENGINE_ID = "V9-GENERATION-ADEQUACY-CONVOLUTION-1"
PROB_TOL = 1e-9


class GeneratingUnit(BaseModel):
    """Генерирующий агрегат с двоичной моделью состояния."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    name: str = Field(min_length=1, max_length=120)
    capacity_mw: float = Field(gt=0)
    forced_outage_rate: float = Field(
        ge=0.0, lt=1.0,
        description="Вероятность вынужденного простоя (FOR), доля")
    for_is_assumption: bool = Field(
        default=True,
        description="False только при наличии натурной статистики отказов")


class AdequacyResult(BaseModel):
    """Метрики адекватности генерирующей системы."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    units_count: int
    installed_capacity_mw: float
    peak_load_mw: float
    n_steps: int
    step_hours: float
    copt_available_mw: List[float]
    copt_probability: List[float]
    lole_hours: float
    eens_mwh: float
    loss_of_load_probability_peak: float
    n_minus_1_secure: bool
    n_minus_1_margin_mw: float
    for_assumption: bool
    decision: str
    production_ready: bool = False


def build_copt(units: Sequence[GeneratingUnit]) -> Dict[float, float]:
    """Свёртка двоичных состояний агрегатов в COPT (доступная мощность -> P)."""
    if not units:
        raise ValueError("ADEQUACY_NO_UNITS: пустой список агрегатов")
    table: Dict[float, float] = {0.0: 1.0}  # до добавления агрегатов мощность 0
    for u in units:
        nxt: Dict[float, float] = {}
        for cap, prob in table.items():
            nxt[cap + u.capacity_mw] = nxt.get(cap + u.capacity_mw, 0.0) + prob * (1.0 - u.forced_outage_rate)
            nxt[cap] = nxt.get(cap, 0.0) + prob * u.forced_outage_rate
        table = nxt
    total_p = sum(table.values())
    if abs(total_p - 1.0) > PROB_TOL * max(1, len(table)):
        raise ArithmeticError(
            f"ADEQUACY_COPT_PROBABILITY_LEAK: sum(P)={total_p!r}")
    return table


def evaluate_adequacy(
    units: Sequence[GeneratingUnit],
    load_mw: Sequence[float],
    step_hours: float = 1.0,
) -> AdequacyResult:
    """LOLE/EENS по COPT и хронологическому ряду нагрузки."""
    if step_hours <= 0:
        raise ValueError("ADEQUACY_STEP_HOURS: шаг должен быть > 0")
    if not load_mw:
        raise ValueError("ADEQUACY_NO_LOAD: пустой ряд нагрузки")
    for lv in load_mw:
        if lv < 0:
            raise ValueError(f"ADEQUACY_NEGATIVE_LOAD: нагрузка {lv} МВт < 0")

    copt = build_copt(units)
    installed = sum(u.capacity_mw for u in units)
    largest = max(u.capacity_mw for u in units)
    peak = max(load_mw)

    lole = 0.0
    eens = 0.0
    for lv in load_mw:
        lolp_t = 0.0
        eens_t = 0.0
        for cap, prob in copt.items():
            deficit = lv - cap
            if deficit > 0:
                lolp_t += prob
                eens_t += prob * deficit
        lole += lolp_t * step_hours
        eens += eens_t * step_hours

    lolp_peak = sum(p for c, p in copt.items() if c < peak)
    margin = installed - largest - peak

    for_assumption = any(u.for_is_assumption for u in units)
    caps_sorted = sorted(copt)
    return AdequacyResult(
        units_count=len(units),
        installed_capacity_mw=installed,
        peak_load_mw=peak,
        n_steps=len(load_mw),
        step_hours=step_hours,
        copt_available_mw=caps_sorted,
        copt_probability=[copt[c] for c in caps_sorted],
        lole_hours=lole,
        eens_mwh=eens,
        loss_of_load_probability_peak=lolp_peak,
        n_minus_1_secure=margin >= 0,
        n_minus_1_margin_mw=margin,
        for_assumption=for_assumption,
        decision="HOLD" if for_assumption else "REVIEW",
    )
