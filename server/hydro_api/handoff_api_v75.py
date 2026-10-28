"""V7.5: tenant-authorized append-only synthetic engineering handoffs."""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .storage import (Asset, User, StudyRun, ResearchProgramme, ResearchProgrammeStudy, ResearchHandoff)
from .studies_api import algorithm_hash
from .studies import ForecastCase,CascadeCase
from .coupling_v75 import (Strict,ForecastCascadeBridge,MaintenanceBridge,
                          couple_forecast_to_cascade,build_maintenance_decision)


class HandoffNew(Strict):
    kind:Literal['forecast_to_cascade','turbine_to_maintenance']
    left_study_id:str=Field(min_length=1,max_length=100)
    right_study_id:str|None=Field(default=None,max_length=100)
    programme_id:str|None=Field(default=None,max_length=100)
    forecast_bridge:ForecastCascadeBridge|None=None
    maintenance_bridge:MaintenanceBridge|None=None
    scope:Literal['SYNTHETIC_LAB_ONLY']='SYNTHETIC_LAB_ONLY'

    @model_validator(mode='after')
    def matched_contract(self):
        if self.kind=='forecast_to_cascade' and (not self.right_study_id or not self.forecast_bridge or self.maintenance_bridge):
            raise ValueError('FORECAST_COUPLING_REQUIRES_TWO_STUDIES_AND_SETTINGS')
        if self.kind=='turbine_to_maintenance' and (self.right_study_id or not self.maintenance_bridge or self.forecast_bridge):
            raise ValueError('MAINTENANCE_REQUIRES_ONE_STUDY_AND_SETTINGS')
        if self.right_study_id==self.left_study_id:raise ValueError('HANDOFF_SAME_STUDY')
        return self


def handoff_engine_hash():
    h=hashlib.sha256()
    for f in ('coupling_v75.py','handoff_api_v75.py'):
        p=Path(__file__).with_name(f)
        h.update(f.encode());h.update(p.read_bytes())
    return h.hexdigest()


