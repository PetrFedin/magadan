"""Тесты turbine_reliability_v9: ISO 20816 зоны, Weibull MLE, E[C] (P1-4)."""
import math
import random

import pytest

from hydro_api.turbine_reliability_v9 import (
    VibrationZones,
    classify_vibration,
    fit_weibull_mle,
    maintenance_economics,
)


def _weibull_sample(beta, eta, n, seed):
    rng = random.Random(seed)
    return [eta * (-math.log(1.0 - rng.random())) ** (1.0 / beta) for _ in range(n)]


# --- ISO 20816 -----------------------------------------------------------

def test_zone_classification():
    z = VibrationZones(ab=2.8, bc=4.5, cd=7.1, unit="mm/s RMS")
    assert [classify_vibration(v, z) for v in [1.0, 3.5, 5.5, 9.0]] == ["A", "B", "C", "D"]
    assert classify_vibration(2.8, z) == "A"  # граница включена в нижнюю зону


def test_zone_boundaries_must_increase():
    with pytest.raises(ValueError, match="STRICTLY_INCREASING"):
        VibrationZones(ab=4.5, bc=2.8, cd=7.1, unit="mm/s RMS")


def test_vibration_value_validated():
    z = VibrationZones(ab=2.8, bc=4.5, cd=7.1, unit="mm/s RMS")
    with pytest.raises(ValueError, match="FINITE_NONNEGATIVE"):
        classify_vibration(-1.0, z)
    with pytest.raises(ValueError, match="FINITE_NONNEGATIVE"):
        classify_vibration(float("nan"), z)


# --- Weibull MLE ---------------------------------------------------------

def test_weibull_recovers_known_ifr():
    times = _weibull_sample(2.0, 10000.0, 200, seed=11)
    fit = fit_weibull_mle(times)
    assert fit.beta == pytest.approx(2.0, rel=0.15)
    assert fit.eta_hours == pytest.approx(10000.0, rel=0.10)


def test_weibull_recovers_known_dfr():
    times = _weibull_sample(0.7, 8000.0, 500, seed=11)
    fit = fit_weibull_mle(times)
    assert fit.beta == pytest.approx(0.7, rel=0.15)
    assert fit.eta_hours == pytest.approx(8000.0, rel=0.15)


def test_weibull_right_censoring():
    times = _weibull_sample(2.0, 10000.0, 200, seed=11)
    cens = [t > 15000.0 for t in times]
    fit = fit_weibull_mle([min(t, 15000.0) for t in times], censored=cens)
    assert fit.n_censored > 0
    assert fit.beta == pytest.approx(2.0, rel=0.20)


def test_weibull_cdf_reliability():
    times = _weibull_sample(2.0, 10000.0, 200, seed=11)
    fit = fit_weibull_mle(times)
    assert fit.cdf(0.0) == 0.0
    assert fit.cdf(fit.eta_hours) == pytest.approx(1.0 - math.exp(-1.0), rel=1e-9)
    assert fit.reliability(fit.eta_hours) == pytest.approx(math.exp(-1.0), rel=1e-9)


def test_weibull_input_validation():
    with pytest.raises(ValueError, match="NO_DATA"):
        fit_weibull_mle([])
    with pytest.raises(ValueError, match="POSITIVE_FINITE"):
        fit_weibull_mle([100.0, -5.0])
    with pytest.raises(ValueError, match="NO_UNCENSORED"):
        fit_weibull_mle([100.0, 200.0], censored=[True, True])


# --- E[C] и fail-closed ---------------------------------------------------

def test_maintenance_decision_hold_when_uncalibrated():
    times = _weibull_sample(2.0, 10000.0, 100, seed=5)
    fit = fit_weibull_mle(times)
    dec = maintenance_economics(
        fit, horizon_hours=8760.0,
        failure_loss_rub=50e6, preventive_cost_rub=3e6,
    )
    assert dec.decision == "HOLD"
    assert dec.probability_calibrated is False
    assert dec.production_ready is False


def test_maintenance_decision_threshold_when_calibrated():
    times = _weibull_sample(2.0, 10000.0, 100, seed=5)
    fit = fit_weibull_mle(times).model_copy(
        update={"calibrated_on_field_failures": True})
    dec = maintenance_economics(
        fit, horizon_hours=8760.0,
        failure_loss_rub=50e6, preventive_cost_rub=3e6,
    )
    expected = "PREVENTIVE" if fit.cdf(8760.0) * 50e6 > 3e6 else "RUN_TO_FAILURE"
    assert dec.decision == expected
    assert dec.probability_calibrated is True
