"""Scientific negative cases and independent arithmetic (not external solver)."""
from copy import deepcopy
from math import isclose
import pytest
from pydantic import ValidationError
from hydro_api.cascade_v83 import (
  CoupledCascadeV83, UniformTravelLagV83, route_uniform_day, evaluate_coupled_cascade_v83,
  linear_interpolate, reservoir_step, ReservoirV83, SECONDS_PER_DAY,
)
from tests_v83.fixture import cascade_case_v83


def calc(data=None):
    return evaluate_coupled_cascade_v83(CoupledCascadeV83.model_validate(data or cascade_case_v83()))


def test_forecast_single_target_day_and_three_physical_scenarios():
    r=calc()
    assert [s['name'] for s in r['scenarios']]==['dry','central','wet']
    assert r['hydrology_report']['horizon_days']==2
    assert r['forecast_actual_lead_to_target_day_start_hours']==14
    assert r['forecast_actual_lead_to_target_day_end_hours']==38
    assert r['target_day_end_utc']>r['target_day_start_utc']
    assert r['feasible_all_three_synthetic_scenarios']
    assert all(s['feasible_under_synthetic_constraints'] for s in r['scenarios'])
    assert all(s['total_energy_mwh']>0 for s in r['scenarios'])
    assert not r['eligible_for_financial_ledger']
    assert r['monetary_benefit_rub'] is None
    assert r['recommended_dispatch_cms'] is None
    assert not r['production_ready']


def test_independent_mass_balance_and_units():
    r=calc()
    for s in r['scenarios']:
        u,d,t=s['upper'],s['lower'],s['transit']
        # Independently rederive storage and transit in m3, without calling engine math.
        expected_u=s['upper_forecast_inflow_cms']*86400 - 150*86400
        assert isclose(u['delta_storage_m3'],expected_u,abs_tol=1e-3)
        assert isclose(d['delta_storage_m3'],(45+150-175)*86400,abs_tol=1e-3)
        expected_global=(s['upper_forecast_inflow_cms']+45-175)*86400
        actual_global=(u['delta_storage_m3']+d['delta_storage_m3']+
                       t['closing_in_transit_m3']-t['opening_in_transit_m3'])
        assert isclose(actual_global,expected_global,abs_tol=1e-3)
        assert abs(s['global_mass_balance_residual_m3'])<1e-4
        assert u['energy_mwh'] == u['power_mw']*24
        assert d['energy_mwh'] == d['power_mw']*24


def test_gravity_efficiency_and_elevation_curve_independent_power():
    r=calc()['scenarios'][1]['upper']
    mid=(r['start_storage_m3']+r['end_storage_m3'])/2
    forebay=395+(mid-1_000_000_000)*15/100_000_000
    tailwater=303
    expected_net_head=forebay-tailwater-1
    expected_power=1000*9.80665*125*expected_net_head*0.90/1_000_000
    assert isclose(r['net_head_m'],expected_net_head,abs_tol=1e-7)
    assert isclose(r['power_mw'],expected_power,rel_tol=1e-12)
    assert isclose(r['energy_mwh'],expected_power*24,rel_tol=1e-12)

@pytest.mark.parametrize('lag,history,arrival_weights',[
   (0,[],[1.]),(12,[100],[0.5,0.5]),(24,[100],[0,1]),
   (36,[100,60],[0,0.5,0.5]),(48,[100,60],[0,0,1]),
   (60,[100,60,20],[0,0,0.5,0.5]),(72,[100,60,20],[0,0,0,1]),
])
def test_fractional_travel_time_mass_balance(lag,history,arrival_weights):
    x=UniformTravelLagV83(delay_hours=lag,previous_daily_releases_cms=history,
                          source_ref='SYNTHETIC-TRAVEL-TIME-STRESS-2026')
    r=route_uniform_day(170,x)
    assert all(abs(a-b)<1e-12 for a,b in zip(r['coefficient_weights_current_then_history'],arrival_weights))
    expected=170*arrival_weights[0]+sum(a*b for a,b in zip(history,arrival_weights[1:]))
    assert isclose(r['arrival_mean_flow_cms'],expected,abs_tol=1e-8)
    assert isclose(r['closing_in_transit_m3'],r['opening_in_transit_m3']+
                   (170-expected)*86400,abs_tol=1e-5)