def install_handoff_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical):
    router=APIRouter()

    def study(db,org_id,id):
        s=db.scalar(select(StudyRun).where(StudyRun.id==id,StudyRun.org_id==org_id))
        if s is None:raise HTTPException(404,'Study not found in organization')
        if asset(db,org_id,s.asset_id).classification!='LAB_REFERENCE':
            raise HTTPException(409,'ONLY_SYNTHETIC_LAB_ASSET_IS_ELIGIBLE')
        if not s.source_ref.startswith('SYNTHETIC-'):
            raise HTTPException(409,'REAL_SOURCE_NOT_ALLOWED_IN_LAB_HANDOFF')
        input_source={'org_id':s.org_id,'asset_id':s.asset_id,'module':s.module,'source_ref':s.source_ref,
                      'scenario_group':s.scenario_group,'case':s.case_payload}
        if sha(input_source)!=s.input_sha256 or sha(s.result)!=s.result_sha256:
            raise HTTPException(409,'HANDOFF_SOURCE_INTEGRITY_FAILED')
        if s.engine_sha256!=algorithm_hash():
            raise HTTPException(409,'HANDOFF_SOURCE_ENGINE_NOT_PINNED')
        return s

    def source_pins(studies):
        return [{'id':s.id,'org_id':s.org_id,'asset_id':s.asset_id,'module':s.module,
                 'input_sha256':s.input_sha256,'result_sha256':s.result_sha256,
                 'engine_sha256':s.engine_sha256} for s in studies]

    def compute(body,left,right):
        try:
            if body.kind=='forecast_to_cascade':
                if left.module!='hydroforecast' or right is None or right.module!='cascade':
                    raise ValueError('WRONG_SOURCE_MODULES_FOR_HYDROLOGY_BRIDGE')
                if left.scenario_group!=right.scenario_group or left.asset_id!=right.asset_id:
                    raise ValueError('FORECAST_AND_CASCADE_CONTEXT_MISMATCH')
                result=couple_forecast_to_cascade(ForecastCase.model_validate(left.case_payload),
                     CascadeCase.model_validate(right.case_payload),body.forecast_bridge)
            else:
                if left.module!='turbine' or right is not None:
                    raise ValueError('WRONG_SOURCE_MODULE_FOR_MAINTENANCE')
                result=build_maintenance_decision(left.result['result'],body.maintenance_bridge)
        except (ValueError, TypeError) as e:
            raise HTTPException(422,{'code':'INVALID_SYNTHETIC_HANDOFF','reason':str(e)[:600]}) from None
        return result

    def normalize(body,left,right,programme_sha256=None):
        sids=[left]+([right] if right is not None else [])
        params=body.model_dump(mode='json')
        return {'version':'7.5-LAB', 'kind':body.kind,'inputs':params,
                'source_pins':source_pins(sids),'programme_sha256':programme_sha256,'research_only':True}

    def programme_gate(db,org_id,pid,ids):
        if not pid:return None
        found=db.scalar(select(ResearchProgramme).where(ResearchProgramme.org_id==org_id,
                         ResearchProgramme.id==pid))
        if found is None:raise HTTPException(404,'Research programme not found')
        if sha(found.snapshot)!=found.snapshot_sha256:
            raise HTTPException(409,'PARENT_PROGRAMME_SNAPSHOT_TAMPERED')
        attached=set(db.scalars(select(ResearchProgrammeStudy.study_id).where(
            ResearchProgrammeStudy.org_id==org_id,ResearchProgrammeStudy.programme_id==pid)).all())
        if any(sid not in attached for sid in ids):
            raise HTTPException(409,'HANDOFF_REQUIRES_SOURCE_STUDIES_IN_PROGRAMME')
        return found.snapshot_sha256

    def reconstruct(db,org_id,r,deep=False):
        if sha(r.snapshot)!=r.snapshot_sha256 or sha(r.input_payload)!=r.input_sha256:
            raise HTTPException(409,'HANDOFF_SNAPSHOT_INTEGRITY_FAILURE')
        if r.engine_sha256!=handoff_engine_hash() or r.snapshot.get('pinned_engine_sha256')!=r.engine_sha256:
            raise HTTPException(409,'HANDOFF_IMPLEMENTATION_CHANGED')
        body=HandoffNew.model_validate(r.input_payload['inputs'])
        if body.kind!=r.kind or body.programme_id!=r.programme_id:
            raise HTTPException(409,'HANDOFF_INPUT_RELATIONAL_MISMATCH')
        if body.left_study_id!=r.left_study_id or body.right_study_id!=r.right_study_id:
            raise HTTPException(409,'HANDOFF_STUDY_RELATIONAL_MISMATCH')
        left=study(db,org_id,r.left_study_id)
        right=study(db,org_id,r.right_study_id) if r.right_study_id else None
        if left.asset_id!=r.asset_id or (right and right.asset_id!=r.asset_id):
            raise HTTPException(409,'HANDOFF_ASSET_RELATIONAL_MISMATCH')
        pinned_programme=programme_gate(db,org_id,body.programme_id,[left.id]+([right.id] if right else []))
        if normalize(body,left,right,pinned_programme)!=r.input_payload or r.snapshot['source_pins']!=source_pins([left]+([right] if right else [])):
            raise HTTPException(409,'HANDOFF_PARENT_PROVENANCE_CHANGED')
        if deep:
            result=compute(body,left,right)
            if sha(result)!=r.snapshot.get('result_sha256') or result!=r.snapshot['result']:
                raise HTTPException(409,'HANDOFF_RECOMPUTATION_DIVERGED')
        return r.snapshot

    @router.get('/v75/meta/readiness')
    def meta():
        return {'version':'7.5','kind':'LAB_SYNTHETIC_ONLY','hydrology_bridge':'TIME_INDEXED_HINDCAST_TO_FIXED_RELEASE_CASCADE',
                'turbine_maintenance_bridge':'NON_PROBABILISTIC_COST_OPTIONS','postgresql_rls_native':'NOT_ACCEPTED',
                'field_data':'NO_MAGADAN_DATA','independent_engineering':'NOT_COMPLETED',
                'production_ready':False,'investment_authorization':False}

    @router.post('/v75/orgs/{org_id}/handoffs',status_code=201)
    def create(org_id:str,body:HandoffNew,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer'},u,db)
        left=study(db,org_id,body.left_study_id)
        right=study(db,org_id,body.right_study_id) if body.right_study_id else None
        if right and right.asset_id!=left.asset_id:
            raise HTTPException(409,'HANDOFF_CROSS_ASSET_SOURCE_REFUSED')
        pinned_programme=programme_gate(db,org_id,body.programme_id,[left.id]+([right.id] if right else []))
        package=normalize(body,left,right,pinned_programme)
        canonical_bytes=canonical(package).encode('utf-8')
        if len(canonical_bytes)>130000:raise HTTPException(413,'HANDOFF_INPUT_TOO_LARGE')
        result=compute(body,left,right)
        snapshot={'version':'7.5-LAB','kind':body.kind,'org_id':org_id,'asset_id':left.asset_id,
                  'source_pins':package['source_pins'],'result':result,'result_sha256':sha(result),
                  'pinned_engine_sha256':handoff_engine_hash(),
                  'status':'RESEARCH_ONLY_NO_INDUSTRIAL_APPROVAL','industrial_approval_eligible':False}
        row=ResearchHandoff(org_id=org_id,asset_id=left.asset_id,kind=body.kind,
              left_study_id=left.id,right_study_id=right.id if right else None,programme_id=body.programme_id,
              input_payload=package,input_sha256=sha(package),snapshot=snapshot,
              snapshot_sha256=sha(snapshot),engine_sha256=handoff_engine_hash(),created_by=u.id)
        try:
            db.add(row);db.flush()
            if db.bind.dialect.name!='postgresql':
                record_audit(db,org_id,u.id,'research.handoff.synthetic.created','research_handoff',row.id,
                             {'kind':body.kind,'snapshot_sha256':row.snapshot_sha256},audit_secret)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409,'DUPLICATE_OR_INVALID_SYNTHETIC_HANDOFF') from None
        return {'id':row.id,'kind':body.kind,'snapshot_sha256':row.snapshot_sha256,
                'result':result,'industrial_approval_eligible':False}

    @router.get('/v75/orgs/{org_id}/handoffs')
    def listing(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        rows=db.scalars(select(ResearchHandoff).where(ResearchHandoff.org_id==org_id)
                   .order_by(ResearchHandoff.created_at.desc()).limit(100)).all()
        return [{'id':r.id,'kind':r.kind,'asset_id':r.asset_id,
                 'programme_id':r.programme_id,'status':'RESEARCH_ONLY'} for r in rows]

    @router.get('/v75/orgs/{org_id}/handoffs/{handoff_id}')
    def detail(org_id:str,handoff_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        r=db.scalar(select(ResearchHandoff).where(ResearchHandoff.id==handoff_id,
                        ResearchHandoff.org_id==org_id))
        if not r:raise HTTPException(404,'Research handoff not found')
        return {'id':r.id,'snapshot':reconstruct(db,org_id,r),
                'status':'RESEARCH_ONLY','industrial_approval_eligible':False}

    @router.post('/v75/orgs/{org_id}/handoffs/{handoff_id}/reproduce')
    def reproduce(org_id:str,handoff_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','auditor'},u,db)
        r=db.scalar(select(ResearchHandoff).where(ResearchHandoff.id==handoff_id,
                       ResearchHandoff.org_id==org_id))
        if not r:raise HTTPException(404,'Research handoff not found')
        snapshot=reconstruct(db,org_id,r,deep=True)
        return {'id':r.id,'reproduced':True,'source_count':len(snapshot['source_pins']),
                'snapshot_sha256':r.snapshot_sha256,'independent_validation':False,
                'industrial_approval_eligible':False}

    @router.get('/v75/orgs/{org_id}/programmes/{programme_id}/handoffs')
    def programme_handoffs(org_id:str,programme_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        parent_sha=programme_gate(db,org_id,programme_id,[])
        rows=db.scalars(select(ResearchHandoff).where(ResearchHandoff.org_id==org_id,
             ResearchHandoff.programme_id==programme_id).order_by(ResearchHandoff.created_at)).all()
        for r in rows:reconstruct(db,org_id,r)
        return {'programme_id':programme_id,'programme_snapshot_sha256':parent_sha,
                'handoff_ids':[r.id for r in rows],
                'handoff_kinds':[r.kind for r in rows],
                'all_handoffs_lab_only':True,'industrial_approval_eligible':False,
                'unclosed_gates':['NATIVE_POSTGRESQL_RLS_NOT_ACCEPTED','INDEPENDENT_ENGINEERING_NOT_ACCEPTED',
                                  'REAL_MAGADAN_ASSET_DATA_NOT_AUTHORIZED','EXTERNAL_ARCHIVE_NOT_ACCEPTED']}

    @router.post('/v75/orgs/{org_id}/programmes/{programme_id}/reproduce-handoffs')
    def reproduce_programme_handoffs(org_id:str,programme_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','auditor'},u,db)
        parent_sha=programme_gate(db,org_id,programme_id,[])
        rows=db.scalars(select(ResearchHandoff).where(ResearchHandoff.org_id==org_id,
             ResearchHandoff.programme_id==programme_id).order_by(ResearchHandoff.created_at)).all()
        checks=[]
        for r in rows:
            snapshot=reconstruct(db,org_id,r,deep=True)
            checks.append({'id':r.id,'kind':r.kind,'snapshot_sha256':sha(snapshot),'reproduced':True})
        return {'programme_id':programme_id,'programme_snapshot_sha256':parent_sha,
                'attached_handoffs_recomputed':len(checks),'checks':checks,
                'parent_programme_models_reproduced_here':False,
                'parent_programme_reproduce_endpoint':f'/v74/orgs/{org_id}/programmes/{programme_id}/reproduce',
                'industrial_approval_eligible':False}

    app.include_router(router)
