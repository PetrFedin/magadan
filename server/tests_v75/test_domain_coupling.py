"""Pure reproducible physics/cost tests: all values SYNTHETIC."""
import copy,json
from decimal import Decimal
from pathlib import Path
import pytest
from pydantic import ValidationError
from hydro_api.studies import ForecastCase,CascadeCase
from hydro_api.coupling_v75 import (ForecastCascadeBridge,couple_forecast_to_cascade,
    MaintenanceBridge,build_maintenance_decision,advance)
from hydro_api.studies import TurbineCase,turbine_deviation

S=json.loads((Path(__file__).parents[1]/'ui'/'samples_v72.json').read_text())

def forecast():return ForecastCase.model_validate(copy.deepcopy(S['hydroforecast']))
def cascade():return CascadeCase.model_validate(copy.deepcopy(S['cascade']))
def settings(**kw):return ForecastCascadeBridge.model_validate({'scenario':'point','step_hours':24,
    'travel_lag_steps':0,'hydrological_mapping_ref':'SYNTHETIC-HYDRO-MAPPING-V75',**kw})
def mplan():return {'planning_reference':'SYNTHETIC-MAINTENANCE-PLANNING-V75',
    'options':[{'option_id':'inspection','action':'inspection','materials_rub':'10000',
        'labor_rub':'25000','north_logistics_rub':'15000','outage_hours':'2',
        'downtime_value_rub_per_hour':'3000','lead_time_days':7,
        'basis_ref':'SYNTHETIC-INSPECTION-ESTIMATE-V75'},
        {'option_id':'planned-repair','action':'repair','materials_rub':'130000',
        'labor_rub':'40000','north_logistics_rub':'60000','outage_hours':'14',
        'downtime_value_rub_per_hour':'3000','lead_time_days':45,
        'basis_ref':'SYNTHETIC-REPAIR-ESTIMATE-V75'}]}


def test_contiguous_hindcast_couples_three_steps_and_mass_balance():
    r=couple_forecast_to_cascade(forecast(),cascade(),settings())
    assert r['status']=='LAB_MASS_BALANCE_OK'
    assert r['n_steps']==3
    assert [x['historical_forecast_cms'] for x in r['rows']]==[103,104,105]
    assert r['rows'][0]['upper']['final_storage_m3']==pytest.approx(700_000_000+(103-60)*86400)
    assert r['rows'][0]['lower']['inflow_cms']==pytest.approx(120)
    assert r['rows'][0]['lower']['final_storage_m3']==pytest.approx(700_000_000+(120-60)*86400)
    assert r['historic_actuals_used_for_hydraulic_input'] is False
    assert r['industrial_approval_eligible'] is False


def test_hindcast_actual_is_not_used_as_input():
    original=couple_forecast_to_cascade(forecast(),cascade(),settings())
    changed=copy.deepcopy(S['hydroforecast'])
    for x in changed['targets']:x['actual_cms']=9000
    rewritten=couple_forecast_to_cascade(ForecastCase.model_validate(changed),cascade(),settings())
    assert original==rewritten


def test_lower_and_upper_scenarios_change_storage_not_energy_under_fixed_release():
    lo=couple_forecast_to_cascade(forecast(),cascade(),settings(scenario='lower'))
    hi=couple_forecast_to_cascade(forecast(),cascade(),settings(scenario='upper'))
    assert lo['rows'][-1]['upper']['final_storage_m3']<hi['rows'][-1]['upper']['final_storage_m3']
    # constant fixed release and head => unchanged generation in this *limited* model
    assert lo['synthetic_total_energy_mwh']==hi['synthetic_total_energy_mwh']


def test_explicit_travel_lag_history_is_required_and_applied():
    with pytest.raises(ValidationError,match='TRAVEL_LAG_REQUIRES_EXPLICIT_HISTORY'):
        settings(travel_lag_steps=1)
    r=couple_forecast_to_cascade(forecast(),cascade(),settings(travel_lag_steps=1,arrival_history_cms=[25]))
    assert r['rows'][0]['lagged_arrival_cms']==25
    assert r['rows'][1]['lagged_arrival_cms']==60
    assert r['rows'][0]['lower']['inflow_cms']==85


def test_incompatible_hours_rejected():
    with pytest.raises(ValueError,match='STEP_HOURS'):
        couple_forecast_to_cascade(forecast(),cascade(),settings(step_hours=12))


