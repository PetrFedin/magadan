"""V8.2: causal-time-aware synthetic daily streamflow forecasting research.

Research evidence only. This does not forecast a real Magadan reservoir, issue
flood warnings, calibrate an operating rule, or demonstrate guaranteed coverage.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from math import ceil, fsum, sqrt
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ENGINE_TAG = 'v82-synthetic-daily-origin-calibration-v1'
MODEL_NAMES = ('persistence', 'rolling_mean_3', 'rolling_mean_7')
SELECTION_DAYS = 28
CALIBRATION_DAYS = 28
HOLDOUT_DAYS = 28

class StrictForecast(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


def _utc(v:datetime)->datetime:
    if v.tzinfo is None or v.utcoffset() is None:
        raise ValueError('FORECAST_TIMEZONE_REQUIRED')
    return v.astimezone(timezone.utc)


class DailyFlowObservation(StrictForecast):
    observed_at: datetime
    available_at: datetime
    mean_flow_cms: float = Field(ge=0, le=100000)
    source_ref: str = Field(min_length=20, max_length=120,
        pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')

    @field_validator('mean_flow_cms', mode='before')
    @classmethod
    def reject_bool(cls,v):
        if type(v) is bool: raise ValueError('BOOLEAN_IS_NOT_FLOW')
        return v

    @model_validator(mode='after')
    def when_known(self):
        start=_utc(self.observed_at)
        known=_utc(self.available_at)
        if start.time() != datetime.min.time():
            raise ValueError('DAILY_OBSERVATION_MUST_BE_UTC_MIDNIGHT')
        if not start <= known <= start+timedelta(hours=12):
            raise ValueError('DAILY_FLOW_AVAILABILITY_INVALID')
        return self


class DailyForecastResearchV82(StrictForecast):
    scope:Literal['SYNTHETIC_HYDROFORECAST_RESEARCH']='SYNTHETIC_HYDROFORECAST_RESEARCH'
    asset_id:str=Field(min_length=2,max_length=120)
    as_of:datetime
    horizon_days:int=Field(ge=1,le=7)
    miscoverage_alpha:float=Field(ge=0.05,le=0.25)
    observations:list[DailyFlowObservation]=Field(min_length=112,max_length=730)
    monitor_threshold_cms:float|None=Field(default=None,ge=0,le=100000)
    @field_validator('horizon_days','miscoverage_alpha','monitor_threshold_cms',mode='before')
    @classmethod
    def reject_bool_inputs(cls,v):
        if type(v) is bool:raise ValueError('BOOLEAN_NOT_ALLOWED_FOR_FORECAST_SETTING')
        return v

    @model_validator(mode='after')
    def chronological(self):
        dates=[_utc(o.observed_at) for o in self.observations]
        if any(b-a!=timedelta(days=1) for a,b in zip(dates,dates[1:])):
            raise ValueError('MISSING_OR_DUPLICATE_DAILY_OBSERVATION')
        asof=_utc(self.as_of)
        if not _utc(self.observations[-1].available_at)<=asof<dates[-1]+timedelta(days=1):
            raise ValueError('AS_OF_NOT_FRESH_OR_BEFORE_LAST_OBSERVATION_AVAILABILITY')
        if any(_utc(p.available_at)>asof for p in self.observations):
            raise ValueError('FUTURE_INFORMATION_LEAKAGE_IN_FLOW_SERIES')
        # Every historical origin has the SAME issuance time-of-day as the
        # requested final forecast, otherwise a backtest may silently use a
        # fresher measurement than was available at its issue timestamp.
        issue_offset=asof-dates[-1]
        if any(_utc(p.available_at)-d>issue_offset
               for p,d in zip(self.observations,dates)):
            raise ValueError('HISTORICAL_ORIGIN_FEATURE_NOT_YET_AVAILABLE_AT_ISSUE')
        return self


def predict(model:str,history:list[float],end_index:int)->float:
    """Only values with index <=end_index are visible; no future training."""
    if end_index<6:raise ValueError('INSUFFICIENT_HISTORY_FOR_COMPARABLE_MODEL')
    if model=='persistence': return history[end_index]
    if model=='rolling_mean_3':return fsum(history[end_index-2:end_index+1])/3
    if model=='rolling_mean_7':return fsum(history[end_index-6:end_index+1])/7
    raise ValueError('UNKNOWN_FORECAST_MODEL')


def _quantile_linear(items:list[float],prob:float)->float:
    if not items:raise ValueError('EMPTY_QUANTILE_SAMPLE')
    sorted_items=sorted(items)
    position=(len(sorted_items)-1)*prob
    lo=int(position);hi=min(lo+1,len(sorted_items)-1)
    weight=position-lo
    return sorted_items[lo]*(1-weight)+sorted_items[hi]*weight


def _scores(actual:list[float],pred:list[float])->dict:
    if not actual or len(actual)!=len(pred):raise ValueError('FORECAST_METRIC_GRAIN_MISMATCH')
    errs=[p-a for a,p in zip(actual,pred)]
    n=len(errs)
    denom=fsum(actual)
    return {
      'count':n,
      'mae_cms':round(fsum(map(abs,errs))/n,6),
      'rmse_cms':round(sqrt(fsum(x*x for x in errs)/n),6),
      'bias_cms':round(fsum(errs)/n,6),
      'wape_percent':None if denom<=0 else round(100*fsum(map(abs,errs))/denom,6),
    }


def evaluate_daily_forecast(case:DailyForecastResearchV82)->dict:
    series=[x.mean_flow_cms for x in case.observations]
    dates=[_utc(x.observed_at) for x in case.observations]
    issue_offset=_utc(case.as_of)-dates[-1]
    lead_hours=case.horizon_days*24-issue_offset.total_seconds()/3600
    n=len(series);h=case.horizon_days
    selection=range(n-84,n-56)
    calibration=range(n-56,n-28)
    holdout=range(n-28,n)

    def projection(name, target_indices):
        return [predict(name,series,t-h) for t in target_indices]

    selected_actual=[series[i] for i in selection]
    selection_table={name:_scores(selected_actual,projection(name,selection))
                     for name in MODEL_NAMES}
    selected=min(MODEL_NAMES,key=lambda name:(selection_table[name]['mae_cms'],MODEL_NAMES.index(name)))
    calibration_abs=[abs(series[i]-p) for i,p in zip(calibration,projection(selected,calibration))]
    k=ceil((len(calibration_abs)+1)*(1-case.miscoverage_alpha))
    if k>len(calibration_abs):raise ValueError('INSUFFICIENT_CALIBRATION_SAMPLES_FOR_ALPHA')
    radius=sorted(calibration_abs)[k-1]
    calibration_pred=projection(selected,calibration)
    calibration_errors=[p-series[i] for i,p in zip(calibration,calibration_pred)]
    calibration_bias=fsum(calibration_errors)/len(calibration_errors)
    calibration_mae=fsum(map(abs,calibration_errors))/len(calibration_errors)

    pred=projection(selected,holdout)
    actual=[series[i] for i in holdout]
    low=[max(0,p-radius) for p in pred]
    high=[p+radius for p in pred]
    hit=[l<=a<=u for a,l,u in zip(actual,low,high)]
    bench=projection('persistence',holdout)
    score=_scores(actual,pred)
    residual=[p-a for p,a in zip(pred,actual)]
    # Diagnostic lag correlation is not a p-value or proof of independence.
    def lag1(xs):
        first=xs[:-1];second=xs[1:]
        m1=fsum(first)/len(first);m2=fsum(second)/len(second)
        num=fsum((x-m1)*(y-m2) for x,y in zip(first,second))
        den1=fsum((x-m1)**2 for x in first)
        den2=fsum((y-m2)**2 for y in second)
        return None if den1<=1e-18 or den2<=1e-18 else round(num/sqrt(den1*den2),6)
    score['held_out_lag1_residual_correlation']=lag1(residual)
    score['calibration_to_holdout_bias_delta_cms']=round(score['bias_cms']-calibration_bias,6)
    benchmark=_scores(actual,bench)
    base_mae=benchmark['mae_cms']
    score['skill_vs_persistence_percent']=(None if base_mae==0 else
                round(100*(1-score['mae_cms']/base_mae),6))
    score['interval_empirical_coverage_fraction']=round(fsum(hit)/len(hit),6)
    score['interval_mean_width_cms']=round(fsum(u-l for l,u in zip(low,high))/len(low),6)
    score['interval_misses']=len(hit)-sum(hit)
    score['mae_target_day_volume_million_m3']=round(score['mae_cms']*86400/1_000_000,6)
    tail_threshold=_quantile_linear(series[:n-28],0.9)
    tails=[j for j,a in enumerate(actual) if a>=tail_threshold]
    score['high_flow_reference_p90_cms']=round(tail_threshold,6)
    score['high_flow_holdout_count']=len(tails)
    score['high_flow_holdout_mae_cms']=(None if not tails else round(
        fsum(abs(actual[i]-pred[i]) for i in tails)/len(tails),6))
    score['high_flow_holdout_coverage_fraction']=(None if not tails else round(
        fsum(hit[i] for i in tails)/len(tails),6))

    future=predict(selected,series,n-1)
    f_low=max(0,future-radius)
    f_high=future+radius
    warnings=['NO_REAL_HYDROLOGICAL_OBSERVATIONS',
              'TIME_SERIES_DEPENDENCE_NO_DISTRIBUTION_FREE_COVERAGE_GUARANTEE',
              'NONSTATIONARITY_AND_EXTREME_EVENTS_NOT_CALIBRATED',
              'NO_EXTERNAL_WEATHER_OR_SNOWPACK_DRIVERS']
    if score['interval_empirical_coverage_fraction']<1-case.miscoverage_alpha:
        warnings.append('EMPIRICAL_HOLDOUT_UNDERCOVERAGE')
    if score['held_out_lag1_residual_correlation'] is not None and abs(score['held_out_lag1_residual_correlation'])>0.3:
        warnings.append('POTENTIAL_SERIAL_CORRELATION_IN_HOLDOUT_ERRORS')
    if len(tails)<5:
        warnings.append('HIGH_FLOW_EXTREMES_NOT_SUFFICIENTLY_SAMPLED')
    if radius<=1e-12:
        warnings.append('ZERO_CALIBRATION_ERROR_BAND_NOT_A_SAFETY_GUARANTEE')
    if score['skill_vs_persistence_percent'] is not None and score['skill_vs_persistence_percent']<=0:
        warnings.append('NO_GAIN_OVER_PERSISTENCE_ON_INDEPENDENT_HOLDOUT')
    if case.monitor_threshold_cms is not None and f_high>=case.monitor_threshold_cms:
        warnings.append('SYNTHETIC_THRESHOLD_POTENTIALLY_CROSSED_NOT_AN_ALARM')
    records=[{
       'target_at':dates[i].isoformat(),
       'issued_at':(dates[i-h]+issue_offset).isoformat(),
       'actual_cms':round(series[i],6),'point_cms':round(p,6),
       'lower_cms':round(l,6),'upper_cms':round(u,6),
       'persistence_cms':round(b,6),'inside_band':bool(ok),
    } for i,p,l,u,b,ok in zip(holdout,pred,low,high,bench,hit)]
    return {
       'scope':'SYNTHETIC_HYDROFORECAST_RESEARCH_ONLY',
       'method':ENGINE_TAG,'issued_at':_utc(case.as_of).isoformat(),
       'asset_id':case.asset_id,'observations':n,
       'horizon_days':h,'actual_forecast_lead_hours':round(lead_hours,6),
       'daily_issuance_offset_hours':round(issue_offset.total_seconds()/3600,6),
       'cadence':'DAILY_UTC_MEAN_FLOW_CMS',
       'split':{
          'initial_history':n-84,'selection':SELECTION_DAYS,
          'calibration':CALIBRATION_DAYS,'holdout':HOLDOUT_DAYS,
          'selection_start':dates[n-84].date().isoformat(),
          'calibration_start':dates[n-56].date().isoformat(),
          'holdout_start':dates[n-28].date().isoformat(),
       },
       'model_selection_mae_cms':{k:v['mae_cms'] for k,v in selection_table.items()},
       'selected_model':selected,
       'calibration':{
         'method':'SPLIT_ABSOLUTE_RESIDUAL_RANK_NOT_TIME_SERIES_COVERAGE_PROOF',
         'nominal_band_fraction':round(1-case.miscoverage_alpha,6),
         'order_statistic_1_based':k,'sample_count':len(calibration_abs),
         'absolute_error_radius_cms':round(radius,6),
         'mean_absolute_calibration_error_cms':round(calibration_mae,6),
         'mean_signed_calibration_error_cms':round(calibration_bias,6),
         'calibration_lag1_residual_correlation':lag1(calibration_errors),
       },
       'holdout':score,'persistence_holdout':benchmark,
       'forecast':{
         'target_at':(dates[-1]+timedelta(days=h)).isoformat(),
         'point_cms':round(future,6),'lower_cms':round(f_low,6),'upper_cms':round(f_high,6),
         'monitor_threshold_cms':case.monitor_threshold_cms,
         'threshold_exceedance_probability':None,
         'daily_volume_million_m3':{
            'lower':round(f_low*86400/1_000_000,6),
            'point':round(future*86400/1_000_000,6),
            'upper':round(f_high*86400/1_000_000,6),
            'basis':'ONE_TARGET_DAY_OF_86400_SECONDS_NOT_HORIZON_TOTAL',
         },
         'band_is_operational_threshold':False,
       },
       'holdout_rows':records,
       'risk_flags':warnings,
       'research_qualification':'REQUIRES_MORE_INDEPENDENT_VALIDATION' if (
            score['interval_empirical_coverage_fraction']<1-case.miscoverage_alpha
            or score['skill_vs_persistence_percent'] is None
            or score['skill_vs_persistence_percent']<=0
            or len(tails)<5
       ) else 'LIMITED_HISTORICAL_SCREEN_PASSED_NOT_FIELD_CERTIFIED',
       'valid_live_forecast':False,
       'calibrated_real_world_flood_probability':None,
       'industrial_decision_eligible':False,
       'commercial_or_energy_benefit_certified':False,
       'reservoir_rules_and_cascade_mapping_verified':False,
    }
