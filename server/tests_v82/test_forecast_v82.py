from copy import deepcopy
from datetime import datetime,timedelta
from math import isclose
import pytest
from pydantic import ValidationError
from hydro_api.forecast_v82 import (DailyForecastResearchV82,evaluate_daily_forecast,
    MODEL_NAMES,predict,_scores)
from tests_v82.fixture import daily_flow_fixture,linear_flow_fixture


def run(sample):
    return evaluate_daily_forecast(DailyForecastResearchV82.model_validate(sample))


def test_statistically_separate_selection_calibration_and_holdout():
    r=run(daily_flow_fixture())
    assert r['split']['selection']==28
    assert r['split']['calibration']==28
    assert r['split']['holdout']==28
    assert r['split']['initial_history']==84
    assert set(r['model_selection_mae_cms'])==set(MODEL_NAMES)
    assert r['selected_model'] in MODEL_NAMES
    assert r['calibration']['order_statistic_1_based']==27
    assert len(r['holdout_rows'])==28
    assert r['valid_live_forecast'] is False
    assert r['industrial_decision_eligible'] is False
    assert r['commercial_or_energy_benefit_certified'] is False
    assert r['calibrated_real_world_flood_probability'] is None


def test_manual_linear_flow_independent_check_no_hidden_fit():
    d=linear_flow_fixture()
    r=run(d)
    assert r['selected_model']=='persistence'
    assert r['model_selection_mae_cms']['persistence']==1
    assert r['calibration']['absolute_error_radius_cms']==1
    assert r['holdout']['mae_cms']==1
    assert r['holdout']['interval_empirical_coverage_fraction']==1
    assert r['holdout']['interval_misses']==0
    assert r['forecast']['point_cms']==d['observations'][-1]['mean_flow_cms']
    assert r['forecast']['upper_cms']==r['forecast']['point_cms']+1
    assert r['holdout']['skill_vs_persistence_percent']==0


def test_changing_holdout_does_not_choose_or_calibrate_model():
    d=daily_flow_fixture(n=168)
    before=run(d)
    changed=deepcopy(d)
    for x in changed['observations'][-28:]:
        x['mean_flow_cms']+=32
    after=run(changed)
    assert before['selected_model']==after['selected_model']
    assert before['model_selection_mae_cms']==after['model_selection_mae_cms']
    assert before['calibration']==after['calibration']
    assert before['holdout']!=after['holdout']
    assert before['forecast']!=after['forecast']


def test_holdout_future_value_does_not_change_earlier_issued_point_forecast():
    d=daily_flow_fixture()
    before=run(d)
    changed=deepcopy(d)
    changed['observations'][-1]['mean_flow_cms']+=99
    after=run(changed)
    assert before['holdout_rows'][0]['point_cms']==after['holdout_rows'][0]['point_cms']
    assert before['holdout_rows'][-1]['point_cms']==after['holdout_rows'][-1]['point_cms']
    assert before['selected_model']==after['selected_model']
    assert before['calibration']==after['calibration']


def test_severe_shift_produces_watch_flags():
    r=run(daily_flow_fixture(regime_shift=65))
    assert 'EMPIRICAL_HOLDOUT_UNDERCOVERAGE' in r['risk_flags']
    assert r['holdout']['interval_empirical_coverage_fraction']<0.9
    assert r['forecast']['threshold_exceedance_probability'] is None


def test_zero_flow_not_falsely_normalized_as_zero_error_percentage():
    d=linear_flow_fixture(starting=0,step=0)
    r=run(d)
    assert r['holdout']['wape_percent'] is None
    assert r['persistence_holdout']['wape_percent'] is None
    assert r['calibration']['absolute_error_radius_cms']==0
    assert 'ZERO_CALIBRATION_ERROR_BAND_NOT_A_SAFETY_GUARANTEE' in r['risk_flags']
    assert r['holdout']['skill_vs_persistence_percent'] is None


