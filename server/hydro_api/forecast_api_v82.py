"""Authenticated but STATELESS synthetic HydroForecast V8.2 research API.

No writes to production, no ledger benefit, no trusted data-source publication.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .forecast_v82 import DailyForecastResearchV82, evaluate_daily_forecast, ENGINE_TAG
from .storage import User


def install_forecast_v82_routes(app,get_db,current_user,access,asset,sha,canonical):
    router=APIRouter()

    @router.get('/v82/meta/hydroforecast-readiness')
    def readiness():
        return {'release':'8.2-LAB','engine':ENGINE_TAG,
                'daily_forecast_generation':True,
                'model_selection_precedes_calibration_and_holdout':True,
                'forecast_horizon_days_supported':[1,2,3,4,5,6,7],
                'original_data_origin':'SYNTHETIC_ONLY',
                'statistical_coverage_is_independently_proven':False,
                'real_magadan_series_used':False,
                'field_issued_forecast':False,
                'production_ready':False}

    @router.post('/v82/orgs/{org_id}/hydroforecast/evaluate')
    def evaluate(org_id:str,body:DailyForecastResearchV82,
                 u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','auditor'},u,db)
        a=asset(db,org_id,body.asset_id)
        if a.classification!='LAB_REFERENCE':
            raise HTTPException(409,'REAL_ASSET_NOT_PERMITTED_IN_LAB_FORECAST')
        payload=body.model_dump(mode='json')
        if len(canonical(payload).encode('utf-8'))>190000:
            raise HTTPException(413,'FORECAST_INPUT_EXCEEDS_190KB')
        try:
            report=evaluate_daily_forecast(body)
        except (ValueError,OverflowError,ArithmeticError) as exc:
            raise HTTPException(422,str(exc)[:500]) from None
        engine_sha=hashlib.sha256(Path(__file__).with_name('forecast_v82.py').read_bytes()).hexdigest()
        return {'org_id':org_id,'asset_id':body.asset_id,'report':report,
                'proof':{'input_sha256':sha({'org_id':org_id,'payload':payload}),
                         'report_sha256':sha(report),'engine_sha256':engine_sha,
                         'stateful_record_saved':False,
                         'source_attestation':False,'external_reviewer_signature':False,
                         'independent_causal_qualification':False,
                         'real_world_prediction_interval_validated':False,
                         'industrial_approval_eligible':False}}

    app.include_router(router)
