"""Тесты routing_v9: Маскингум / Маскингум-Кундж (P0-3)."""
import math

import pytest

from hydro_api.routing_v9 import (
    MuskingumParams,
    muskingum_coefficients,
    muskingum_cunge_params,
    route_muskingum,
)


def test_coefficients_sum_to_one():
    for k, x, dt in [(2.0, 0.2, 1.0), (6.0, 0.4, 5.0), (1.0, 0.0, 0.5)]:
        c0, c1, c2 = muskingum_coefficients(k, x, dt)
        assert c0 + c1 + c2 == pytest.approx(1.0, abs=1e-12)


def test_pure_translation_when_dt_equals_2kx():
    # K=dt, X=0.5 -> C0=C2=0, C1=1 -> чистая задержка на один шаг
    p = MuskingumParams(k_hours=1.0, x=0.5, dt_hours=1.0)
    r = route_muskingum([0.0, 10.0, 20.0, 5.0, 0.0, 0.0], p)
    assert r.outflow_m3s == [0.0, 0.0, 10.0, 20.0, 5.0, 0.0]


def test_peak_attenuation_and_lag():
    inflow = [100.0 + 900.0 * math.exp(-((t - 24) ** 2) / (2 * 8.0**2))
              for t in range(120)]
    p = MuskingumParams(k_hours=2.0, x=0.2, dt_hours=1.0)
    r = route_muskingum(inflow, p)
    assert r.peak_outflow_m3s < r.peak_inflow_m3s
    assert r.peak_lag_steps > 0
    assert r.mass_balance_rel_error < 1e-3


def test_constant_inflow_passes_unchanged():
    p = MuskingumParams(k_hours=3.0, x=0.3, dt_hours=2.0)  # band [1.8; 4.2]
    r = route_muskingum([500.0] * 50, p)
    assert all(abs(v - 500.0) < 1e-9 for v in r.outflow_m3s)


def test_negative_coefficients_rejected():
    with pytest.raises(ValueError, match="MUSKINGUM_NEGATIVE_COEFFICIENT"):
        MuskingumParams(k_hours=6.0, x=0.2, dt_hours=1.0)  # 2KX=2.4 > dt


def test_negative_inflow_rejected():
    p = MuskingumParams(k_hours=2.0, x=0.2, dt_hours=1.0)
    with pytest.raises(ValueError, match="ROUTING_INFLOW"):
        route_muskingum([100.0, -5.0, 100.0], p)


def test_muskingum_cunge_from_channel_geometry():
    p = muskingum_cunge_params(
        reach_length_m=20000.0, reference_discharge_m3s=800.0,
        channel_width_m=250.0, bed_slope=0.0004, manning_n=0.035,
        dt_hours=3.0,
    )
    assert p.k_hours > 0
    assert 0.0 <= p.x <= 0.5


def test_muskingum_cunge_dt_outside_band_rejected():
    with pytest.raises(ValueError, match="MC_DT_OUTSIDE_CLASSICAL_BAND"):
        muskingum_cunge_params(
            reach_length_m=20000.0, reference_discharge_m3s=800.0,
            channel_width_m=250.0, bed_slope=0.0004, manning_n=0.035,
            dt_hours=1.0,
        )


def test_fail_closed_flags():
    p = MuskingumParams(k_hours=2.0, x=0.2, dt_hours=1.0)
    r = route_muskingum([100.0, 300.0, 100.0], p)
    assert r.production_ready is False
    assert r.benchmarked_against_reference_solution is False
    assert r.source_id.startswith("SYNTHETIC")
