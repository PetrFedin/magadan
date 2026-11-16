"""API for synthetic cross-module studies; not connected to industrial approvals."""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .storage import StudyRun, User, Asset
from .studies import Strict, MODULES, ENGINE_VERSION, compute_study, SCHEMA

class StudyNew(Strict):
    asset_id: str
    module: Literal['hydroforecast','cascade','turbine','gridloss','heatnet','hydrocapex']
    source_ref: str = Field(min_length=15,max_length=220,pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')
    scenario_group: str = Field(min_length=4,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    case: dict
    scope: Literal['SYNTHETIC_LAB_ONLY']='SYNTHETIC_LAB_ONLY'

class StudyCompare(Strict):
    left_run_id: str
    right_run_id: str

def algorithm_hash():
    digest=hashlib.sha256()
    for name in ('studies.py','engineering.py','radial_grid.py'):
        path=Path(__file__).with_name(name)
        digest.update(name.encode());digest.update(path.read_bytes())
    return digest.hexdigest()

def install_study_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical):
    router=APIRouter()
    def scoped(org_id,db,sid):
        s=db.scalar(select(StudyRun).where(StudyRun.org_id==org_id,StudyRun.id==sid))
        if s is None:raise HTTPException(404,'Study not found')
        return s
    def verify(s):
        ih=sha({'org_id':s.org_id,'asset_id':s.asset_id,'module':s.module,'source_ref':s.source_ref,
                'scenario_group':s.scenario_group,'case':s.case_payload})
        if ih!=s.input_sha256 or sha(s.result)!=s.result_sha256:
            raise HTTPException(409,'STUDY_RECORD_INTEGRITY_FAILURE')
        return ih

    @router.get('/v72/meta/modules')
    def modules():
        return {'version':ENGINE_VERSION,'modules':list(MODULES),
                'data_perimeter':'SYNTHETIC_LAB_ONLY','no_industrial_control':True,
                'all_six_studies_available_as_synthetic_explorations':True,
                'industrial_engineering_verification':False,'approval_pipeline_connected':False,
                'postgresql_native_rls_acceptance':False}

    @router.get('/v72/meta/modules/{module}/schema')
    def module_schema(module:str):
        if module not in SCHEMA:raise HTTPException(404,'Unknown laboratory module')
        return {'module':module,'engine_version':ENGINE_VERSION,
                'request_scope':'SYNTHETIC_LAB_ONLY',
                'json_schema':SCHEMA[module].model_json_schema()}

    @router.post('/v72/orgs/{org_id}/studies',status_code=201)
    def create(org_id:str,body:StudyNew,u:User=Depends(current_user),db:Session=Depends(get_db)):
        role={'economist'} if body.module=='hydrocapex' else {'engineer'}
        access(org_id,role,u,db)
        authorized_asset=asset(db,org_id,body.asset_id)
        if authorized_asset.classification!='LAB_REFERENCE':
            raise HTTPException(409,'NON_SYNTHETIC_ASSET_BLOCKED_FROM_LAB_STUDIES')
        try:
            raw_case=canonical(body.case).encode('utf-8')
        except (TypeError,ValueError):
            raise HTTPException(422,'STUDY_NON_FINITE_OR_INVALID_JSON') from None
        if len(raw_case)>131072:
            raise HTTPException(413,'Synthetic study input exceeds 128 KiB')
        try:result=compute_study(body.module,body.case)
        except (ValueError,TypeError) as ex:
            raise HTTPException(422,{'code':'STUDY_VALIDATION_FAILED','reason':str(ex)[:700]}) from None
        fingerprint=sha({'org_id':org_id,'asset_id':body.asset_id,'module':body.module,
                        'source_ref':body.source_ref,'scenario_group':body.scenario_group,'case':body.case})
        row=StudyRun(org_id=org_id,asset_id=body.asset_id,module=body.module,
                     source_ref=body.source_ref,scenario_group=body.scenario_group,
                     case_payload=body.case,input_sha256=fingerprint,
                     result=result,result_sha256=sha(result),engine_sha256=algorithm_hash(),created_by=u.id)
        db.add(row);db.flush()
        if db.bind.dialect.name!='postgresql':
            record_audit(db,org_id,u.id,'study.synthetic.created','study_run',row.id,
                         {'module':row.module,'input_sha256':fingerprint,'result_sha256':row.result_sha256},audit_secret)
        db.commit()
        return {'id':row.id,'org_id':org_id,'module':row.module,'status':'SYNTHETIC_UNVERIFIED',
                'result':row.result,'hashes':{'input':row.input_sha256,'result':row.result_sha256,
                                            'engine':row.engine_sha256},
                'allowed_as_industrial_decision_evidence':False}

    @router.get('/v72/orgs/{org_id}/studies')
    def listing(org_id:str,asset_id:str|None=None,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        query=select(StudyRun).where(StudyRun.org_id==org_id)
        if asset_id: query=query.where(StudyRun.asset_id==asset_id)
        rows=db.scalars(query.order_by(StudyRun.created_at.desc(),StudyRun.id.desc()).limit(200)).all()
        return [{'id':s.id,'module':s.module,'asset_id':s.asset_id,'source_ref':s.source_ref,
                 'scenario_group':s.scenario_group,'status':'SYNTHETIC_UNVERIFIED'} for s in rows]

    @router.get('/v72/orgs/{org_id}/studies/{study_id}')
    def detail(org_id:str,study_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        s=scoped(org_id,db,study_id);verify(s)
        return {'id':s.id,'asset_id':s.asset_id,'module':s.module,'source_ref':s.source_ref,
                'case':s.case_payload,'result':s.result,'scenario_group':s.scenario_group,
                'assurance':{'synthetic':True,'independent_engineer_signoff':False,
                             'industrial_approval_eligible':False,'data_authorized_for_magadan_assets':False}}

    @router.post('/v72/orgs/{org_id}/studies/{study_id}/reproduce')
    def reproduce(org_id:str,study_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','auditor'},u,db)
        s=scoped(org_id,db,study_id);verify(s)
        if s.engine_sha256!=algorithm_hash():
            raise HTTPException(409,'PINNED_STUDY_ENGINE_NOT_AVAILABLE')
        recomputed=compute_study(s.module,s.case_payload)
        if sha(recomputed)!=s.result_sha256:
            raise HTTPException(409,'REPRODUCTION_RESULT_CHANGED')
        return {'study_id':s.id,'reproduced':True,'input_sha256':s.input_sha256,
                'result_sha256':s.result_sha256,'engine_sha256':s.engine_sha256,
                'industrial_validation':False}

    @router.post('/v72/orgs/{org_id}/studies/compare-pair')
    def compare(org_id:str,body:StudyCompare,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor'},u,db)
        if body.left_run_id==body.right_run_id:
            raise HTTPException(422,'Choose two distinct study IDs')
        l=scoped(org_id,db,body.left_run_id);r=scoped(org_id,db,body.right_run_id)
        verify(l);verify(r)
        if (l.asset_id,l.module,l.scenario_group)!=(r.asset_id,r.module,r.scenario_group):
            raise HTTPException(409,'DIFFERENT_ASSET_MODULE_OR_SCENARIO_GROUP')
        metric={'hydroforecast':'mae_cms','cascade':'total_energy_mwh',
                'turbine':'robust_z','gridloss':'line_loss_p_mw','heatnet':'estimated_pipe_loss_mw',
                'hydrocapex':'selected_npv_rub'}[l.module]
        first=l.result['result'].get(metric)
        second=r.result['result'].get(metric)
        delta=None
        try:
            from decimal import Decimal
            if first is not None and second is not None:
                delta=str(Decimal(str(second))-Decimal(str(first)))
        except (ValueError,TypeError):pass
        return {'left':l.id,'right':r.id,'module':l.module,'metric':metric,
                'left_value':first,'right_value':second,'delta_right_minus_left':delta,
                'comparability_status':'UNVERIFIED_TAG_ONLY',
                'industrial_decision_eligible':False,
                'warning':'Matching scenario_group is a label, not physical or statistical proof of equivalent baseline conditions'}
    app.include_router(router)
