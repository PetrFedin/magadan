"""V7.8 synthetic grid DCF: pinned studies + exclusive WBS + temporal costs.

No route attaches these reports to V7 authorized initiatives, bank disbursements,
SCADA, permits or signed engineering evidence.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .storage import (GridAnnualDossierV78, ResearchProgramme, ResearchProgrammeStudy,
                      ResearchProgrammeFinance, StudyRun, User, GridEconomicDossier, AssurancePackV76)
from .grid_cashflow_v78 import GridDCFInputV78, evaluate_grid_dcf_v78
from .programme_v74 import CapitalScreen
from .programme_api_v74 import programme_engine_hash
from .radial_grid import RadialCase, physical_comparability
from .studies_api import algorithm_hash
from .studies import compute_study, Strict


class CreateGridDCF(Strict):
    programme_id: str=Field(min_length=1,max_length=120)
    baseline_run_id:str=Field(min_length=1,max_length=120)
    proposed_run_id:str=Field(min_length=1,max_length=120)
    parameters:GridDCFInputV78


def implementation_sha256():
    dig=sha256()
    for name in ('grid_cashflow_v78.py','grid_cashflow_api_v78.py'):
        path=Path(__file__).with_name(name)
        dig.update(name.encode());dig.update(path.read_bytes())
    return dig.hexdigest()


def install_grid_cashflow_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical):
    r=APIRouter()

    def reconstruct(db,org_id,body):
        if body.baseline_run_id==body.proposed_run_id:
            raise HTTPException(409,'BASELINE_EQUALS_ALTERNATIVE')
        p=db.scalar(select(ResearchProgramme).where(ResearchProgramme.org_id==org_id,
                                                    ResearchProgramme.id==body.programme_id))
        if not p:raise HTTPException(404,'Research programme unavailable')
        if sha(p.snapshot)!=p.snapshot_sha256 or p.snapshot.get('pinned_programme_engine_sha256')!=programme_engine_hash():
            raise HTTPException(409,'PINNED_PROGRAMME_DIVERGED')
        if (not p.capital_input or p.snapshot.get('capital')!=p.capital_input
            or p.snapshot.get('cannot_be_used_for_field_approval') is not True):
            raise HTTPException(409,'EXCLUSIVE_LAB_WBS_REQUIRED')
        if (p.snapshot.get('financial_dossier_ids') or p.snapshot.get('heat_screenings') or
            p.snapshot.get('links') or len(p.snapshot.get('study_ids',[]))!=2):
            raise HTTPException(409,'WBS_MUST_BE_SCOPED_TO_ONE_ENGINEERING_MEASURE')
        if set(p.snapshot['study_ids'])!={body.baseline_run_id,body.proposed_run_id}:
            raise HTTPException(409,'WBS_STUDY_PAIR_MISMATCH')
        links=set(db.scalars(select(ResearchProgrammeStudy.study_id).where(
            ResearchProgrammeStudy.org_id==org_id,ResearchProgrammeStudy.programme_id==p.id)).all())
        if links!=set(p.snapshot['study_ids']):
            raise HTTPException(409,'PROGRAMME_STUDY_MEMBERSHIP_DRIFT')
        if db.scalar(select(ResearchProgrammeFinance.id).where(
            ResearchProgrammeFinance.org_id==org_id,ResearchProgrammeFinance.programme_id==p.id)):
            raise HTTPException(409,'WBS_ALREADY_ASSIGNED_TO_EXISTING_FINANCE_DOSSIER')
        runs=[]
        for sid in (body.baseline_run_id,body.proposed_run_id):
            run=db.scalar(select(StudyRun).where(StudyRun.org_id==org_id,StudyRun.id==sid))
            if not run:raise HTTPException(404,'Source study unavailable')
            if asset(db,org_id,run.asset_id).classification!='LAB_REFERENCE':
                raise HTTPException(409,'REAL_ASSET_NOT_ALLOWED_IN_RESEARCH_DCF')
            if run.module!='gridloss' or run.case_payload.get('model_kind')!='radial_ac_v73':
                raise HTTPException(409,'REQUIRES_SYNTHETIC_RADIAL_STUDY')
            if not run.source_ref.startswith('SYNTHETIC-'):
                raise HTTPException(409,'NON_SYNTHETIC_SOURCE_REJECTED')
            expected=sha({'org_id':run.org_id,'asset_id':run.asset_id,'module':run.module,
                'source_ref':run.source_ref,'scenario_group':run.scenario_group,'case':run.case_payload})
            if expected!=run.input_sha256 or sha(run.result)!=run.result_sha256 or run.engine_sha256!=algorithm_hash():
                raise HTTPException(409,'SOURCE_STUDY_OR_ENGINE_INTEGRITY_FAILED')
            try:recomputed=compute_study('gridloss',run.case_payload)
            except Exception as exc:raise HTTPException(409,'ENGINEERING_SOURCE_REPLAY_FAILED') from exc
            if sha(recomputed)!=run.result_sha256:
                raise HTTPException(409,'ENGINEERING_SOURCE_RECOMPUTATION_DIVERGED')
            runs.append(run)
        b,a=runs
        if (b.org_id,b.asset_id,b.scenario_group)!=(a.org_id,a.asset_id,a.scenario_group):
            raise HTTPException(409,'DIFFERENT_ASSET_OR_SCENARIO_GROUP')
        bc,ac=RadialCase.model_validate(b.case_payload),RadialCase.model_validate(a.case_payload)
        ok,reasons=physical_comparability(bc,ac)
        if not ok:raise HTTPException(409,{'code':'ENGINEERING_INVARIANTS_BROKEN','reasons':reasons})
        try:
            report=evaluate_grid_dcf_v78(bc,ac,b.result['result'],a.result['result'],
                                         CapitalScreen.model_validate(p.capital_input),body.parameters)
        except (ValueError,ArithmeticError) as exc:
            raise HTTPException(422,str(exc)[:350]) from None
        pins={'programme_sha256':p.snapshot_sha256,'baseline_input_sha256':b.input_sha256,
              'baseline_result_sha256':b.result_sha256,'alternative_input_sha256':a.input_sha256,
              'alternative_result_sha256':a.result_sha256,'study_engine_sha256':b.engine_sha256,
              'grid_dcf_engine_sha256':implementation_sha256()}
        return p,b,a,pins,report

    def pin(db,org_id,row):
        if sha(row.finance_input)!=row.input_sha256 or sha(row.report)!=row.report_sha256 or implementation_sha256()!=row.engine_sha256:
            raise HTTPException(409,'DCF_SOURCE_INTEGRITY_OR_CODE_VERSION_FAILURE')
        if row.report.get('industrial_approval_eligible') is not False:
            raise HTTPException(409,'ILLEGAL_APPROVAL_STATUS')
        body=CreateGridDCF.model_validate(row.finance_input)
        p,b,a,pins,fresh=reconstruct(db,org_id,body)
        if sha(pins)!=row.source_bundle_sha256:
            raise HTTPException(409,'SOURCE_BUNDLE_PIN_CHANGED')
        if row.benefit_key!=body.parameters.benefit_key or row.programme_id!=p.id or row.asset_id!=b.asset_id:
            raise HTTPException(409,'DCF_RELATIONAL_LINK_DRIFT')
        if sha(fresh)!=row.report_sha256:
            raise HTTPException(409,'DCF_REPRODUCTION_DIFFERENCE')
        return body,fresh

    @r.get('/v78/meta/readiness')
    def readiness():
        return {'version':'7.8','lab_only':True,'annual_hourly_window_valuation':True,
            'capex_only_from_pinned_wbs':True,'postgresql_rls_native_accepted':False,
            'external_independent_accepted':False,'real_magadan_data':False,'production_ready':False}

    @r.post('/v78/orgs/{org_id}/grid-annual-dossiers',status_code=201)
    def create(org_id:str,body:CreateGridDCF,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'economist'},u,db)
        p,b,a,pins,report=reconstruct(db,org_id,body)
        # Research-only cross-version guard. Atomic cross-table uniqueness still
        # requires an authoritative benefit registry at PostgreSQL acceptance.
        other_grid=db.scalar(select(GridEconomicDossier.id).where(
            GridEconomicDossier.org_id==org_id,
            (GridEconomicDossier.benefit_key==body.parameters.benefit_key) |
            ((GridEconomicDossier.baseline_run_id==b.id)&(GridEconomicDossier.proposed_run_id==a.id))))
        other_pack=db.scalar(select(AssurancePackV76.id).where(
            AssurancePackV76.org_id==org_id,AssurancePackV76.benefit_key==body.parameters.benefit_key))
        if other_grid or other_pack:
            raise HTTPException(409,'BENEFIT_ALREADY_USED_IN_ANOTHER_FINANCIAL_MODULE')
        payload=body.model_dump(mode='json')
        if len(canonical(payload).encode())>110000 or len(canonical(report).encode())>1050000:
            raise HTTPException(413,'LAB_REPORT_TOO_LARGE')
        row=GridAnnualDossierV78(org_id=org_id,asset_id=b.asset_id,programme_id=p.id,
            baseline_run_id=b.id,proposed_run_id=a.id,benefit_key=body.parameters.benefit_key,
            source_bundle_sha256=sha(pins),finance_input=payload,input_sha256=sha(payload),
            report=report,report_sha256=sha(report),engine_sha256=implementation_sha256(),created_by=u.id)
        try:
            db.add(row);db.flush()
            if db.bind.dialect.name!='postgresql':
                record_audit(db,org_id,u.id,'grid.annual_dcf.lab.created',
                             'grid_annual_dossiers_v78',row.id,
                             {'report_sha256':row.report_sha256,'programme_id':p.id,'scope':'LAB_ONLY'},audit_secret)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409,'DUPLICATED_WBS_OR_BENEFIT_OR_GRID_PAIR') from None
        return {'id':row.id,'report_sha256':row.report_sha256,'report':report,
                'industrial_approval_eligible':False}

    @r.get('/v78/orgs/{org_id}/grid-annual-dossiers')
    def listing(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        rows=db.scalars(select(GridAnnualDossierV78).where(GridAnnualDossierV78.org_id==org_id)
            .order_by(GridAnnualDossierV78.created_at.desc()).limit(100)).all()
        return [{'id':x.id,'programme_id':x.programme_id,'benefit_key':x.benefit_key,
                 'status':'SYNTHETIC_RESEARCH_NOT_APPROVED'} for x in rows]

    def load(db,org_id,item_id):
        x=db.scalar(select(GridAnnualDossierV78).where(GridAnnualDossierV78.org_id==org_id,
                                                          GridAnnualDossierV78.id==item_id))
        if not x:raise HTTPException(404,'Lab annual dossier unavailable')
        return x

    @r.get('/v78/orgs/{org_id}/grid-annual-dossiers/{item_id}')
    def get(org_id:str,item_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        item=load(db,org_id,item_id)
        body,fresh=pin(db,org_id,item)
        return {'id':item.id,'report':fresh,'report_sha256':item.report_sha256,
                'reproduced_from_sources':True,'industrial_approval_eligible':False}

    @r.post('/v78/orgs/{org_id}/grid-annual-dossiers/{item_id}/reproduce')
    def reproduce(org_id:str,item_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'auditor'},u,db)
        item=load(db,org_id,item_id)
        body,fresh=pin(db,org_id,item)
        return {'id':item.id,'reproduced':True,'report_sha256':sha(fresh),
                'field_approved':False,'industrial_approval_eligible':False}

    app.include_router(r)
