"""Тесты декомпозиции CRPS (crps_decomposition_v9)."""
import random

import pytest

from hydro_api.crps_decomposition_v9 import (
    ENGINE_ID,
    decompose_crps,
)
from hydro_api.probabilistic_verification_v9 import mean_crps


class TestIdentity:
    def test_identity_random_ensembles(self):
        rng = random.Random(42)
        ens = [[rng.gauss(0, 1) for _ in range(10)] for _ in range(50)]
        obs = [rng.gauss(0.3, 1.2) for _ in range(50)]
        d = decompose_crps(ens, obs)
        assert d.reliability - d.resolution + d.uncertainty == pytest.approx(
            mean_crps(ens, obs), abs=1e-9)
        assert d.identity_residual == pytest.approx(0.0, abs=1e-9)

    def test_identity_small_m(self):
        rng = random.Random(7)
        ens = [[rng.uniform(0, 10) for _ in range(3)] for _ in range(20)]
        obs = [rng.uniform(0, 10) for _ in range(20)]
        d = decompose_crps(ens, obs)
        assert abs(d.identity_residual) < 1e-9

    def test_components_nonnegative(self):
        rng = random.Random(1)
        ens = [[rng.gauss(0, 2) for _ in range(5)] for _ in range(40)]
        obs = [rng.gauss(0, 2) for _ in range(40)]
        d = decompose_crps(ens, obs)
        assert d.reliability >= 0.0
        assert d.resolution >= 0.0
        assert d.uncertainty >= 0.0


class TestLimitingCases:
    def test_climatological_forecast_zero_resolution(self):
        # Один и тот же ансамбль каждый день => единственная группа на
        # каждом пороге => RES = 0 точно.
        clim = [1.0, 2.0, 3.0, 4.0, 5.0]
        rng = random.Random(3)
        obs = [rng.uniform(0, 6) for _ in range(60)]
        d = decompose_crps([clim] * 60, obs)
        assert d.resolution == pytest.approx(0.0, abs=1e-12)

    def test_perfect_deterministic_forecast_zero_crps(self):
        # Все члены ансамбля равны наблюдению => CRPS = 0,
        # а REL = 0 и RES = UNC (декомпозиция вырождается корректно).
        obs = [1.0, 2.0, 3.5, 7.0]
        ens = [[y, y, y] for y in obs]
        d = decompose_crps(ens, obs)
        assert d.crps_mean == pytest.approx(0.0, abs=1e-12)
        assert d.reliability == pytest.approx(0.0, abs=1e-12)
        assert d.resolution == pytest.approx(d.uncertainty, abs=1e-9)

    def test_well_calibrated_ensemble_low_reliability(self):
        # obs из того же распределения, что и члены ансамбля:
        # REL мала относительно CRPS (конечная выборка: REL = O(m/n)*CRPS,
        # асимптотически -> 0; при n=400, m=20 ожидаемо несколько процентов).
        rng = random.Random(11)
        n = 400
        ens = [[rng.gauss(0, 1) for _ in range(20)] for _ in range(n)]
        obs = [rng.gauss(0, 1) for _ in range(n)]
        d = decompose_crps(ens, obs)
        assert d.reliability / d.crps_mean < 0.15

    def test_biased_forecast_reliability_penalty(self):
        # Смещённый ансамбль: REL заметно больше, чем у калиброванного.
        rng = random.Random(12)
        n = 400
        ens_cal = [[rng.gauss(0, 1) for _ in range(20)] for _ in range(n)]
        ens_biased = [[x + 1.5 for x in e] for e in ens_cal]
        obs = [rng.gauss(0, 1) for _ in range(n)]
        d_cal = decompose_crps(ens_cal, obs)
        d_bias = decompose_crps(ens_biased, obs)
        assert d_bias.reliability > 10.0 * max(d_cal.reliability, 1e-12)
        assert d_bias.crps_mean > d_cal.crps_mean


class TestValidation:
    def test_empty_pool_rejected(self):
        with pytest.raises(ValueError, match="CRPS_DECOMP_EMPTY"):
            decompose_crps([], [])

    def test_length_mismatch_rejected(self):
        with pytest.raises(ValueError, match="CRPS_DECOMP_LENGTH_MISMATCH"):
            decompose_crps([[1.0, 2.0]], [1.0, 2.0])

    def test_heterogeneous_ensemble_rejected(self):
        with pytest.raises(ValueError, match="CRPS_DECOMP_HETEROGENEOUS"):
            decompose_crps([[1.0, 2.0], [1.0, 2.0, 3.0]], [1.5, 2.0])

    def test_empty_ensemble_rejected(self):
        with pytest.raises(ValueError, match="CRPS_DECOMP_EMPTY_ENSEMBLE"):
            decompose_crps([[]], [1.0])

    def test_result_flags(self):
        d = decompose_crps([[1.0, 2.0, 3.0]] * 5, [2.0] * 5)
        assert d.engine == ENGINE_ID
        assert d.production_ready is False
        assert d.n_cases == 5
        assert d.ensemble_size == 3
