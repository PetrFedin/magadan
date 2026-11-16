"""Тесты тренд-адаптивного климатологического ансамбля (V9.4).

Проверяются: восстановление известного тренда, ДИ Сена, устранение
отставания уровня против сырой климатологии, инфляция дисперсии от
неопределённости тренда, строгая причинность (будущее не влияет),
fail-closed гарды, бит-в-бит детерминизм.
"""
from __future__ import annotations

import math

import pytest

from hydro_api.backtest_v9 import climatology_ensemble
from hydro_api.probabilistic_verification_v9 import interval_coverage, pit_value
from hydro_api.trend_adaptive_v9 import (
    _theil_sen_ci,
    trend_adaptive_ensemble,
)


def _det_series(years, month_fn):
    """Детерминированный ряд: month_fn(year, month) -> расход > 0."""
    return {(y, m): month_fn(y, m) for y in years for m in range(1, 13)}


class TestTheilSen:
    def test_recovers_known_slope(self):
        x = [float(y) for y in range(1970, 1990)]
        y = [2.0 + 0.03 * v for v in x]
        slope, lo, hi, n_pairs = _theil_sen_ci(x, y)
        assert abs(slope - 0.03) < 1e-12
        assert lo <= slope <= hi
        assert n_pairs == 20 * 19 // 2

    def test_ci_contains_true_slope_with_noise(self):
        x = [float(y) for y in range(1970, 1990)]
        y = [2.0 + 0.03 * v + 0.05 * math.sin(12.9898 * v) for v in x]
        slope, lo, hi, _ = _theil_sen_ci(x, y)
        assert lo <= 0.03 <= hi

    def test_degenerate_x_fails(self):
        with pytest.raises(ArithmeticError, match="TREND_NO_PAIRWISE_SLOPES"):
            _theil_sen_ci([1970.0, 1970.0, 1970.0], [1.0, 2.0, 3.0])


