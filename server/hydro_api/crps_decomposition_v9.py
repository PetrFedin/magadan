"""Декомпозиция CRPS: reliability / resolution / uncertainty (V9).

Точное тождество для конечных ансамблей через пороговую форму CRPS
(Hersbach, 2000, Weather and Forecasting 15:559-570, eq. 5):

    CRPS(F, y) = integral_z BS(F(z), 1{y <= z}) dz,
    F(z) = P(X <= z) — эмпирическая ФР ансамбля в точке z

и декомпозиция Мёрфи (Murphy, 1973) двойки Бриера в каждой точке z.
Ключевое наблюдение Hersbach: для ансамбля из m членов F(z) принимает
ровно m+1 значений {0, 1/m, ..., 1}, поэтому группировка случаев по
числу членов ниже порога точна, а не приближена:

    BS(z)  = REL(z) - RES(z) + UNC(z)
    UNC(z) = o(1-o),                    o  = P(y <= z) по всей выборке
    REL(z) = sum_j w_j (j/m - o_j)^2    (калибровка внутри группы)
    RES(z) = sum_j w_j (o_j - o)^2      (различимость групп)

Интегрирование по z выполняется точно: подынтегральная функция
кусочно-постоянна, изломы только в точках членов ансамблей и наблюдений.

Инвариант, проверяемый тестами:
    REL - RES + UNC == mean_crps(ансамбли, наблюдения)  (1e-9)

Репозиторная культура fail-closed: декомпозиция — диагностика качества
прогноза, а не сертификат; production_ready=False.
"""
from __future__ import annotations

import bisect
from typing import List, Sequence

from pydantic import BaseModel, ConfigDict, Field

from hydro_api.probabilistic_verification_v9 import crps_ensemble

ENGINE_ID = "V9-CRPS-MURPHY-DECOMPOSITION-1"
IDENTITY_TOL = 1e-9


class CrpsDecomposition(BaseModel):
    """Компоненты декомпозиции CRPS по пулу прогноз-наблюдение."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine: str = ENGINE_ID
    n_cases: int
    ensemble_size: int
    crps_mean: float
    reliability: float
    resolution: float
    uncertainty: float
    identity_residual: float
    production_ready: bool = False


def _murphy_at_threshold(members_below: List[int], obs_below: List[bool],
                         m: int) -> tuple[float, float, float]:
    """Мёрфи-декомпозиция средней двойки Бриера в одной точке z."""
    n = len(members_below)
    o_bar = sum(obs_below) / n
    unc = o_bar * (1.0 - o_bar)

    groups: dict[int, list[int]] = {}
    for j, ob in zip(members_below, obs_below):
        g = groups.setdefault(j, [0, 0])
        g[0] += 1
        g[1] += 1 if ob else 0

    rel = 0.0
    res = 0.0
    for j, (cnt, hits) in groups.items():
        w = cnt / n
        o_j = hits / cnt
        rel += w * (j / m - o_j) ** 2
        res += w * (o_j - o_bar) ** 2
    return rel, res, unc


def decompose_crps(
    ensembles: Sequence[Sequence[float]],
    observations: Sequence[float],
) -> CrpsDecomposition:
    """Точная декомпозиция CRPS по пулу из N пар (ансамбль, наблюдение).

    Все ансамбли должны иметь одинаковый размер m >= 1.
    """
    n = len(ensembles)
    if n == 0:
        raise ValueError("CRPS_DECOMP_EMPTY: пустой пул прогнозов")
    if len(observations) != n:
        raise ValueError(
            f"CRPS_DECOMP_LENGTH_MISMATCH: ensembles={n}, obs={len(observations)}")

    m = len(ensembles[0])
    if m < 1:
        raise ValueError("CRPS_DECOMP_EMPTY_ENSEMBLE: ансамбль без членов")
    for e in ensembles:
        if len(e) != m:
            raise ValueError(
                "CRPS_DECOMP_HETEROGENEOUS_ENSEMBLE: размеры ансамблей различаются")

    # Контрольная сумма CRPS энергетической формой (эталон модуля верификации)
    crps_mean = sum(crps_ensemble(e, y) for e, y in zip(ensembles, observations)) / n

    # Точки излома кусочно-постоянного подынтегрального выражения
    breakpoints = sorted({v for e in ensembles for v in e} | set(observations))
    rel_int = res_int = unc_int = 0.0
    sorted_ens = [sorted(e) for e in ensembles]

    for left, right in zip(breakpoints[:-1], breakpoints[1:]):
        width = right - left
        if width <= 0:
            continue
        z = 0.5 * (left + right)
        members_below = [bisect.bisect_right(e, z) for e in sorted_ens]
        obs_below = [y <= z for y in observations]
        rel, res, unc = _murphy_at_threshold(members_below, obs_below, m)
        rel_int += rel * width
        res_int += res * width
        unc_int += unc * width

    residual = rel_int - res_int + unc_int - crps_mean
    scale = max(1.0, abs(crps_mean))
    if abs(residual) > IDENTITY_TOL * scale:
        raise ArithmeticError(
            f"CRPS_DECOMP_IDENTITY_VIOLATION: REL-RES+UNC={rel_int - res_int + unc_int!r} "
            f"!= CRPS={crps_mean!r}")

    return CrpsDecomposition(
        n_cases=n,
        ensemble_size=m,
        crps_mean=crps_mean,
        reliability=rel_int,
        resolution=res_int,
        uncertainty=unc_int,
        identity_residual=residual,
    )