def test_volume_bounds_are_violations_not_silent_capping():
    d=cascade_case_v83();d['upper']['start_volume_m3']=1_090_000_000
    # Tight volume upper limit can be exceeded in some water-scenario branches.
    d['upper']['max_volume_m3']=1_091_000_000
    r=calc(d)
    assert not r['feasible_all_three_synthetic_scenarios']
    assert any('FINAL_STORAGE_OUTSIDE_ALLOWED_LIMITS' in '|'.join(s['violations'])
               for s in r['scenarios'])
    assert any(s['total_energy_mwh'] is None for s in r['scenarios'])
    assert r['scenario_energy_span_mwh'] is None


def test_no_extrapolation_even_when_already_infeasible():
    d=cascade_case_v83();d['upper']['turbine_release_cms']=90_000
    d['upper']['turbine_capacity_cms']=95_000
    d['upper']['max_daily_ramp_cms']=100_000
    r=calc(d)
    assert any('ENGINEERING_CURVE_EXTRAPOLATION_FORBIDDEN' in '|'.join(s['violations'])
               for s in r['scenarios'])
    assert all(s['upper']['energy_mwh'] is None for s in r['scenarios'])


def test_head_rated_capacity_violation_returns_no_energy():
    d=cascade_case_v83();d['upper']['rated_capacity_mw']=1
    r=calc(d)
    assert any('ELECTRICAL_RATED_CAPACITY_EXCEEDED' in '|'.join(s['violations'])
               for s in r['scenarios'])
    assert all(s['total_energy_mwh'] is None for s in r['scenarios'])


def test_low_min_release_and_ramp_are_prohibited():
    d=cascade_case_v83();d['upper']['minimum_release_cms']=151
    d['upper']['max_daily_ramp_cms']=0
    d['upper']['previous_release_cms']=140
    d['route']['previous_daily_releases_cms']=[140]
    r=calc(d)
    assert 'upper:MINIMUM_RELEASE_NOT_MET' in r['scenarios'][0]['violations']
    assert 'upper:RELEASE_RAMP_LIMIT_EXCEEDED' in r['scenarios'][0]['violations']


def test_one_day_forecast_cannot_be_stretched_into_multiday_path():
    d=cascade_case_v83();d['forecast']['horizon_days']=7
    with pytest.raises(ValidationError,match='EXACTLY_TWO_DAY_END_TIMESTAMP'):
        CoupledCascadeV83.model_validate(d)
    d=cascade_case_v83();d['forecast']['horizon_days']=1
    with pytest.raises(ValidationError,match='EXACTLY_TWO_DAY_END_TIMESTAMP'):
        CoupledCascadeV83.model_validate(d)


def test_cross_asset_misuse_not_allowed():
    d=cascade_case_v83();d['forecast']['asset_id']='other-upstream'
    with pytest.raises(ValidationError,match='FORECAST_MEASUREMENT_BOUNDARY'):
        CoupledCascadeV83.model_validate(d)
    d=cascade_case_v83();d['lower']['asset_id']='feeder-a'
    with pytest.raises(ValidationError,match='TWO_DISTINCT_SYNTHETIC_ASSETS_REQUIRED'):
        CoupledCascadeV83.model_validate(d)


def test_previous_discharge_mismatch_is_rejected():
    d=cascade_case_v83();d['route']['previous_daily_releases_cms']=[200]
    with pytest.raises(ValidationError,match='PREVIOUS_UPSTREAM_RELEASE_CONFLICTS'):
        CoupledCascadeV83.model_validate(d)


def test_untrusted_real_source_is_rejected():
    d=cascade_case_v83();d['upper']['source_ref']='real SCADA station 45'
    with pytest.raises(ValidationError):CoupledCascadeV83.model_validate(d)


def test_bad_stage_curve_and_bounds_are_rejected():
    d=cascade_case_v83();d['upper']['storage_curve'][1]['upstream_elevation_m']=380
    with pytest.raises(ValidationError,match='NONMONOTONE_STORAGE_ELEVATION_CURVE'):
        CoupledCascadeV83.model_validate(d)
    d=cascade_case_v83();d['lower']['min_volume_m3']=350_000_000
    with pytest.raises(ValidationError,match='RESERVOIR_LIMITS_OUTSIDE_SURVEYED_CURVE'):
        CoupledCascadeV83.model_validate(d)


def test_invalid_efficiency_curve_cannot_claim_generation():
    d=cascade_case_v83();d['upper']['efficiency_curve'][-1]['efficiency']=1.5
    with pytest.raises(ValidationError):CoupledCascadeV83.model_validate(d)


