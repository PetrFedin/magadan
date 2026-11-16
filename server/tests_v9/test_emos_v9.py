"""Тесты EMOS-постобработки (emos_v9)."""
import math

import pytest

from hydro_api.emos_v9 import (
    EMOSFit,
    emos_predictive_quantiles,
    fit_emos_log,
    gaussian_crps,
)
from hydro_api.probabilistic_verification_v9 import crps_ensemble


def _det_series(n, seed=0.0):
    """Детерминированный псевдошум без random (воспроизводимость теста)."""
    return [math.sin(seed + 12.9898 * i) * 43758.5453 % 1.0 for i in range(n)]


class TestGaussianCRPS:
    def test_closed_form_matches_ensemble_form(self):
        # CRPS(N(0,1), 0.3) по замкнутой форме против эд. формы
        # на плотном квантильном ансамбле нормали.
        from statistics import NormalDist
        n = 2001
        dist = NormalDist()
        ens = [dist.inv_cdf((i + 0.5) / n) for i in range(n)]
        assert gaussian_crps(0.0, 1.0, 0.3) == pytest.approx(
            crps_ensemble(ens, 0.3), rel=1e-4)

    def test_sigma_nonpositive_fails(self):
        with pytest.raises(ValueError, match="EMOS_SIGMA_NONPOSITIVE"):
            gaussian_crps(0.0, 0.0, 1.0)
        with pytest.raises(ValueError, match="EMOS_SIGMA_NONPOSITIVE"):
            gaussian_crps(0.0, -1.0, 1.0)

    def test_nonfinite_fails(self):
        with pytest.raises(ValueError, match="EMOS_CRPS_NONFINITE"):
            gaussian_crps(float("nan"), 1.0, 0.0)


class TestFitEMOSLog:
    def test_insufficient_pairs_fail_closed(self):
        with pytest.raises(ValueError, match="EMOS_INSUFFICIENT_PAIRS"):
            fit_emos_log([[1.0, 2.0]] * 5, [1.5] * 5, min_pairs=10)

    def test_nonpositive_data_fail_closed(self):
        ens = [[1.0, 2.0, 3.0]] * 12
        obs = [1.5] * 12
        obs[3] = 0.0
        with pytest.raises(ValueError, match="EMOS_NONPOSITIVE_DATA"):
            fit_emos_log(ens, obs, min_pairs=10)
        bad_ens = [[1.0, -2.0, 3.0]] * 12
        with pytest.raises(ValueError, match="EMOS_NONPOSITIVE_DATA"):
            fit_emos_log(bad_ens, [1.5] * 12, min_pairs=10)

    def test_constant_series_fail_closed_not_converged(self):
        # Вырожденный случай: сигма уходит в ноль, симплекс не сходится —
        # отказ, а не тихий ответ.
        with pytest.raises(ArithmeticError, match="EMOS_FIT_NOT_CONVERGED"):
            fit_emos_log([[100.0, 100.0, 100.0]] * 20, [100.0] * 20,
                         min_pairs=10, max_iter=200)

    def test_recovers_location_bias(self):
        # Наблюдения систематически в 2 раза выше медианы ансамбля =>
        # подгонка в лог-шкале должна дать a > 0 при b ~ 1.
        noise = _det_series(60, seed=1.0)
        ens, obs = [], []
        for i in range(60):
            mb = math.log(100.0 + 10.0 * (i % 7))
            spread = 0.1
            ens.append([math.exp(mb + spread * (noise[(i + k) % 60] - 0.5) * 2)
                        for k in range(5)])
            obs.append(math.exp(mb + math.log(2.0) + 0.05 * (noise[i] - 0.5)))
        fit = fit_emos_log(ens, obs, min_pairs=10)
        assert fit.a == pytest.approx(math.log(2.0), abs=0.1)
        assert fit.b == pytest.approx(1.0, abs=0.15)
        assert fit.converged is True
        assert fit.production_ready is False

    def test_unknown_objective_fail_closed(self):
        with pytest.raises(ValueError, match="EMOS_UNKNOWN_OBJECTIVE"):
            fit_emos_log([[1.0, 2.0, 3.0]] * 12, [1.5] * 12,
                         min_pairs=10, objective="median")

    def test_determinism_bitwise(self):
        noise = _det_series(40, seed=2.0)
        ens = [[math.exp(4.0 + 0.2 * (noise[(i + k) % 40] - 0.5)) for k in range(6)]
               for i in range(40)]
        obs = [math.exp(4.0 + 0.15 * (noise[i] - 0.5)) for i in range(40)]
        f1 = fit_emos_log(ens, obs, min_pairs=10)
        f2 = fit_emos_log(ens, obs, min_pairs=10)
        assert f1.model_dump_json() == f2.model_dump_json()


class TestPredictiveQuantiles:
    def _fit(self):
        noise = _det_series(40, seed=3.0)
        ens = [[math.exp(5.0 + 0.3 * (noise[(i + k) % 40] - 0.5)) for k in range(8)]
               for i in range(40)]
        obs = [math.exp(5.0 + 0.35 * (noise[i] - 0.5)) for i in range(40)]
        return fit_emos_log(ens, obs, min_pairs=10), ens, obs

    def test_quantiles_sorted_positive_fixed_size(self):
        fit, ens, _obs = self._fit()
        q = emos_predictive_quantiles(fit, ens[0], m=20)
        assert len(q) == 20
        assert all(v > 0 for v in q)
        assert all(q[i] < q[i + 1] for i in range(19))

    def test_quantile_count_guard(self):
        fit, ens, _obs = self._fit()
        with pytest.raises(ValueError, match="EMOS_QUANTILE_COUNT"):
            emos_predictive_quantiles(fit, ens[0], m=1)

    def test_calibration_fixes_underdispersion_out_of_sample(self):
        # Ансамбль недооценивает разброс в 3 раза; EMOS, обученный на
        # прошлом, на НОВЫХ данных должен поднять покрытие 80%-интервала.
        # Проверяются обе постановки цели.
        noise = _det_series(240, seed=4.0)

        def make(i):
            base = math.exp(3.0 + 0.4 * math.sin(i * 0.05))
            true_sigma = 0.3
            ens_spread = 0.1  # в 3 раза уже истинного
            e = [base * math.exp(ens_spread * (noise[(i * 7 + k) % 240] - 0.5) * 2)
                 for k in range(10)]
            o = base * math.exp(true_sigma * (noise[(i * 13 + 3) % 240] - 0.5) * 2)
            return e, o

        train_ens, train_obs, test_ens, test_obs = [], [], [], []
        for i in range(120):
            e, o = make(i)
            (train_ens if i < 80 else test_ens).append(e)
            (train_obs if i < 80 else test_obs).append(o)
        from hydro_api.probabilistic_verification_v9 import interval_coverage
        raw_cov = interval_coverage(test_ens, test_obs, alpha=0.2)["empirical_coverage"]
        assert raw_cov < 0.55
        for objective in ("log", "original_scale"):
            fit = fit_emos_log(train_ens, train_obs, min_pairs=10,
                               objective=objective)
            assert fit.objective == objective
            emos_ens = [emos_predictive_quantiles(fit, e, m=20) for e in test_ens]
            emos_cov = interval_coverage(
                emos_ens, test_obs, alpha=0.2)["empirical_coverage"]
            assert emos_cov > raw_cov + 0.2, objective
            assert 0.6 <= emos_cov <= 1.0, objective
