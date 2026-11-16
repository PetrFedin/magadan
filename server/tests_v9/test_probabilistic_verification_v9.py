"""Тесты probabilistic_verification_v9: CRPS/PIT/coverage/rank histogram (P0-2)."""
import random

import pytest

from hydro_api.probabilistic_verification_v9 import (
    build_verification_report,
    crps_ensemble,
    interval_coverage,
    mean_crps,
    pit_value,
    rank_histogram,
)


def test_crps_two_member_analytic():
    # CRPS({0,1}, 0.5) = 0.5 - 2/(2*4) = 0.25
    assert crps_ensemble([0.0, 1.0], 0.5) == pytest.approx(0.25, abs=1e-12)


def test_crps_perfect_deterministic_is_zero():
    assert crps_ensemble([5.0] * 8, 5.0) == pytest.approx(0.0, abs=1e-12)


def test_crps_nonnegative():
    rng = random.Random(1)
    for _ in range(100):
        ens = [rng.gauss(0, 1) for _ in range(10)]
        assert crps_ensemble(ens, rng.gauss(0, 1)) >= -1e-12


def test_pit_bounds_and_midpoint():
    assert 0.0 <= pit_value([1.0, 2.0, 3.0], 2.0) <= 1.0
    assert pit_value([1.0, 2.0, 3.0], 2.0) == pytest.approx(0.5)


def test_interval_coverage_exchangeable():
    # Наблюдение обмениваемо с членами ансамбля из m=19 -> покрытие
    # центрального 90% интервала ~ (k_hi - k_lo)/(m+1), плоский rank hist
    rng = random.Random(42)
    ensembles, obs = [], []
    for _ in range(1900):
        mu = rng.uniform(50, 150)
        ensembles.append([rng.gauss(mu, 10) for _ in range(19)])
        obs.append(rng.gauss(mu, 10))
    rep = build_verification_report(ensembles, obs)
    assert 0.78 < rep.coverage_90["empirical_coverage"] < 0.95
    assert abs(rep.pit_mean - 0.5) < 0.05
    assert len(rep.rank_histogram) == 20
    # плоскость: каждая корзина в пределах 2x от равномерного ожидания
    uniform = 1900 / 20
    assert all(0.4 * uniform < c < 1.6 * uniform for c in rep.rank_histogram)


def test_underdispersed_ensemble_undercovers():
    rng = random.Random(7)
    ensembles = [[rng.gauss(100, 1) for _ in range(30)] for _ in range(500)]
    obs = [rng.gauss(100, 10) for _ in range(500)]  # истинная дисперсия в 10 раз больше
    rep = build_verification_report(ensembles, obs)
    assert rep.coverage_90["empirical_coverage"] < 0.5
    # U-образная гистограмма: крайние корзины заполнены сильнее центральных
    hist = rep.rank_histogram
    assert hist[0] + hist[-1] > sum(hist[14:17])


def test_input_validation():
    with pytest.raises(ValueError, match="ENSEMBLE_EMPTY"):
        crps_ensemble([], 1.0)
    with pytest.raises(ValueError, match="NONFINITE"):
        crps_ensemble([1.0, float("nan")], 1.0)
    with pytest.raises(ValueError, match="LENGTH_MISMATCH"):
        interval_coverage([[1, 2]], [1.0, 2.0])
    with pytest.raises(ValueError, match="ALPHA"):
        interval_coverage([[1, 2]], [1.0], alpha=1.5)


def test_mean_crps_matches_sample_mean():
    rng = random.Random(3)
    ensembles = [[rng.gauss(0, 1) for _ in range(5)] for _ in range(50)]
    obs = [rng.gauss(0, 1) for _ in range(50)]
    expected = sum(crps_ensemble(e, o) for e, o in zip(ensembles, obs)) / 50
    assert mean_crps(ensembles, obs) == pytest.approx(expected)


def test_report_fail_closed_flags():
    rep = build_verification_report([[1.0, 2.0, 3.0]], [2.0])
    assert rep.production_ready is False
    assert rep.verified_on_observed_data is False
    assert rep.source_id.startswith("SYNTHETIC")
