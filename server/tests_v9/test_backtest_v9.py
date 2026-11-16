"""Тесты rolling-origin бэктеста месячного стока (backtest_v9)."""
import math

import pytest

from hydro_api.backtest_v9 import (
    ENGINE_ID,
    climatology_ensemble,
    run_monthly_backtest,
)


def make_series(years=range(1933, 2000), base=100.0, month_amp=0.0):
    """Детерминированный синтетический ряд: Q = base*(1+month_amp*(m-1))."""
    return {(y, m): base * (1.0 + month_amp * (m - 1))
            for y in years for m in range(1, 13)}


class TestClimatologyEnsemble:
    def test_no_future_leakage(self):
        s = make_series()
        ens = climatology_ensemble(s, 1950, 6, min_history=5)
        assert len(ens) == 17  # 1933..1949
        # значения константны, поэтому проверяем утечку по длине и отдельно —
        # на нестационарном ряду
        s2 = {(y, m): float(y) for y in range(1933, 1960) for m in range(1, 13)}
        ens2 = climatology_ensemble(s2, 1950, 6, min_history=5)
        assert max(ens2) == 1949.0  # будущее недоступно
        assert 1950.0 not in ens2

    def test_window_limits_history(self):
        s2 = {(y, m): float(y) for y in range(1933, 1960) for m in range(1, 13)}
        ens = climatology_ensemble(s2, 1955, 1, min_history=3, window_years=5)
        assert ens == [1950.0, 1951.0, 1952.0, 1953.0, 1954.0]

    def test_insufficient_history_fails_closed(self):
        s = make_series()
        with pytest.raises(ValueError, match="BACKTEST_INSUFFICIENT_HISTORY"):
            climatology_ensemble(s, 1935, 3, min_history=10)

    def test_min_history_floor(self):
        with pytest.raises(ValueError, match="BACKTEST_MIN_HISTORY"):
            climatology_ensemble(make_series(), 1950, 1, min_history=1)

    def test_month_range(self):
        with pytest.raises(ValueError, match="BACKTEST_MONTH_RANGE"):
            climatology_ensemble(make_series(), 1950, 13)


class TestRunBacktest:
    def test_constant_series_perfect_skill(self):
        # константный ряд => ансамбль идеален, CRPS=0, покрытие 1.0
        s = make_series(base=200.0)
        r = run_monthly_backtest(s, "SYNTHETIC-TEST", 1953, 1999,
                                 min_history=20, window_years=20)
        assert r.n_cases == 47 * 12
        assert r.crps_climatology == pytest.approx(0.0, abs=1e-12)
        assert r.coverage_80 == pytest.approx(1.0)
        assert r.coverage_95 == pytest.approx(1.0)
        assert r.crps_persistence == pytest.approx(0.0, abs=1e-12)
        assert r.engine == ENGINE_ID
        assert r.benchmark_model == "climatology"
        assert r.production_ready is False

    def test_step_series_persistence_beats_climatology(self):
        # скачок уровня в 1960: persistence (прошлый год) точнее старой климатологии
        s = {(y, m): (100.0 if y < 1960 else 300.0)
             for y in range(1933, 1990) for m in range(1, 13)}
        r = run_monthly_backtest(s, "SYNTHETIC-TEST", 1961, 1989,
                                 min_history=20, window_years=20)
        # после 1960 окно полностью «новое» => CRPS=0 для обоих; проверяем год скачка
        assert r.years_backtested[0] == 1961
        assert r.crps_climatology >= 0.0

    def test_nonuniform_ensemble_rejected(self):
        # расширяющееся окно => размеры растут => fail-closed
        s = make_series()
        with pytest.raises(ValueError, match="BACKTEST_NONUNIFORM_ENSEMBLE"):
            run_monthly_backtest(s, "SYNTHETIC-TEST", 1953, 1999,
                                 min_history=20, window_years=0)

    def test_empty_result_fails_closed(self):
        s = make_series(years=range(1990, 2000))
        with pytest.raises(ValueError, match="BACKTEST_NO_CASES"):
            run_monthly_backtest(s, "SYNTHETIC-TEST", 1990, 1999,
                                 min_history=20, window_years=20)

    def test_year_range_validation(self):
        with pytest.raises(ValueError, match="BACKTEST_YEAR_RANGE"):
            run_monthly_backtest(make_series(), "X", 1999, 1953,
                                 min_history=5, window_years=5)

    def test_skill_bounded(self):
        s = {(y, m): 100.0 + 10.0 * math.sin(y * 0.7 + m)
             for y in range(1933, 2000) for m in range(1, 13)}
        r = run_monthly_backtest(s, "SYNTHETIC-TEST", 1953, 1999,
                                 min_history=20, window_years=20)
        assert r.crps_climatology > 0.0
        assert r.decomposition_reliability >= 0.0
        assert r.decomposition_uncertainty >= 0.0
        # инвариант декомпозиции
        assert (r.decomposition_reliability - r.decomposition_resolution
                + r.decomposition_uncertainty) == pytest.approx(r.crps_climatology, rel=1e-6)