class TestTrendAdaptiveEnsemble:
    def test_fixes_location_lag_vs_raw_climatology(self):
        # лог-тренд +1%/год: сырое окно систематически занижает будущий уровень
        series = _det_series(range(1950, 2001), lambda y, m: 100.0 * m * math.exp(0.01 * (y - 1950)))
        y_test, m_test = 1999, 6
        obs = series[(y_test, m_test)]
        raw = climatology_ensemble(series, y_test, m_test, min_history=20, window_years=20)
        trend, fit = trend_adaptive_ensemble(series, y_test, m_test, min_history=20, window_years=20)
        raw_med = raw[len(raw) // 2]
        trend_med = trend[len(trend) // 2]
        assert abs(trend_med - obs) / obs < 0.02          # перенос точен
        assert (obs - raw_med) / obs > 0.05               # сырое окно отстаёт
        assert fit.slope_log_per_year == pytest.approx(0.01, abs=1e-9)

    def test_strict_causality_future_does_not_change_ensemble(self):
        base = _det_series(range(1950, 2001), lambda y, m: 50.0 + 10.0 * m + 0.3 * (y - 1950))
        modified = dict(base)
        for y in range(1995, 2001):  # «будущее» резко меняем — ансамбль 1994 не должен среагировать
            for m in range(1, 13):
                modified[(y, m)] = 1.0e6
        e1, _ = trend_adaptive_ensemble(base, 1994, 3, min_history=20, window_years=20)
        e2, _ = trend_adaptive_ensemble(modified, 1994, 3, min_history=20, window_years=20)
        assert e1 == e2

    def test_trend_uncertainty_inflates_dispersion(self):
        # шумные данные: широкий ДИ наклона => смесь шире чистых аномалий
        series = _det_series(
            range(1950, 2000),
            lambda y, m: 100.0 * math.exp(0.01 * (y - 1950) + 0.35 * math.sin(3.7 * y + m)))
        ens, fit = trend_adaptive_ensemble(series, 1999, 6, min_history=20, window_years=20)
        assert fit.pred_var_log > 0.0
        width = math.log(ens[-1]) - math.log(ens[0])
        raw_spread = max(
            math.log(series[(y, 6)]) for y in range(1979, 1999)
        ) - min(math.log(series[(y, 6)]) for y in range(1979, 1999))
        assert width > 0.9 * raw_spread  # инфляция не схлопывает ансамбль

    def test_flat_series_pred_var_positive_and_members_centered(self):
        series = _det_series(range(1960, 2000), lambda y, m: 200.0 + 5.0 * math.sin(y * 1.3 + m))
        ens, fit = trend_adaptive_ensemble(series, 1999, 7, min_history=20, window_years=20)
        assert abs(fit.slope_log_per_year) < 0.01
        assert 150.0 < ens[len(ens) // 2] < 260.0
        assert ens == sorted(ens)
        assert all(v > 0.0 for v in ens)

    def test_determinism_bitwise(self):
        series = _det_series(range(1950, 2000), lambda y, m: 80.0 + 0.5 * y % 13 + m)
        a = trend_adaptive_ensemble(series, 1998, 2, min_history=20, window_years=20)
        b = trend_adaptive_ensemble(series, 1998, 2, min_history=20, window_years=20)
        assert a[0] == b[0] and a[1].model_dump_json() == b[1].model_dump_json()

    def test_guards(self):
        series = _det_series(range(1980, 2000), lambda y, m: 100.0)
        with pytest.raises(ArithmeticError, match="TREND_INSUFFICIENT_HISTORY"):
            trend_adaptive_ensemble(series, 1990, 1, min_history=20, window_years=20)
        with pytest.raises(ArithmeticError, match="TREND_MONTH_RANGE"):
            trend_adaptive_ensemble(series, 1995, 13, min_history=5, window_years=10)
        with pytest.raises(ArithmeticError, match="TREND_ENSEMBLE_SIZE"):
            trend_adaptive_ensemble(series, 1995, 1, min_history=5, window_years=10, m=1)
        bad = dict(series)
        bad[(1994, 5)] = 0.0
        with pytest.raises(ArithmeticError, match="TREND_NONPOSITIVE_DATA"):
            trend_adaptive_ensemble(bad, 1995, 5, min_history=5, window_years=10)


class TestTrendAdaptiveOutOfSample:
    def test_coverage_improves_on_trended_series(self):
        # on-line проверка на детерминированном ряде с трендом:
        # тренд-адаптивный ансамбль покрывает чаще сырого
        series = _det_series(
            range(1950, 2001),
            lambda y, m: 100.0 * math.exp(0.015 * (y - 1950)) * (1.0 + 0.20 * math.sin(2.3 * y + 1.7 * m)))
        n = cov_raw = cov_tr = 0
        for y in range(1975, 2001):
            for m in (3, 6, 9):
                obs = series[(y, m)]
                raw = climatology_ensemble(series, y, m, min_history=20, window_years=20)
                tr, _ = trend_adaptive_ensemble(series, y, m, min_history=20, window_years=20)
                n += 1
                cov_raw += interval_coverage([raw], [obs], alpha=0.2)["empirical_coverage"]
                cov_tr += interval_coverage([tr], [obs], alpha=0.2)["empirical_coverage"]
        assert cov_tr / n > cov_raw / n + 0.10
        pit_raw, pit_tr = 0.0, 0.0
        for y in range(1990, 2001):
            obs = series[(y, 6)]
            raw = climatology_ensemble(series, y, 6, min_history=20, window_years=20)
            tr, _ = trend_adaptive_ensemble(series, y, 6, min_history=20, window_years=20)
            pit_raw += pit_value(raw, obs)
            pit_tr += pit_value(tr, obs)
        assert abs(pit_tr / 12 - 0.5) < abs(pit_raw / 12 - 0.5)  # смещение положения уменьшено
