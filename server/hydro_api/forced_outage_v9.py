"""Показатели вынужденных простоев (FOR/EFOR/EFORd) гидроагрегатов (V9.4).

ENGINE_ID: V9-FORCED-OUTAGE-STATISTICS-1

Мотивация — развитие TurbineReliability (зрелость 2 после V9.0: ISO 20816-5,
Weibull MLE, E[C] с HOLD) опорой на ОПУБЛИКОВАННУЮ натурную статистику
отказов вместо чисто синтетических параметров. Опорные классы —
data/reference/hydro_for_open_stats.json (класс OPEN-PUBLISHED-REFERENCE:
NERC GADS 2008-2012 hydro class и др., каждое число со source_ref).

Формулы — отраслевые стандарты, воспроизведены по опубликованным
первоисточникам:
  * IEEE Std 762 / NERC GADS DRI (Appendix F): FOR = FOH/(FOH+SH+Sync+Pmp);
    EFOR = (FOH+EFDH)/(FOH+SH+Sync+Pmp+EFDHRS).
  * PJM Manual 22 (rev. 18): EFORd = (f*FOH + fp*EFDH)/(SH + f*FOH),
    f-фактор спроса f = (1/r + 1/T)/(1/r + 1/T + 1/D), где
    r = FOH/N_FO (средняя длительность отказа), D = SH/N_starts (среднее
    время спроса), T = RSH/N_attempted (средний резервный простой).
  * PJM Manual 22 (immature unit): объединение собственной истории агрегата
    с классовым средним — EEFORd = (n*hist + (N-n)*class)/N, N=5 лет —
    эмпирически-байесовская стягивание малой выборки к классу; это и есть
    отраслевой способ работы с малым числом лет наблюдений.
  * PJM Manual 22 (two-state model): mu = (1-p)*C, var = (1-p)*p*C^2.
  * Биномиальная надёжность станции из n агрегатов (классика, ср. русскую
    практику Kв = omega*Tв по Дудову): P(k из n доступны) = C(n,k) p^k q^(n-k).

Fail-closed: отрицательные часы, нулевые знаменатели, вероятности вне
[0,1] — ArithmeticError. Никаких «типичных» значений по умолчанию:
числа приходят аргументами или из reference-файла с source_ref.

production_ready=False: классовая статистика GADS (североамериканский
флот) НЕ является натурной статистикой Колымского каскада; применение к
конкретным агрегатам — только после натурной выгрузки журналов (HOLD).
"""
from __future__ import annotations

import math
from typing import List, Tuple

from pydantic import BaseModel, ConfigDict, Field

ENGINE_ID = "V9-FORCED-OUTAGE-STATISTICS-1"

_PJM_MATURE_YEARS = 5  # PJM Manual 22: агрегат «зрелый» после 5 полных лет


class UnitOutageHours(BaseModel):
    """Часы состояний агрегата за период (термины IEEE 762 / GADS)."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    foh: float = Field(ge=0)    # forced outage hours (U1+U2+U3+SF)
    sh: float = Field(ge=0)     # service hours
    rsh: float = Field(ge=0)    # reserve shutdown hours
    efdh: float = Field(ge=0)   # equivalent forced derated hours (D1+D2+D3)
    sync_hours: float = Field(ge=0, default=0.0)
    pumping_hours: float = Field(ge=0, default=0.0)
    n_forced_outages: int = Field(ge=0, default=0)
    n_actual_starts: int = Field(ge=0, default=0)
    n_attempted_starts: int = Field(ge=0, default=0)


class UnitReliabilityReport(BaseModel):
    """Сводные показатели надёжности агрегата с квитанцией."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    for_rate: float = Field(ge=0, le=1)
    efor: float = Field(ge=0, le=1)
    eford: float = Field(ge=0, le=1)
    f_factor_full: float = Field(ge=0, le=1)
    eford_pooled: float = Field(ge=0, le=1)
    pool_years_used: float = Field(ge=0)
    production_ready: bool = False


def for_rate(h: UnitOutageHours) -> float:
    """FOR = FOH/(FOH+SH+Sync+Pmp) — IEEE 762 / NERC GADS DRI App. F."""
    den = h.foh + h.sh + h.sync_hours + h.pumping_hours
    if den <= 0.0:
        raise ArithmeticError("FOR_ZERO_DENOMINATOR: FOH+SH+Sync+Pmp == 0")
    return h.foh / den


def efor(h: UnitOutageHours) -> float:
    """EFOR = (FOH+EFDH)/(FOH+SH+Sync+Pmp) (EFDHRS=0: дерейтинги при RS не учитываем)."""
    den = h.foh + h.sh + h.sync_hours + h.pumping_hours
    if den <= 0.0:
        raise ArithmeticError("EFOR_ZERO_DENOMINATOR")
    return (h.foh + h.efdh) / den


def f_factor_full(h: UnitOutageHours) -> float:
    """f-фактор спроса PJM Manual 22: f = (1/r + 1/T)/(1/r + 1/T + 1/D)."""
    if h.n_forced_outages <= 0 or h.n_actual_starts <= 0 or h.n_attempted_starts <= 0:
        raise ArithmeticError("F_FACTOR_COUNTS: нужны n_forced_outages, n_actual_starts, n_attempted_starts > 0")
    r = h.foh / h.n_forced_outages        # средняя длительность вынужденного простоя
    d = h.sh / h.n_actual_starts          # среднее время спроса
    t = h.rsh / h.n_attempted_starts      # средний резервный простой
    if r <= 0.0 or d <= 0.0:
        raise ArithmeticError("F_FACTOR_DEGENERATE: r или D неположительны")
    num = 1.0 / r + (1.0 / t if t > 0.0 else 0.0)
    den = num + 1.0 / d
    return num / den


