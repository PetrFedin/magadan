"""V7.9 post-project M&V *simulation* with temporal training separation.

Counterfactual baseline rates are estimated from synthetic PRE-commissioning data,
then evaluated on synthetic POST conditions. No causal attribution or field signoff.
"""
from __future__ import annotations
from datetime import datetime, timezone
from math import isfinite
from typing import Literal
import numpy as np
from pydantic import Field, field_validator, model_validator
from .radial_grid import Strict


def aware_utc(v):
    if not isinstance(v, datetime) or v.tzinfo is None or v.utcoffset() is None:
        raise ValueError('TIMEZONE_AWARE_TIMESTAMP_REQUIRED')
    return v.astimezone(timezone.utc)


class LossObservation(Strict):
    started_at: datetime
    available_at: datetime
    duration_hours: float = Field(gt=0, le=168)
    mean_delivered_load_mw: float = Field(ge=0, le=1000)
    mean_ambient_temperature_c: float = Field(ge=-80, le=70)
    metered_loss_kwh: float = Field(ge=0, le=1e10)
    source_ref: str = Field(min_length=20, max_length=150,
                            pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')

    @field_validator('duration_hours','mean_delivered_load_mw','mean_ambient_temperature_c','metered_loss_kwh',mode='before')
    @classmethod
    def no_boolean(cls,v):
        if isinstance(v,bool):raise ValueError('BOOLEAN_IS_NOT_MEASUREMENT')
        return v

    @model_validator(mode='after')
    def available(self):
        end=self.started_at.timestamp() + 3600*self.duration_hours
        if aware_utc(self.available_at).timestamp() + 1e-6 < end:
            raise ValueError('MEASUREMENT_AVAILABLE_BEFORE_WINDOW_END')
        return self


class MVScreenV79(Strict):
    scope: Literal['SYNTHETIC_MV_RESEARCH_NO_REALIZED_SAVINGS'] = 'SYNTHETIC_MV_RESEARCH_NO_REALIZED_SAVINGS'
    asset_id: str = Field(min_length=1, max_length=120)
    commissioned_at: datetime
    report_as_of: datetime
    baseline: list[LossObservation] = Field(min_length=32, max_length=250)
    post: list[LossObservation] = Field(min_length=8, max_length=250)
    measurement_boundary_ref: str = Field(min_length=20, max_length=160,
                                          pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')
    adjustment_description: str = Field(min_length=90, max_length=1600)

    @model_validator(mode='after')
    def chronology(self):
        commission=aware_utc(self.commissioned_at)
        asof=aware_utc(self.report_as_of)
        if commission>=asof:raise ValueError('REPORT_MUST_FOLLOW_COMMISSIONING')
        def valid_series(items,label):
            times=[aware_utc(r.started_at) for r in items]
            if times != sorted(times) or len(times)!=len(set(times)):
                raise ValueError(label+'_TIMELINE_NOT_ORDERED_OR_DUPLICATE')
            for i,r in enumerate(items):
                end=times[i].timestamp() + 3600*r.duration_hours
                if i+1<len(items) and end>times[i+1].timestamp()+1e-6:
                    raise ValueError(label+'_MEASUREMENT_INTERVAL_OVERLAP')
            return times
        base=valid_series(self.baseline,'BASELINE')
        aft=valid_series(self.post,'POST')
        if (any(t.timestamp()+3600*x.duration_hours>commission.timestamp()+1e-6
                for t,x in zip(base,self.baseline))
                or any(aware_utc(x.available_at)>commission for x in self.baseline)):
            raise ValueError('BASELINE_USES_POST_COMMISSIONING_INFORMATION')
        if (any(t<=commission or t.timestamp()+3600*x.duration_hours>asof.timestamp()+1e-6
                for t,x in zip(aft,self.post))
                or any(aware_utc(x.available_at)>asof for x in self.post)):
            raise ValueError('POST_PERIOD_OUTSIDE_REPORT_TIME')
        return self


def _features(obs):
    p=obs.mean_delivered_load_mw / 10.0
    t=obs.mean_ambient_temperature_c / 30.0
    return [1.0, p, p*p, t]


def evaluate_mv_screen(case:MVScreenV79)->dict:
    b=case.baseline;post=case.post
    train_n=max(24,int(len(b)*0.75))
    if len(b)-train_n<8:raise ValueError('MINIMUM_CHRONOLOGICAL_HOLDOUT_REQUIRED')
    xt=np.array([_features(r) for r in b[:train_n]],dtype=float)
    yt=np.array([r.metered_loss_kwh/r.duration_hours for r in b[:train_n]],dtype=float)
    xv=np.array([_features(r) for r in b[train_n:]],dtype=float)
    yv=np.array([r.metered_loss_kwh/r.duration_hours for r in b[train_n:]],dtype=float)
    xp=np.array([_features(r) for r in post],dtype=float)
    rank=int(np.linalg.matrix_rank(xt))
    condition=float(np.linalg.cond(xt))
    if rank<4 or not isfinite(condition) or condition>1e7:
        raise ValueError('BASELINE_FEATURES_NOT_IDENTIFIABLE')
    beta=np.linalg.lstsq(xt,yt,rcond=None)[0]
    predicted_val=xv@beta
    predicted_post=xp@beta
    if np.min(predicted_post)<-1e-7 or np.min(predicted_val)<-1e-7:
        raise ValueError('NEGATIVE_COUNTERFACTUAL_OUTSIDE_MODEL_SCOPE')
    # Conservative support check in ORIGINAL covariates, not the observed losses.
    load=[z.mean_delivered_load_mw for z in b[:train_n]]
    temp=[z.mean_ambient_temperature_c for z in b[:train_n]]
    tol=1e-9
    out_of_domain=[i for i,z in enumerate(post) if
                   z.mean_delivered_load_mw < min(load)-tol or
                   z.mean_delivered_load_mw > max(load)+tol or
                   z.mean_ambient_temperature_c < min(temp)-tol or
                   z.mean_ambient_temperature_c > max(temp)+tol]
    if out_of_domain:
        raise ValueError('POST_CONDITIONS_OUT_OF_BASELINE_SUPPORT:'+','.join(map(str,out_of_domain[:8])))
    val_mae=float(np.mean(np.abs(predicted_val-yv)))
    val_bias=float(np.mean(predicted_val-yv))
    val_rmse=float(np.sqrt(np.mean((predicted_val-yv)**2)))
    actual=np.array([z.metered_loss_kwh for z in post],dtype=float)
    hours=np.array([z.duration_hours for z in post],dtype=float)
    counterfactual=np.maximum(predicted_post,0)*hours
    difference=counterfactual-actual
    # The same physical effect may be explained by unobserved confounding.
    return {
       'status':'SYNTHETIC_COUNTERFACTUAL_RESEARCH_ONLY',
       'model':'CHRONOLOGICAL_OLS_HOURLY_LOSS_KW_ON_LOAD_LOAD_SQUARED_TEMPERATURE',
       'input_measurement_boundary_ref':case.measurement_boundary_ref,
       'train_observations':train_n,'holdout_observations':len(b)-train_n,
       'post_observations':len(post),
       'temporal_leakage_guard':'BASELINE_ONLY_PRE_COMMISSIONING',
       'design_rank':rank,'design_condition_number':round(condition,6),
       'coefficients_kw':[round(float(x),9) for x in beta],
       'holdout_mae_kw':round(val_mae,9),'holdout_rmse_kw':round(val_rmse,9),
       'holdout_bias_kw':round(val_bias,9),
       'covered_post_hours':round(float(np.sum(hours)),6),
       'counterfactual_baseline_loss_kwh':round(float(np.sum(counterfactual)),6),
       'observed_synthetic_post_loss_kwh':round(float(np.sum(actual)),6),
       'signed_normalized_difference_kwh':round(float(np.sum(difference)),6),
       'post_windows':[{'started_at_utc':z.started_at.astimezone(timezone.utc).isoformat(),
                        'hours':z.duration_hours,
                        'baseline_counterfactual_kwh':round(float(counterfactual[i]),6),
                        'metered_synthetic_loss_kwh':round(float(actual[i]),6),
                        'signed_difference_kwh':round(float(difference[i]),6)}
                       for i,z in enumerate(post)],
       'confidence_interval':'NOT_CERTIFIED_SERIAL_CORRELATION_AND_METER_ERROR_NOT_MODELED',
       'verified_actual_savings':False,
       'benefit_recognition_eligible':False,
       'industrial_approval_eligible':False,
       'limitations':['Synthetic inputs only', 'No independent meter traceability',
            'OLS baseline does not establish causality or structural stability',
            'Weather/load model cannot be extrapolated to unobserved conditions',
            'No approved M&V method, third party review, tariff or tax valuation']
    }