def test_lag_history_and_extrapolation_guard():
    d=cascade_case_v83();d['route']['previous_daily_releases_cms']=[]
    with pytest.raises(ValidationError,match='TRAVEL_LAG_HISTORY_LENGTH'):
        CoupledCascadeV83.model_validate(d)
    with pytest.raises(ValueError,match='EXTRAPOLATION_FORBIDDEN'):
        linear_interpolate(500,[0,100],[0,50])


def test_forecast_with_future_observation_is_not_accepted():
    d=cascade_case_v83()
    d['forecast']['observations'][-1]['available_at']='2026-07-01T00:00:00+00:00'
    with pytest.raises(ValidationError):CoupledCascadeV83.model_validate(d)


def test_report_is_deterministic_and_statistical_limits_preserved():
    first=calc();second=calc()
    assert first==second
    assert first['hydrology_report']['nominal_interval_fraction']==.9
    assert first['hydrology_report']['interval_is_probabilistic_scenario_weight'] is False
    assert first['data_source_attested'] is False
    assert first['actual_magadan_hydro_curve_used'] is False
    assert first['external_engineer_verified'] is False
    assert all('SYNTHETIC' in s['status'] or s['status']=='LAB_FEASIBLE_ONLY' for s in [first['scenarios'][0]['upper']])


def test_density_changes_power_linearly_not_storage_volume():
    d=cascade_case_v83()
    a=calc(d)
    d['water_density_kg_m3']=995
    b=calc(d)
    assert a['feasible_all_three_synthetic_scenarios']
    assert b['feasible_all_three_synthetic_scenarios']
    for i in range(3):
        for reservoir in ('upper','lower'):
            p=a['scenarios'][i][reservoir]['power_mw']
            other=b['scenarios'][i][reservoir]['power_mw']
            assert isclose(other/p,0.995,abs_tol=1e-12)
            assert isclose(a['scenarios'][i][reservoir]['end_storage_m3'],
                           b['scenarios'][i][reservoir]['end_storage_m3'],abs_tol=1e-6)


def test_zero_turbine_flow_returns_real_zero_not_missing_energy():
    d=cascade_case_v83()
    d['upper']['turbine_release_cms']=0
    d['upper']['spill_release_cms']=150
    r=calc(d)
    assert r['feasible_all_three_synthetic_scenarios']
    assert all(s['upper']['power_mw']==0 for s in r['scenarios'])
    assert all(s['upper']['energy_mwh']==0 for s in r['scenarios'])
    assert all(s['total_energy_mwh'] is not None for s in r['scenarios'])


def test_negative_net_head_never_emits_false_generation():
    d=cascade_case_v83()
    for row, elevation in zip(d['upper']['storage_curve'],[250,260,270]):
        row['upstream_elevation_m']=elevation
    r=calc(d)
    assert all('upper:NONPOSITIVE_NET_HEAD' in s['violations'] for s in r['scenarios'])
    assert all(s['upper']['energy_mwh'] is None for s in r['scenarios'])
    assert all(s['total_energy_mwh'] is None for s in r['scenarios'])


def test_global_mass_balance_does_not_mask_individual_violation():
    d=cascade_case_v83()
    d['upper']['minimum_release_cms']=190
    r=calc(d)
    assert all(abs(s['global_mass_balance_residual_m3'])<1e-4 for s in r['scenarios'])
    assert all(not s['feasible_under_synthetic_constraints'] for s in r['scenarios'])
    assert all(s['total_energy_mwh'] is None for s in r['scenarios'])


def test_future_storage_and_prior_release_are_explicit_scenario_assumptions():
    d=cascade_case_v83()
    result=calc(d)
    assert result['conditional_future_assumptions_flag']=='TARGET_START_STORAGE_AND_PREVIOUS_DAY_RELEASES_ARE_SCENARIO_INPUTS_NOT_MEASURED_AT_ISSUE'
    assert 'FUTURE portions' in ' '.join(result['limitations'])
    d.pop('target_start_state_and_prior_release_basis')
    with pytest.raises(ValidationError,match='target_start_state_and_prior_release_basis'):
        CoupledCascadeV83.model_validate(d)


def test_future_state_assumptions_cannot_be_mislabelled_observed():
    d=cascade_case_v83()
    d['target_start_state_and_prior_release_basis']='MEASURED_AS_OF_ISSUE'
    with pytest.raises(ValidationError,match='target_start_state_and_prior_release_basis'):
        CoupledCascadeV83.model_validate(d)