def test_forecast_wide_horizons_correct_issuance_and_target():
    for horizon in range(1,8):
        d=daily_flow_fixture(horizon=horizon)
        r=run(d)
        last=datetime.fromisoformat(d['observations'][-1]['observed_at'])
        target=datetime.fromisoformat(r['forecast']['target_at'])
        assert target-last==timedelta(days=horizon)
        assert r['horizon_days']==horizon
        assert r['calibration']['sample_count']==28
        assert len(r['holdout_rows'])==28
        first_row=r['holdout_rows'][0]
        assert (datetime.fromisoformat(first_row['target_at'])-
                datetime.fromisoformat(first_row['issued_at']))==timedelta(days=horizon,hours=-10)
        assert r['actual_forecast_lead_hours']==24*horizon-10


def test_prediction_uses_only_end_index():
    a=[float(i) for i in range(50)]
    for m in MODEL_NAMES:
        x=predict(m,a,20)
        b=a[:21]+[2000.0]*29
        assert predict(m,b,20)==x


def test_missing_day_or_duplicate_day_blocked():
    d=daily_flow_fixture()
    d['observations'].pop(24)
    with pytest.raises(ValidationError,match='MISSING_OR_DUPLICATE_DAILY_OBSERVATION'):
        DailyForecastResearchV82.model_validate(d)
    d=daily_flow_fixture()
    d['observations'][11]['observed_at']=d['observations'][10]['observed_at']
    d['observations'][11]['available_at']=d['observations'][10]['available_at']
    with pytest.raises(ValidationError,match='MISSING_OR_DUPLICATE_DAILY_OBSERVATION'):
        DailyForecastResearchV82.model_validate(d)


def test_daylight_23_hour_day_invalid_even_when_local_clock_shifts():
    d=daily_flow_fixture()
    dt=datetime.fromisoformat(d['observations'][10]['observed_at'])
    d['observations'][10]['observed_at']=(dt-timedelta(hours=1)).isoformat()
    with pytest.raises(ValidationError,match='DAILY_OBSERVATION_MUST_BE_UTC_MIDNIGHT'):
        DailyForecastResearchV82.model_validate(d)


def test_future_source_availability_blocked():
    d=daily_flow_fixture()
    i=12
    date=datetime.fromisoformat(d['observations'][i]['observed_at'])
    d['observations'][i]['available_at']=(date+timedelta(days=2)).isoformat()
    with pytest.raises(ValidationError,match='DAILY_FLOW_AVAILABILITY_INVALID'):
        DailyForecastResearchV82.model_validate(d)


def test_current_as_of_stale_or_before_availability_blocked():
    d=daily_flow_fixture()
    last=datetime.fromisoformat(d['observations'][-1]['observed_at'])
    d['as_of']=(last+timedelta(days=5)).isoformat()
    with pytest.raises(ValidationError,match='AS_OF_NOT_FRESH'):
        DailyForecastResearchV82.model_validate(d)
    d=daily_flow_fixture()
    d['as_of']=(last+timedelta(hours=1)).isoformat()
    with pytest.raises(ValidationError,match='AS_OF_NOT_FRESH'):
        DailyForecastResearchV82.model_validate(d)


def test_unaware_timestamp_blocked_and_timezone_offset_normalized():
    d=daily_flow_fixture()
    d['as_of']=d['as_of'].replace('+00:00','')
    with pytest.raises(ValidationError,match='FORECAST_TIMEZONE_REQUIRED'):
        DailyForecastResearchV82.model_validate(d)
    d=daily_flow_fixture()
    d['observations'][15]['observed_at']=d['observations'][15]['observed_at'].replace('00:00:00+00:00','03:00:00+03:00')
    assert run(d)['observations']==168


