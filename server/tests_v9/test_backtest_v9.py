"""Тесты V9.2: бэктест месячного стока (rolling-origin, строго причинный)."""

import math

import pytest

from hydro_api.backtest_v9 import (
    climatology_ensemble,
    run_monthly_backtest,
)


def _series(years, value_fn):
    """{(год, месяц): значение} для диапазона лет."""
    return {(y, m): value_fn(y, m) for y in years for m in range(1, 13)}


class TestClimatologyEnsemble:
    def test_strictly_causal_no_future_leak(self):
        # Значение равно номеру года: если бы утёк год прогноза,
        # член 2000 появился бы в ансамбле для 2000.
        series = _series(range(1990, 2005), lambda y, m: float(y))
        ens = climatology_ensemble(series, 2000, 6, min_history=5)
        assert max(ens) == 1999.0
        assert len(ens) == 10

    def test_window_limits_history(self):
        series = _series(range(1980, 2005), lambda y, m: float(y))
        ens = climatology_ensemble(series, 2000, 6, min_history=5, window_years=5)
        assert sorted(ens) == [1995.0, 1996.0, 1997.0, 1998.0, 1999.0]

    def test_insufficient_history_fail_closed(self):
        series = _series(range(1998, 2005), lambda y, m: 1.0)
        with pytest.raises(ValueError, match="BACKTEST_INSUFFICIENT_HISTORY"):
            climatology_ensemble(series, 2000, 6, min_history=10)

    def test_gaps_not_interpolated(self):
        series = _series(range(1990, 2001), lambda y, m: float(y))
        del series[(1995, 6)]
        ens = climatology_ensemble(series, 2000, 6, min_history=5)
        assert 1995.0 not in ens
        assert len(ens) == 9

    def test_invalid_month(self):
        with pytest.raises(ValueError, match="BACKTEST_MONTH_RANGE"):
            climatology_ensemble({}, 2000, 13)


class TestRunMonthlyBacktest:
    def test_no_cases_fail_closed(self):
        series = _series(range(2000, 2003), lambda y, m: 1.0)
        with pytest.raises(ArithmeticError, match="BACKTEST_NO_CASES"):
            run_monthly_backtest(
                series, station="t", year_start=2000, year_end=2002,
                min_history=10, window_years=10,
            )

    def test_nonuniform_ensemble_rejected(self):
        # min_history < window_years=0: ранние годы дают меньший ансамбль.
        series = _series(range(1990, 2000), lambda y, m: float(100 + m))
        with pytest.raises(ArithmeticError, match="BACKTEST_NONUNIFORM_ENSEMBLE"):
            run_monthly_backtest(
                series, station="t", year_start=1995, year_end=1998,
                min_history=3, window_years=0,
            )

    def test_constant_series_perfect_skill(self):
        series = _series(range(1933, 2000), lambda y, m: 500.0)
        rep = run_monthly_backtest(
            series, station="t", year_start=1953, year_end=1999,
            min_history=20, window_years=20,
        )
        assert rep.cases_evaluated == (1999 - 1953 + 1) * 12
        assert rep.ensemble_size == 20
        assert rep.crps_climatology == pytest.approx(0.0, abs=1e-12)
        assert rep.crps_skill_vs_persistence == pytest.approx(0.0, abs=1e-12)
        assert rep.coverage_80 == pytest.approx(1.0)
        assert rep.production_ready is False

    def test_climatology_beats_persistence_on_stable_climate(self):
        # Строгая месячная климатология без тренда: климатология обязана
        # систематически бить персистентность.
        base = [50, 45, 40, 60, 300, 900, 500, 350, 250, 90, 60, 55]

        def vf(y, m):
            return float(base[m - 1] + ((y * 7 + m * 13) % 11) - 5)

        series = _series(range(1933, 2000), vf)
        rep = run_monthly_backtest(
            series, station="t", year_start=1953, year_end=1999,
            min_history=20, window_years=20,
        )
        assert rep.crps_skill_vs_persistence > 0.2
        assert rep.decomposition["reliability"] >= 0.0
        # Инвариант декомпозиции (проверяется и внутри модуля):
        dec = rep.decomposition
        assert dec["reliability"] - dec["resolution"] + dec["uncertainty"] == pytest.approx(
            dec["mean_crps"], abs=1e-9
        )

    def test_year_range_guard(self):
        with pytest.raises(ValueError, match="BACKTEST_YEAR_RANGE"):
            run_monthly_backtest(
                {}, station="t", year_start=2000, year_end=1990,
                min_history=10, window_years=10,
            )

    def test_counts_are_consistent(self):
        series = _series(range(1933, 1995), lambda y, m: float(100 + m))
        del series[(1960, 3)]  # выбивает случай 1960-03 и персистентность 1961-03
        rep = run_monthly_backtest(
            series, station="t", year_start=1953, year_end=1994,
            min_history=20, window_years=20,
        )
        total_slots = (1994 - 1953 + 1) * 12
        assert (
            rep.cases_evaluated + rep.cases_skipped_no_data
            + rep.cases_skipped_no_history == total_slots
        )
        assert rep.cases_skipped_no_data == 2
