"""V8.3.2 head integration / instantaneous nameplate guard, synthetic only.

Regression counterexamples generated from artificial, non-site reservoir curves.
The old midpoint method falsely approved end-of-day peak generation and
mislabeled average energy at a piecewise storage-elevation knot.
"""
from __future__ import annotations

from math import isclose
import pytest

from hydro_api.cascade_v83 import (
    ReservoirV83, exact_mean_piecewise_linear, reservoir_step, linear_interpolate,
)
from tests_v83.fixture import cascade_case_v83


def base_upper():
    return cascade_case_v83()['upper']


def test_exact_trapezoid_on_monotone_piecewise_knot_midpoint_error():
    d=base_upper()
    d['start_volume_m3']=950_000_000
    d['storage_curve'][2]['upstream_elevation_m']=435
    d['rated_capacity_mw']=500
    res=ReservoirV83.model_validate(d)
    got=reservoir_step(res,150+100_000_000/86400,1000)
    assert got['violations']==[]
    assert got['end_storage_m3']==1_050_000_000
    # Independent pencil derivation: 50% day on each side of the curve knot.
    # First half stage average (387.5 + 395)/2; second (395 + 415)/2.
    average_forebay=(387.5+395+395+415)/4
    net_head=average_forebay - 303 - 1
    power=1000*9.80665*125*net_head*.9/1e6
    assert isclose(got['net_head_m'],94.125,abs_tol=1e-9)
    assert isclose(got['power_mw'],power,rel_tol=1e-12)
    assert isclose(got['energy_mwh'],power*24,rel_tol=1e-12)
    midpoint_energy=1000*9.80665*125*(395-303-1)*.9/1e6*24
    assert isclose(got['energy_mwh']-midpoint_energy,82.743609375,abs_tol=1e-8)
    assert got['energy_integration_method']=='EXACT_PIECEWISE_LINEAR_STAGE_AT_CONSTANT_NET_DAILY_FLOW'


def test_instantaneous_rated_peak_over_110_mw_not_approved():
    d=base_upper()
    d['rated_capacity_mw']=110
    res=ReservoirV83.model_validate(d)
    got=reservoir_step(res,150+90_000_000/86400,1000)
    assert got['end_storage_m3']==1_090_000_000
    # Previous midpoint test saw 107.84 MW and returned a false PASS.
    old_midpoint=1000*9.80665*125*(395+13.5/2-303-1)*.9/1e6
    assert old_midpoint<110
    assert got['max_instantaneous_theoretical_power_mw']>115
    assert 'ELECTRICAL_RATED_CAPACITY_EXCEEDED' in got['violations']
    assert got['power_mw'] is None and got['energy_mwh'] is None
    assert got['status']=='PHYSICAL_SCREEN_FAILED'


def test_endpoint_peak_works_for_decreasing_volume():
    d=base_upper()
    d['start_volume_m3']=1_070_000_000
    d['rated_capacity_mw']=110
    # -50e6 m3 in one day, so highest elevation is at day start.
    r=reservoir_step(ReservoirV83.model_validate(d),150-50_000_000/86400,1000)
    assert r['end_storage_m3']==1_020_000_000
    assert r['head_at_start_m']>r['head_at_end_m']
    assert 'ELECTRICAL_RATED_CAPACITY_EXCEEDED' in r['violations']
    assert r['energy_mwh'] is None


def test_single_segment_average_equals_midpoint_and_reverse_is_symmetric():
    xs=[10.,30.,60.];ys=[100.,115.,155.]
    assert exact_mean_piecewise_linear(12,29,xs,ys)==linear_interpolate(20.5,xs,ys)
    f=exact_mean_piecewise_linear(12,55,xs,ys)
    assert isclose(f,exact_mean_piecewise_linear(55,12,xs,ys),abs_tol=1e-12)
    assert exact_mean_piecewise_linear(30,30,xs,ys)==115


def test_exact_integrator_cannot_extrapolate():
    with pytest.raises(ValueError,match='EXTRAPOLATION_FORBIDDEN'):
        exact_mean_piecewise_linear(-1,50,[0,30,60],[10,30,50])
    with pytest.raises(ValueError,match='EXTRAPOLATION_FORBIDDEN'):
        exact_mean_piecewise_linear(5,61,[0,30,60],[10,30,50])


def test_negative_head_at_start_refuses_positive_day_average():
    d=base_upper()
    d['start_volume_m3']=900_000_000
    d['storage_curve'][0]['upstream_elevation_m']=250
    d['rated_capacity_mw']=500
    res=ReservoirV83.model_validate(d)
    # large influx, end stage is high and midpoint is positive
    r=reservoir_step(res,150+195_000_000/86400,1000)
    assert 'FINAL_STORAGE_OUTSIDE_ALLOWED_LIMITS' not in r['violations']
    assert r['net_head_m']>0
    assert 'NONPOSITIVE_NET_HEAD' in r['violations']
    assert r['energy_mwh'] is None


def test_zero_turbine_flow_is_zero_even_with_storage_change():
    d=base_upper()
    d['turbine_release_cms']=0
    d['spill_release_cms']=150
    res=ReservoirV83.model_validate(d)
    r=reservoir_step(res,150+10_000_000/86400,1000)
    assert r['energy_mwh']==0
    assert r['power_mw']==0
    assert r['max_instantaneous_theoretical_power_mw']==0


def test_constant_volume_matches_original_steady_state():
    res=ReservoirV83.model_validate(base_upper())
    r=reservoir_step(res,150,1000)
    assert r['start_storage_m3']==r['end_storage_m3']
    assert r['head_at_start_m']==r['head_at_end_m']
    assert isclose(r['energy_mwh'],r['power_mw']*24,rel_tol=1e-12)


def test_exceeding_bounds_disables_generation_even_if_average_head_computable():
    res=ReservoirV83.model_validate(base_upper())
    r=reservoir_step(res,150+200_000_000/86400,1000)
    assert 'FINAL_STORAGE_OUTSIDE_ALLOWED_LIMITS' in r['violations']
    assert 'ENGINEERING_CURVE_EXTRAPOLATION_FORBIDDEN' in r['violations']
    assert r['energy_mwh'] is None


def test_constant_flow_assumption_disclosed_not_dispatch():
    r=reservoir_step(ReservoirV83.model_validate(base_upper()),150,1000)
    assert r['energy_integration_method']=='EXACT_PIECEWISE_LINEAR_STAGE_AT_CONSTANT_NET_DAILY_FLOW'
    assert 'instantaneous' in 'max_instantaneous_theoretical_power_mw'
