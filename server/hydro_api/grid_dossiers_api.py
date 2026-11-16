"""V7.3 synthetic radial-grid run -> physically comparable -> financial dossier.

No production approvals, real assets, tariff assertions or customer networks.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .storage import StudyRun, GridEconomicDossier, GridAnnualDossierV78, User
from .studies import Strict,compute_study
from .studies_api import algorithm_hash
from .radial_grid import RadialCase,physical_comparability
from .finance_evidence import LabFinance,evaluate_feeder_alternative

class RadialStudyNew(Strict):
    asset_id: str = Field(min_length=1,max_length=100)
    scenario_group: str = Field(min_length=4,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    source_ref: str = Field(min_length=15,max_length=220,pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')
    scope: Literal['SYNTHETIC_LAB_ONLY']='SYNTHETIC_LAB_ONLY'
    case: RadialCase

class ComparisonInput(Strict):
    baseline_run_id: str
    proposed_run_id: str

class FinanceInput(ComparisonInput):
    asset_id: str
    benefit_key: str=Field(min_length=5,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    finance: LabFinance


def source_hash():
    digest=hashlib.sha256()
    for name in ('finance_evidence.py','grid_dossiers_api.py'):
        path=Path(__file__).with_name(name)
        digest.update(name.encode());digest.update(path.read_bytes())
    return digest.hexdigest()


def install_radial_economics_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical):
    r=APIRouter()

    def run_for_org(db,org_id,sid):
        x=db.scalar(select(StudyRun).where(StudyRun.org_id==org_id,StudyRun.id==sid))
        if x is None:raise HTTPException(404,'Study unavailable')
        if x.module!='gridloss' or x.case_payload.get('model_kind')!='radial_ac_v73':
            raise HTTPException(409,'REQUIRES_V73_RADIAL_SYNTHETIC_RUN')
        fingerprint=sha({'org_id':x.org_id,'asset_id':x.asset_id,'module':x.module,
            'source_ref':x.source_ref,'scenario_group':x.scenario_group,'case':x.case_payload})
        if x.input_sha256!=fingerprint or x.result_sha256!=sha(x.result):
            raise HTTPException(409,'STORED_STUDY_INTEGRITY_FAILURE')
        if x.engine_sha256!=algorithm_hash():
            raise HTTPException(409,'STUDY_CODE_VERSION_NO_LONGER_PINNED')
        return x

    def prepare_pair(db,org_id,body):
        if body.baseline_run_id==body.proposed_run_id:
            raise HTTPException(422,'BASELINE_AND_PROPOSED_MUST_DIFFER')
        baseline=run_for_org(db,org_id,body.baseline_run_id)
        proposed=run_for_org(db,org_id,body.proposed_run_id)
        if (baseline.org_id,baseline.asset_id,baseline.scenario_group)!=(proposed.org_id,proposed.asset_id,proposed.scenario_group):
            raise HTTPException(409,'CROSS_ASSET_OR_SCENARIO_GROUP_MISMATCH')
        b=RadialCase.model_validate(baseline.case_payload)
        p=RadialCase.model_validate(proposed.case_payload)
        comparable,reasons=physical_comparability(b,p)
        return baseline,proposed,b,p,comparable,reasons

    @r.get('/v73/meta/readiness')
    def v73_readiness():
        return {'version':'0.7.3-synthetic-lab','production_ready':False,
            'radial_grid_synthetic_solver':True,
            'independent_nodal_kcl_numerical_crosscheck':True,
            'physical_comparability_policy':'EXPLICIT_INVARIANTS_ONLY',
            'economic_dossier':'SYNTHETIC_NON_AUTHORITATIVE',
            'postgreSQL_native_rls':'NOT_ACCEPTED',
            'magadan_field_validation':False,
            'industrial_decision_approval_for_radial_dossiers':False}

    @r.post('/v73/orgs/{org_id}/radial-runs',status_code=201)
    def create_run(org_id:str,body:RadialStudyNew,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer'},u,db)
        if asset(db,org_id,body.asset_id).classification!='LAB_REFERENCE':
            raise HTTPException(409,'NON_LAB_ASSET_CANNOT_RUN_SYNTHETIC_ENGINE')
        payload=body.case.model_dump(mode='json')
        if len(canonical(payload).encode('utf-8'))>131072:
            raise HTTPException(413,'SYNTHETIC_INPUT_TOO_LARGE')
        try: result=compute_study('gridloss',payload)
        except (ValueError,TypeError) as ex:
            raise HTTPException(422,str(ex)[:500]) from None
        fingerprint=sha({'org_id':org_id,'asset_id':body.asset_id,'module':'gridloss',
            'source_ref':body.source_ref,'scenario_group':body.scenario_group,'case':payload})
        x=StudyRun(org_id=org_id,asset_id=body.asset_id,module='gridloss',source_ref=body.source_ref,
            scenario_group=body.scenario_group,case_payload=payload,input_sha256=fingerprint,
            result=result,result_sha256=sha(result),engine_sha256=algorithm_hash(),created_by=u.id)
        db.add(x);db.flush()
        if db.bind.dialect.name!='postgresql':
            record_audit(db,org_id,u.id,'grid.radial.synthetic.created','study_run',x.id,
                {'input_sha256':x.input_sha256,'result_sha256':x.result_sha256,'scope':'LAB_ONLY'},audit_secret)
        db.commit()
        return {'run_id':x.id,'status':'SYNTHETIC_UNVERIFIED',
                'result':x.result,'input_sha256':x.input_sha256,'result_sha256':x.result_sha256,
                'industrial_approval_eligible':False}

    @r.get('/v73/orgs/{org_id}/radial-runs')
    def list_radial_runs(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','viewer'},u,db)
        rows=db.scalars(select(StudyRun).where(StudyRun.org_id==org_id,StudyRun.module=='gridloss')
            .order_by(StudyRun.created_at.desc()).limit(200)).all()
        return [{'id':x.id,'asset_id':x.asset_id,'scenario_group':x.scenario_group,
                 'loss_mwh':x.result['result']['total_line_energy_loss_mwh'],
                 'status':'SYNTHETIC_UNVERIFIED'} for x in rows if x.case_payload.get('model_kind')=='radial_ac_v73']

    @r.post('/v73/orgs/{org_id}/radial-runs/compare')
    def compare(org_id:str,body:ComparisonInput,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','auditor','manager'},u,db)
        b,p,bc,pc,ok,reasons=prepare_pair(db,org_id,body)
        return {'baseline_run_id':b.id,'proposed_run_id':p.id,
            'comparability':'MATCHED_SYNTHETIC_INVARIANTS' if ok else 'NOT_COMPARABLE',
            'mismatch_reasons':reasons,'baseline_loss_mwh':b.result['result']['total_line_energy_loss_mwh'],
            'proposed_loss_mwh':p.result['result']['total_line_energy_loss_mwh'],
            'investment_evidence_status':'NOT_AUTHORIZED'}

    @r.post('/v73/orgs/{org_id}/economic-dossiers',status_code=201)
    def create_dossier(org_id:str,body:FinanceInput,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'economist'},u,db)
        a=asset(db,org_id,body.asset_id)
        if a.classification!='LAB_REFERENCE':
            raise HTTPException(409,'NON_LAB_ASSET_CANNOT_GENERATE_SYNTHETIC_ECONOMICS')
        if db.scalar(select(GridEconomicDossier).where(GridEconomicDossier.org_id==org_id,GridEconomicDossier.benefit_key==body.benefit_key)):
            raise HTTPException(409,'BENEFIT_KEY_ALREADY_REGISTERED')
        if db.scalar(select(GridAnnualDossierV78.id).where(GridAnnualDossierV78.org_id==org_id,
            (GridAnnualDossierV78.benefit_key==body.benefit_key) |
            ((GridAnnualDossierV78.baseline_run_id==body.baseline_run_id)&
             (GridAnnualDossierV78.proposed_run_id==body.proposed_run_id)))):
            raise HTTPException(409,'BENEFIT_ALREADY_USED_IN_V78_GRID_DCF')
        b,p,bc,pc,ok,reasons=prepare_pair(db,org_id,body)
        if b.asset_id!=body.asset_id:
            raise HTTPException(409,'DOSSIER_ASSET_MISMATCH')
        if not ok:
            raise HTTPException(409,{'code':'PHYSICAL_BASELINE_MISMATCH','invariants':reasons})
        try:
            result=evaluate_feeder_alternative(bc,pc,b.result['result'],p.result['result'],body.finance)
        except ValueError as ex:
            raise HTTPException(409,str(ex)) from None
        params=body.finance.model_dump(mode='json')
        report={'baseline_run_id':b.id,'proposed_run_id':p.id,
                'baseline_result_sha256':b.result_sha256,'proposed_result_sha256':p.result_sha256,
                'finance_inputs':params,'economic_result':result,
                'status':'SYNTHETIC_RESEARCH_ONLY_NO_APPROVAL'}
        x=GridEconomicDossier(org_id=org_id,asset_id=body.asset_id,baseline_run_id=b.id,
           proposed_run_id=p.id,benefit_key=body.benefit_key,finance_input=params,result=report,
           result_sha256=sha(report),pinned_engine_sha256=source_hash(),created_by=u.id)
        try:
            db.add(x);db.flush()
            if db.bind.dialect.name!='postgresql':
                record_audit(db,org_id,u.id,'grid.economics.synthetic.created','grid_economic_dossier',x.id,
                     {'result_sha256':x.result_sha256,'benefit_key':body.benefit_key},audit_secret)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409,'DUPLICATE_FINANCIAL_EFFECT_OR_SCENARIO_PAIR') from None
        return {'dossier_id':x.id,'status':'SYNTHETIC_RESEARCH_ONLY_NO_APPROVAL',
                'result_sha256':x.result_sha256,'report':report,
                'can_be_submitted_to_investment_approval':False}

    @r.get('/v73/orgs/{org_id}/economic-dossiers')
    def list_dossiers(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','viewer'},u,db)
        rows=db.scalars(select(GridEconomicDossier).where(GridEconomicDossier.org_id==org_id).order_by(GridEconomicDossier.created_at.desc()).limit(200)).all()
        return [{'id':x.id,'asset_id':x.asset_id,'benefit_key':x.benefit_key,
                 'status':'SYNTHETIC_RESEARCH_ONLY_NO_APPROVAL'} for x in rows]

    @r.get('/v73/orgs/{org_id}/economic-dossiers/{dossier_id}')
    def show_dossier(org_id:str,dossier_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','viewer'},u,db)
        x=db.scalar(select(GridEconomicDossier).where(GridEconomicDossier.org_id==org_id,GridEconomicDossier.id==dossier_id))
        if x is None:raise HTTPException(404,'Dossier unavailable')
        if x.result_sha256!=sha(x.result):
            raise HTTPException(409,'DOSSIER_HASH_MISMATCH')
        return {'dossier_id':x.id,'report':x.result,'status':'SYNTHETIC_RESEARCH_ONLY_NO_APPROVAL'}

    @r.post('/v73/orgs/{org_id}/economic-dossiers/{dossier_id}/reproduce')
    def reproduce_dossier(org_id:str,dossier_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','auditor'},u,db)
        x=db.scalar(select(GridEconomicDossier).where(GridEconomicDossier.org_id==org_id,GridEconomicDossier.id==dossier_id))
        if x is None:raise HTTPException(404,'Dossier unavailable')
        if x.result_sha256!=sha(x.result) or x.pinned_engine_sha256!=source_hash():
            raise HTTPException(409,'PINNED_FINANCIAL_MODEL_OR_REPORT_CHANGED')
        b,p,bc,pc,ok,reasons=prepare_pair(db,org_id,ComparisonInput(baseline_run_id=x.baseline_run_id,proposed_run_id=x.proposed_run_id))
        if not ok:raise HTTPException(409,'INVARIANT_DRIFT')
        bnew=compute_study('gridloss',b.case_payload)
        pnew=compute_study('gridloss',p.case_payload)
        if sha(bnew)!=b.result_sha256 or sha(pnew)!=p.result_sha256:
            raise HTTPException(409,'ENGINEERING_REPRODUCTION_DIVERGED')
        fresh=evaluate_feeder_alternative(bc,pc,bnew['result'],pnew['result'],LabFinance.model_validate(x.finance_input))
        if fresh!=x.result['economic_result']:
            raise HTTPException(409,'FINANCIAL_REPRODUCTION_DIVERGED')
        return {'dossier_id':x.id,'reproduced':True,'engineering_inputs_pinned':True,
                'financial_assumptions_pinned':True,'independent_field_signoff':False,
                'industrial_approval_eligible':False}

    app.include_router(r)