def test_missing_or_duplicate_hydrological_timestamps_are_rejected():
    d=copy.deepcopy(S['hydroforecast']);d['targets'][1]['target_at']='2026-10-03T10:00:00+03:00'
    d['targets'][1]['truth_available_at']='2026-10-03T13:00:00+03:00'
    with pytest.raises(ValueError,match='NON_CONTIGUOUS'):
        couple_forecast_to_cascade(ForecastCase.model_validate(d),cascade(),settings())
    d=copy.deepcopy(S['hydroforecast']);d['targets'][1]['target_at']=d['targets'][0]['target_at']
    with pytest.raises(ValidationError,match='Duplicate forecast targets'):
        ForecastCase.model_validate(d)


def test_no_implicit_violation_removal():
    d=copy.deepcopy(S['cascade']);d['upper']['max_storage_m3']=705_000_000
    r=couple_forecast_to_cascade(forecast(),CascadeCase.model_validate(d),settings())
    assert r['status']=='LAB_CONSTRAINT_BREACH'
    assert any('FINAL_STORAGE_OUT_OF_BOUNDS' in x for x in r['constraint_violations'])


def test_boolean_time_and_invalid_source_ref_rejected():
    for bad in ({'step_hours':True},{'travel_lag_steps':True}, {'hydrological_mapping_ref':'REAL-DATA'}):
        with pytest.raises(ValidationError):settings(**bad)


def test_advance_reservoir_matches_integrated_balance_with_zero_losses():
    s=cascade().upper
    result=advance(s,s.initial_storage_m3,103,24)
    delta=(103-s.turbine_release_cms-s.spill_release_cms-s.other_losses_cms)*24*3600
    assert result['final_storage_m3']-result['initial_storage_m3']==pytest.approx(delta,abs=1e-3)


def test_maintenance_options_are_explainable_non_probabilistic():
    t=turbine_deviation(TurbineCase.model_validate(S['turbine']))
    d=build_maintenance_decision(t,MaintenanceBridge.model_validate(mplan()))
    assert d['calibrated_failure_probability'] is None
    assert d['auto_recommended_option_id'] is None
    assert d['expected_avoided_failure_cost_rub'] is None
    assert d['options'][0]['total_direct_plus_downtime_rub']=='56000.00'
    assert d['options'][1]['total_direct_plus_downtime_rub']=='272000.00'
    assert d['industrial_approval_eligible'] is False


def test_maintenance_no_baseless_recommendation_of_zero_cost_deferral():
    p=mplan()
    p['options'].append({'option_id':'defer','action':'defer','materials_rub':'0',
        'labor_rub':'0','north_logistics_rub':'0','outage_hours':'0',
        'downtime_value_rub_per_hour':'0','lead_time_days':0,
        'basis_ref':'SYNTHETIC-DEFERRAL-HYPOTHESIS-V75'})
    r=build_maintenance_decision(turbine_deviation(TurbineCase.model_validate(S['turbine'])),
                                  MaintenanceBridge.model_validate(p))
    assert r['auto_recommended_option_id'] is None
    assert any(x['action']=='defer' for x in r['options'])
    assert r['economic_comparison_completeness']=='DIRECT_COSTS_ONLY_NOT_LIFECYCLE_RISK'


def test_failure_probability_and_invalid_amounts_are_rejected():
    with pytest.raises(ValueError,match='UNSUPPORTED_FAILURE_PROBABILITY'):
        build_maintenance_decision({'status':'CHECK_SIGNAL','failure_probability':0.12},MaintenanceBridge.model_validate(mplan()))
    for bad in ('NaN', True,'-1'):
        p=mplan();p['options'][0]['labor_rub']=bad
        with pytest.raises((ValidationError,ValueError)):
            MaintenanceBridge.model_validate(p)


def test_maintenance_duplicate_option_and_fake_completed_deferral_denied():
    p=mplan();p['options'][1]['option_id']='inspection'
    with pytest.raises(ValidationError,match='DUPLICATE_MAINTENANCE_OPTION'):
        MaintenanceBridge.model_validate(p)
    p=mplan();p['options'][0]['action']='defer'
    with pytest.raises(ValidationError,match='DEFER_CANNOT_CLAIM'):
        MaintenanceBridge.model_validate(p)
