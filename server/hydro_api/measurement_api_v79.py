"""V7.9 synthetic counterfactual M&V API, tenant isolated and append only."""
from __future__ import annotations
import hashlib
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .measurement_v79 import MVScreenV79, evaluate_mv_screen
from .storage import MeasurementScreenV79, User


def implementation_sha256():
    p=Path(__file__).with_name('measurement_v79.py')
    return hashlib.sha256(p.read_bytes()).hexdigest()


def install_mv_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical):
    router=APIRouter()
    def view(db,org_id,row):
        if row.org_id != org_id:
            raise HTTPException(404,'Measurement screen not found')
        if (sha(row.input_payload)!=row.input_sha256 or
            sha(row.report)!=row.report_sha256 or
            row.engine_sha256!=implementation_sha256()):
            raise HTTPException(409,'MEASUREMENT_SOURCE_INTEGRITY_FAILURE')
        case=MVScreenV79.model_validate(row.input_payload)
        if case.asset_id!=row.asset_id:
            raise HTTPException(409,'MV_RELATIONAL_BINDING_DRIFT')
        recomputed=evaluate_mv_screen(case)
        if sha(recomputed)!=row.report_sha256:
            raise HTTPException(409,'COUNTERFACTUAL_REPLAY_DIVERGED')
        return {'id':row.id,'report':recomputed,'input_sha256':row.input_sha256,
                'report_sha256':row.report_sha256,'reproduced_from_sources':True,
                'measured_savings_certified':False,'industrial_approval_eligible':False}

    @router.get('/v79/meta/measurement-readiness')
    def meta():
        return {'release':'7.9-LAB','actual_savings_recognised':False,
                'synthetic_normalization':True,'baseline_temporal_holdout':True,
                'normalization_extrapolation_blocked':True,'real_meter_attestation':False,
                'post_investment_verified':False,'industrial_approval_eligible':False}

    @router.post('/v79/orgs/{org_id}/measurement-screens',status_code=201)
    def create(org_id:str,body:MVScreenV79,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist'},u,db)
        if asset(db,org_id,body.asset_id).classification!='LAB_REFERENCE':
            raise HTTPException(409,'REAL_ASSET_NOT_ALLOWED_IN_SYNTHETIC_MV')
        payload=body.model_dump(mode='json')
        if len(canonical(payload).encode())>180000:
            raise HTTPException(413,'MV_INPUT_TOO_LARGE')
        try:
            result=evaluate_mv_screen(body)
        except (ValueError,ArithmeticError) as exc:
            raise HTTPException(422,str(exc)[:500]) from None
        row=MeasurementScreenV79(org_id=org_id,asset_id=body.asset_id,
            input_payload=payload,input_sha256=sha(payload),report=result,
            report_sha256=sha(result),engine_sha256=implementation_sha256(),created_by=u.id)
        try:
            db.add(row);db.flush()
            if db.bind.dialect.name!='postgresql':
                record_audit(db,org_id,u.id,'measurement.synthetic.created',
                    'measurement_screens_v79',row.id,
                    {'result_sha256':row.report_sha256,'actual_savings_certified':False},audit_secret)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409,'DUPLICATE_MEASUREMENT_SCREEN') from None
        return view(db,org_id,row)

    @router.get('/v79/orgs/{org_id}/measurement-screens')
    def listing(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        rows=db.scalars(select(MeasurementScreenV79).where(
            MeasurementScreenV79.org_id==org_id).order_by(
            MeasurementScreenV79.created_at.desc()).limit(100)).all()
        return [{'id':row.id,'asset_id':row.asset_id,
                 'report_sha256':row.report_sha256,
                 'status':'SYNTHETIC_COUNTERFACTUAL_ONLY'} for row in rows]

    @router.get('/v79/orgs/{org_id}/measurement-screens/{item_id}')
    def get(org_id:str,item_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        row=db.scalar(select(MeasurementScreenV79).where(
            MeasurementScreenV79.org_id==org_id,MeasurementScreenV79.id==item_id))
        if row is None:raise HTTPException(404,'Measurement screen unavailable')
        return view(db,org_id,row)

    @router.post('/v79/orgs/{org_id}/measurement-screens/{item_id}/reproduce')
    def reproduce(org_id:str,item_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'auditor'},u,db)
        row=db.scalar(select(MeasurementScreenV79).where(
            MeasurementScreenV79.org_id==org_id,MeasurementScreenV79.id==item_id))
        if row is None:raise HTTPException(404,'Measurement screen unavailable')
        result=view(db,org_id,row)
        return {**result,'audit_reproduced':True,'independent_expert_validation':False}

    @router.get('/v8/orgs/{org_id}/measurement-screens/{item_id}/quality')
    def quality(org_id:str,item_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        row=db.scalar(select(MeasurementScreenV79).where(
            MeasurementScreenV79.org_id==org_id,MeasurementScreenV79.id==item_id))
        if row is None:raise HTTPException(404,'Measurement screen unavailable')
        # Run existing full original-code replay before producing a quality diagnostic.
        baseline=view(db,org_id,row)
        from .measurement_quality_v8 import evaluate_quality
        case=MVScreenV79.model_validate(row.input_payload)
        return {'measurement_id':row.id,'measurement_report_sha256':baseline['report_sha256'],
                'quality':evaluate_quality(case),'actual_savings_certified':False}

    app.include_router(router)