def eford(h: UnitOutageHours, f_full: float, f_partial: float) -> float:
    """EFORd = (f*FOH + fp*EFDH)/(SH + f*FOH) — PJM Manual 22, уравнение 2."""
    for name, v in (("f_full", f_full), ("f_partial", f_partial)):
        if not 0.0 <= v <= 1.0:
            raise ArithmeticError(f"EFORD_FACTOR_RANGE: {name}={v} вне [0,1]")
    den = h.sh + f_full * h.foh
    if den <= 0.0:
        raise ArithmeticError("EFORD_ZERO_DENOMINATOR: SH + f*FOH == 0")
    return (f_full * h.foh + f_partial * h.efdh) / den


def pool_class_average(
    historical_rate: float,
    n_full_years: float,
    class_average_rate: float,
    mature_years: int = _PJM_MATURE_YEARS,
) -> float:
    """Стягивание малой истории к классовому среднему (PJM M22, immature unit).

    EEFORd = (n*hist + (N-n)*class)/N; n >= N => чистая история;
    n == 0 => чистый класс. Отраслевой эмпирически-байесовский приём.
    """
    for name, v in (("historical_rate", historical_rate), ("class_average_rate", class_average_rate)):
        if not 0.0 <= v <= 1.0:
            raise ArithmeticError(f"POOL_RATE_RANGE: {name}={v} вне [0,1]")
    if n_full_years < 0.0:
        raise ArithmeticError("POOL_YEARS_NEGATIVE")
    if mature_years <= 0:
        raise ArithmeticError("POOL_MATURE_YEARS_NONPOSITIVE")
    n = min(n_full_years, float(mature_years))
    return (n * historical_rate + (mature_years - n) * class_average_rate) / mature_years


def two_state_capacity(eford_d: float, capacity_mw: float) -> Tuple[float, float]:
    """Двухсостоятельная модель PJM M22: mu=(1-p)*C, var=(1-p)*p*C^2."""
    if not 0.0 <= eford_d <= 1.0:
        raise ArithmeticError(f"TWO_STATE_RATE_RANGE: p={eford_d} вне [0,1]")
    if capacity_mw <= 0.0:
        raise ArithmeticError("TWO_STATE_CAPACITY_NONPOSITIVE")
    return (1.0 - eford_d) * capacity_mw, (1.0 - eford_d) * eford_d * capacity_mw ** 2


def binomial_station_availability(n_units: int, p_unit: float, min_units: int) -> float:
    """P(доступно >= min_units из n) при независимых агрегатах с p_unit.

    Классическая биномиальная модель (теорема о повторении опытов);
    p_unit = 1 - q, q — вероятность аварийного простоя (в русской
    практике q = Kв = omega_в * T_в).
    """
    if n_units < 1 or not 1 <= min_units <= n_units:
        raise ArithmeticError("BINOMIAL_CONFIG: нужно 1 <= min_units <= n_units")
    if not 0.0 <= p_unit <= 1.0:
        raise ArithmeticError(f"BINOMIAL_P_RANGE: p={p_unit} вне [0,1]")
    total = 0.0
    for k in range(min_units, n_units + 1):
        if p_unit == 0.0:
            pmf = 0.0  # k >= min_units >= 1: безотказных агрегатов нет
        elif p_unit == 1.0:
            pmf = 1.0 if k == n_units else 0.0
        else:
            log_pmf = (math.lgamma(n_units + 1) - math.lgamma(k + 1) - math.lgamma(n_units - k + 1)
                       + k * math.log(p_unit) + (n_units - k) * math.log1p(-p_unit))
            pmf = math.exp(log_pmf)
        total += pmf
    return min(1.0, total)


def expected_forced_energy_loss_mwh(eford_d: float, capacity_mw: float, service_hours: float) -> float:
    """Ожидаемая недоотдача энергии от вынужденных простоев, МВт·ч за период."""
    if not 0.0 <= eford_d <= 1.0:
        raise ArithmeticError("EENS_RATE_RANGE")
    if capacity_mw <= 0.0 or service_hours <= 0.0:
        raise ArithmeticError("EENS_ARGS_NONPOSITIVE")
    return eford_d * capacity_mw * service_hours


def unit_report(h: UnitOutageHours, class_average_eford: float, n_full_years: float) -> UnitReliabilityReport:
    """Полная квитанция агрегата: FOR/EFOR/EFORd + стягивание к классу."""
    if not 0.0 <= class_average_eford <= 1.0:
        raise ArithmeticError("CLASS_RATE_RANGE")
    f_full = f_factor_full(h) if h.n_forced_outages > 0 and h.foh > 0 else 1.0
    ed = eford(h, f_full, f_full)
    return UnitReliabilityReport(
        for_rate=for_rate(h), efor=efor(h), eford=ed, f_factor_full=f_full,
        eford_pooled=pool_class_average(ed, n_full_years, class_average_eford),
        pool_years_used=min(n_full_years, float(_PJM_MATURE_YEARS)))
