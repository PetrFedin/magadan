"""Lab-only reference comparison API. Importing results never grants field acceptance."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .storage import StudyRun,GridReferenceComparisonV77,User
from .radial_grid import RadialCase
from .reference_v77 import ReferenceSubmission,compare_reference
from .studies_api import algorithm_hash
from .studies import compute_study

class ImportBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    study_id:str=Field(min_length=1,max_length=120)
    submission:ReferenceSubmission


def reference_engine_sha():
    s=sha256()
    for filename in ('reference_v77.py','reference_api_v77.py'):
        fp=Path(__file__).with_name(filename)
        s.update(filename.encode());s.update(fp.read_bytes())
    return s.hexdigest()


def install_reference_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical):
    router=APIRouter()
    def source(db,org_id,study_id):
        row=db.scalar(select(StudyRun).where(StudyRun.org_id==org_id,StudyRun.id==study_id))
        if not row:raise HTTPException(404,'Study unavailable')
        if row.module!='gridloss' or row.case_payload.get('model_kind')!='radial_ac_v73':
            raise HTTPException(409,'REFERENCE_REQUIRES_RADIAL_LAB_STUDY')
        if asset(db,org_id,row.asset_id).classification!='LAB_REFERENCE':
            raise HTTPException(409,'REFERENCE_LAB_ASSET_REQUIRED')
        if row.engine_sha256!=algorithm_hash():
            raise HTTPException(409,'ENGINE_VERSION_CHANGED_RECALCULATE_STUDY')
        expected=sha({'org_id':row.org_id,'asset_id':row.asset_id,'module':row.module,
            'source_ref':row.source_ref,'scenario_group':row.scenario_group,'case':row.case_payload})
        if expected!=row.input_sha256 or sha(row.result)!=row.result_sha256:
            raise HTTPException(409,'SOURCE_STUDY_INTEGRITY_MISMATCH')
        try:
            repeated=compute_study('gridloss',row.case_payload)
        except (ValueError,TypeError) as exc:
            raise HTTPException(409,'SOURCE_STUDY_REPLAY_FAILED') from exc
        if sha(repeated)!=row.result_sha256:
            raise HTTPException(409,'SOURCE_STUDY_COMPUTATION_DIVERGED')
        return row

    @router.get('/v77/meta/readiness')
    def readiness():
        return {'version':'0.7.7','scope':'SYNTHETIC_LAB_ONLY','production_ready':False,
             'external_reference_adapter':'DATA_EXCHANGE_ONLY','solver_execution_attested':False,
             'independent_engineer_signoff':False,'magadan_field_approval':False,
             'postgres_rls_native_accepted':False,'industrial_approval_eligible':False}

    @router.get('/v77/orgs/{org_id}/grid-reference/request/{study_id}')
    def export_reference_request(org_id:str,study_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','viewer'},u,db)
        r=source(db,org_id,study_id)
        return {'format':'hydrokontur-reference-request-v77','scope':'SYNTHETIC_UNATTESTED_REFERENCE_ONLY',
            'study_id':r.id,'org_id':r.org_id,'asset_id':r.asset_id,
            'case_sha256':sha(r.case_payload),'source_input_sha256':r.input_sha256,
            'reference_case':r.case_payload,'expected_windows':[w['name'] for w in r.case_payload['windows']],
            'independent_reference_must_be_executed_outside_this_service':True,
            'not_field_approved':True}

    @router.post('/v77/orgs/{org_id}/grid-reference/comparisons',status_code=201)
    def import_reference(org_id:str,body:ImportBody,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer'},u,db)
        r=source(db,org_id,body.study_id)
        sub=body.submission.model_dump(mode='json')
        if len(canonical(sub).encode())>128000:
            raise HTTPException(413,'REFERENCE_PAYLOAD_TOO_LARGE')
        try:
            RadialCase.model_validate(r.case_payload)
            result=compare_reference(r.result['result'],body.submission,sha(r.case_payload))
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from None
        entry=GridReferenceComparisonV77(org_id=org_id,asset_id=r.asset_id,study_id=r.id,
            source_input_sha256=r.input_sha256,submission=sub,submission_sha256=sha(sub),
            report=result,report_sha256=sha(result),engine_sha256=reference_engine_sha(),created_by=u.id)
        try:
            db.add(entry);db.flush()
            if db.bind.dialect.name!='postgresql':
                record_audit(db,org_id,u.id,'grid.reference.lab.imported',
                    'grid_reference_comparison_v77',entry.id,
                    {'study_id':r.id,'report_sha256':entry.report_sha256,'status':result['status'],
                     'not_independent_attestation':True},audit_secret)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409,'IDENTICAL_REFERENCE_ALREADY_REGISTERED') from None
        return {'comparison_id':entry.id,'status':result['status'],'report':result,
            'independent_engineering_accepted':False,'industrial_approval_eligible':False}

    @router.get('/v77/orgs/{org_id}/grid-reference/comparisons/{comparison_id}')
    def show(org_id:str,comparison_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','viewer'},u,db)
        row=db.scalar(select(GridReferenceComparisonV77).where(
          GridReferenceComparisonV77.org_id==org_id,GridReferenceComparisonV77.id==comparison_id))
        if not row:raise HTTPException(404,'Comparison unavailable')
        return {'comparison_id':row.id,'study_id':row.study_id,'status':row.report['status'],
            'report':row.report,'submitted_reference_unattested':True,'industrial_approval_eligible':False}

    @router.post('/v77/orgs/{org_id}/grid-reference/comparisons/{comparison_id}/reproduce')
    def reproduce(org_id:str,comparison_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'auditor'},u,db)
        row=db.scalar(select(GridReferenceComparisonV77).where(
          GridReferenceComparisonV77.org_id==org_id,GridReferenceComparisonV77.id==comparison_id))
        if not row:raise HTTPException(404,'Comparison unavailable')
        r=source(db,org_id,row.study_id)
        if r.input_sha256!=row.source_input_sha256 or reference_engine_sha()!=row.engine_sha256:
            raise HTTPException(409,'PINNED_SOURCE_OR_REFERENCE_CODE_CHANGED')
        if sha(row.submission)!=row.submission_sha256 or sha(row.report)!=row.report_sha256:
            raise HTTPException(409,'REFERENCE_RECORD_TAMPERED')
        submission=ReferenceSubmission.model_validate(row.submission)
        fresh=compare_reference(r.result['result'],submission,sha(r.case_payload))
        if sha(fresh)!=row.report_sha256:
            raise HTTPException(409,'REFERENCE_COMPARISON_REPLAY_DIVERGED')
        return {'comparison_id':row.id,'reproduced':True,'status':fresh['status'],
            'reference_origin_verified':False,'independent_engineer_signoff':False,
            'industrial_approval_eligible':False}
    app.include_router(router)