def test_nan_infinity_negative_and_bool_rejected():
    for value in [float('nan'),float('inf'),-1,True]:
        d=daily_flow_fixture()
        d['observations'][10]['mean_flow_cms']=value
        with pytest.raises(ValidationError):DailyForecastResearchV82.model_validate(d)
    d=daily_flow_fixture();d['horizon_days']=True
    with pytest.raises(ValidationError):DailyForecastResearchV82.model_validate(d)


def test_synthetic_scope_is_strict():
    d=daily_flow_fixture();d['scope']='REAL_MAGADAN_RUS_HYDRO';
    with pytest.raises(ValidationError):DailyForecastResearchV82.model_validate(d)
    d=daily_flow_fixture();d['observations'][0]['source_ref']='ACTUAL_GAUGES_NAGO'
    with pytest.raises(ValidationError):DailyForecastResearchV82.model_validate(d)


def test_undocumented_new_fields_forbidden():
    d=daily_flow_fixture();d['emergency_spill_approval']=True
    with pytest.raises(ValidationError):DailyForecastResearchV82.model_validate(d)


def test_forecast_reproducible_and_nonmutating():
    d=daily_flow_fixture();original=deepcopy(d)
    assert run(d)==run(d)
    assert d==original


def test_horizon_alpha_bounds():
    for key,val in [('horizon_days',0),('horizon_days',8),('miscoverage_alpha',0.01),('miscoverage_alpha',0.4)]:
        d=daily_flow_fixture();d[key]=val
        with pytest.raises(ValidationError):DailyForecastResearchV82.model_validate(d)


def test_holdout_row_coverage_matches_aggregate():
    r=run(daily_flow_fixture())
    rows=r['holdout_rows']
    assert round(sum(z['inside_band'] for z in rows)/len(rows),6)==r['holdout']['interval_empirical_coverage_fraction']
    assert all(row['lower_cms']<=row['point_cms']<=row['upper_cms'] for row in rows)


def test_no_bering_or_unverified_probability_claims():
    r=run(daily_flow_fixture())
    assert 'беринг' not in repr(r).lower()
    assert 'bering' not in repr(r).lower()
    assert r['forecast']['threshold_exceedance_probability'] is None
    assert r['risk_flags']


def test_daily_volume_conversion_is_one_target_day_not_horizon_total():
    r=run(linear_flow_fixture(horizon=7))
    f=r['forecast']
    v=f['daily_volume_million_m3']
    assert v['basis']=='ONE_TARGET_DAY_OF_86400_SECONDS_NOT_HORIZON_TOTAL'
    assert v['point']==round(f['point_cms']*86400/1_000_000,6)
    assert v['lower']==round(f['lower_cms']*86400/1_000_000,6)
    assert v['upper']==round(f['upper_cms']*86400/1_000_000,6)
    assert r['holdout']['mae_target_day_volume_million_m3']==round(r['holdout']['mae_cms']*86400/1_000_000,6)
    assert r['reservoir_rules_and_cascade_mapping_verified'] is False


def test_historical_origin_rejects_measurement_available_after_issuance():
    d=daily_flow_fixture()
    at=datetime.fromisoformat(d['observations'][45]['observed_at'])
    d['observations'][45]['available_at']=(at+timedelta(hours=11)).isoformat()
    # Individual observation is within allowed +12 h availability, but the
    # 10 h forecast origin cannot have used it.
    with pytest.raises(ValidationError,match='HISTORICAL_ORIGIN_FEATURE_NOT_YET_AVAILABLE_AT_ISSUE'):
        DailyForecastResearchV82.model_validate(d)


def test_issued_at_matches_origin_in_every_backtest_row():
    r=run(daily_flow_fixture(horizon=4))
    assert r['daily_issuance_offset_hours']==10
    for row in r['holdout_rows']:
        issue=datetime.fromisoformat(row['issued_at'])
        target=datetime.fromisoformat(row['target_at'])
        assert target-issue==timedelta(hours=r['actual_forecast_lead_hours'])
