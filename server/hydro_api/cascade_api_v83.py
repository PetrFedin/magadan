"""V8.3 authenticated stateless two-reservoir feasibility screen.

No database mutation, no dispatch, no generation/benefit/financial accounting.
Authorization is checked server-side for BOTH assets under the same org.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .cascade_v83 import CoupledCascadeV83, evaluate_coupled_cascade_v83, ENGINE_TAG
from .forecast_v82 import ENGINE_TAG as FORECAST_ENGINE_V82
from .storage import User


def install_cascade_v83_routes(app,get_db,current_user,access,asset,sha,canonical):
    router=APIRouter()

    @router.get('/v83/meta/cascade-readiness')
    def readiness():
        return {'release':'8.3.2-LAB','engine':ENGINE_TAG,
           'forecast_engine':FORECAST_ENGINE_V82,
           'forecast_horizon_eligible_days':[2],
           'two_reservoir_mass_balance_with_in_transit_storage':True,
           'real_hydrological_reservoir_curves_verified':False,
           'independent_hydraulics_validated':False,
           'financial_benefit_certified':False,'production_ready':False}

    @router.post('/v83/orgs/{org_id}/cascade/forecast-screen')
    def research_cascade(org_id:str,body:CoupledCascadeV83,
                 u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','auditor'},u,db)
        for identifier in (body.upper.asset_id,body.lower.asset_id):
            a=asset(db,org_id,identifier)
            if a.classification!='LAB_REFERENCE':
                raise HTTPException(409,'REAL_ASSET_NOT_PERMITTED_IN_LAB_CASCADE')
        payload=body.model_dump(mode='json')
        if len(canonical(payload).encode('utf-8'))>240000:
            raise HTTPException(413,'CASCADE_SYNTHETIC_INPUT_EXCEEDS_240KB')
        try:
            result=evaluate_coupled_cascade_v83(body)
        except (ValueError, ArithmeticError, OverflowError) as exc:
            raise HTTPException(422,str(exc)[:500]) from None
        engine_sha=hashlib.sha256(Path(__file__).with_name('cascade_v83.py').read_bytes()).hexdigest()
        forecast_sha=hashlib.sha256(Path(__file__).with_name('forecast_v82.py').read_bytes()).hexdigest()
        return {'org_id':org_id,'upper_asset_id':body.upper.asset_id,
           'lower_asset_id':body.lower.asset_id,'report':result,
           'proof':{'input_sha256':sha({'org_id':org_id,'payload':payload}),
                    'report_sha256':sha(result),'engine_sha256':engine_sha,
                    'forecast_engine_sha256':forecast_sha,
                    'trusted_source_data':False,'real_assets_tested':False,
                    'stateful_record_saved':False,'benefit_registry_updated':False,
                    'independent_engineer_signature':False,
                    'native_postgresql17_rls_verified':False,
                    'production_approved':False}}

    app.include_router(router)
