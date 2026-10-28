"""V7.4 synthetic interdisciplinary assurance: tenant scoped and append only."""
from __future__ import annotations
from pathlib import Path
import hashlib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .storage import (
    User,Asset,StudyRun,GridEconomicDossier,ResearchProgramme,
    ResearchProgrammeStudy,ResearchProgrammeFinance,ResearchProgrammeLink,
)
from .programme_v74 import ProgrammeNew,ProgrammeLink,CapitalScreen,HeatScenarioScreen,screen_capital,evaluate_programme
from .studies_api import algorithm_hash
from .studies import compute_study
from .radial_grid import RadialCase, physical_comparability
from .finance_evidence import LabFinance, evaluate_feeder_alternative
from .grid_dossiers_api import source_hash as financial_engine_hash


def programme_engine_hash()->str:
    digest=hashlib.sha256()
    for name in ('programme_v74.py','programme_api_v74.py','heat_economics_v74.py'):
        p=Path(__file__).with_name(name)
        digest.update(name.encode());digest.update(p.read_bytes())
    return digest.hexdigest()


def install_programme_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical):
    router=APIRouter()

    def load_studies(db,org_id,ids):
        results=[]
        for id in ids:
            s=db.scalar(select(StudyRun).where(StudyRun.id==id,StudyRun.org_id==org_id))
            if s is None:raise HTTPException(404,'Study not available in organization')
            a=asset(db,org_id,s.asset_id)
            if a.classification!='LAB_REFERENCE':raise HTTPException(409,'RESEARCH_PACKAGE_REQUIRES_LAB_ASSETS')
            fingerprint=sha({'org_id':s.org_id,'asset_id':s.asset_id,'module':s.module,
                'source_ref':s.source_ref,'scenario_group':s.scenario_group,'case':s.case_payload})
            if fingerprint!=s.input_sha256 or sha(s.result)!=s.result_sha256:
                raise HTTPException(409,'STUDY_SOURCE_INTEGRITY_FAILURE')
            if s.engine_sha256!=algorithm_hash():raise HTTPException(409,'STUDY_ENGINE_VERSION_NOT_PINNED')
            if not s.source_ref.startswith('SYNTHETIC-'):
                raise HTTPException(409,'UNAUTHORIZED_REAL_DATA_MIXED_IN_LAB')
            results.append({'id':s.id,'module':s.module,'asset_id':s.asset_id,'scenario_group':s.scenario_group,
                'result':s.result,'case_payload':s.case_payload,'input_sha256':s.input_sha256,'result_sha256':s.result_sha256,
                'engine_sha256':s.engine_sha256})
        return results

    def load_financial_dossiers(db,org_id,ids):
        out=[]
        for id in ids:
            d=db.scalar(select(GridEconomicDossier).where(GridEconomicDossier.id==id,
                     GridEconomicDossier.org_id==org_id))
            if d is None:raise HTTPException(404,'Finance dossier not available in organization')
            if sha(d.result)!=d.result_sha256 or d.pinned_engine_sha256!=financial_engine_hash():
                raise HTTPException(409,'FINANCIAL_SOURCE_INTEGRITY_OR_ENGINE_CHANGED')
            if d.result.get('baseline_run_id')!=d.baseline_run_id or d.result.get('proposed_run_id')!=d.proposed_run_id:
                raise HTTPException(409,'FINANCIAL_REFERENCE_MISMATCH')
            if d.result.get('finance_inputs')!=d.finance_input:
                raise HTTPException(409,'FINANCIAL_ASSUMPTIONS_MISMATCH')
            out.append({'id':d.id,'asset_id':d.asset_id,'baseline_run_id':d.baseline_run_id,
                'proposed_run_id':d.proposed_run_id,'benefit_key':d.benefit_key,
                'result':d.result,'result_sha256':d.result_sha256})
        return out

    def build_snapshot(reference_code,title,purpose,study_ids,finance_ids,links,capital,studies,dossiers,heat_screenings=None):
        result=evaluate_programme(studies,dossiers,links,capital,heat_screenings)
        source={'studies':[{'id':s['id'],'input_sha256':s['input_sha256'],
                 'result_sha256':s['result_sha256'],'engine_sha256':s['engine_sha256']} for s in studies],
                'financial_dossiers':[{'id':d['id'],'result_sha256':d['result_sha256']} for d in dossiers]}
        return {'release':'7.4-LAB_ONLY','reference_code':reference_code,'title':title,'purpose':purpose,
                'study_ids':study_ids,'financial_dossier_ids':finance_ids,
                'links':[l.model_dump(mode='json') for l in links],
                'heat_screenings':[h.model_dump(mode='json') for h in (heat_screenings or [])],
                'capital':capital.model_dump(mode='json') if capital else None,
                'pinned_programme_engine_sha256':programme_engine_hash(),
                'source_versions':source,'screening':result,
                'cannot_be_used_for_field_approval':True}

    def get_programme(db,org_id,id):
        x=db.scalar(select(ResearchProgramme).where(ResearchProgramme.org_id==org_id,
                   ResearchProgramme.id==id))
        if not x:raise HTTPException(404,'Research programme unavailable')
        return x

    def reconstruct(db,org_id,x,deep_verify=False):
        if sha(x.snapshot)!=x.snapshot_sha256:
            raise HTTPException(409,'PROGRAMME_SNAPSHOT_INTEGRITY_FAILURE')
        if x.snapshot.get('pinned_programme_engine_sha256')!=programme_engine_hash():
            raise HTTPException(409,'PROGRAMME_ENGINE_VERSION_MISMATCH')
        ids=[r.study_id for r in db.scalars(select(ResearchProgrammeStudy).where(
             ResearchProgrammeStudy.org_id==org_id,ResearchProgrammeStudy.programme_id==x.id)).all()]
        fids=[r.dossier_id for r in db.scalars(select(ResearchProgrammeFinance).where(
              ResearchProgrammeFinance.org_id==org_id,ResearchProgrammeFinance.programme_id==x.id)).all()]
        edges=[ProgrammeLink(from_study_id=e.from_study_id,to_study_id=e.to_study_id,relationship=e.relationship)
               for e in db.scalars(select(ResearchProgrammeLink).where(
                 ResearchProgrammeLink.org_id==org_id,ResearchProgrammeLink.programme_id==x.id)).all()]
        stored_ids=x.snapshot['study_ids'];stored_fids=x.snapshot['financial_dossier_ids']
        if set(ids)!=set(stored_ids) or len(ids)!=len(stored_ids) or set(fids)!=set(stored_fids) or len(fids)!=len(stored_fids):
            raise HTTPException(409,'PROGRAMME_RELATIONAL_LINK_DRIFT')
        if set((e.from_study_id,e.to_study_id,e.relationship) for e in edges)!=set(
            (e['from_study_id'],e['to_study_id'],e['relationship']) for e in x.snapshot['links']):
            raise HTTPException(409,'PROGRAMME_SEMANTIC_EDGE_DRIFT')
        studies=load_studies(db,org_id,stored_ids)
        dossiers=load_financial_dossiers(db,org_id,stored_fids)
        if deep_verify:
            # This checks actual mathematical outputs, not only database hashes.
            # It does NOT constitute an external independent engineering reference.
            by_study={z['id']:z for z in studies}
            for study in studies:
                recomputed=compute_study(study['module'],study['case_payload'])
                if sha(recomputed)!=study['result_sha256']:
                    raise HTTPException(409, 'UNDERLYING_STUDY_REPLAY_DIVERGED')
            for dossier in dossiers:
                base=by_study[dossier['baseline_run_id']]
                alt=by_study[dossier['proposed_run_id']]
                if base['module']!='gridloss' or alt['module']!='gridloss':
                    raise HTTPException(409,'INVALID_FINANCIAL_MODEL_PAIR')
                try:
                    bc=RadialCase.model_validate(base['case_payload'])
                    pc=RadialCase.model_validate(alt['case_payload'])
                    matched,_=physical_comparability(bc,pc)
                    if not matched:
                        raise HTTPException(409,'UNDERLYING_FINANCIAL_BASELINE_DRIFT')
                    current=evaluate_feeder_alternative(
                        bc,pc,base['result']['result'],alt['result']['result'],
                        LabFinance.model_validate(dossier['result']['finance_inputs']))
                except HTTPException:
                    raise
                except (TypeError,ValueError) as ex:
                    raise HTTPException(409, 'UNDERLYING_FINANCIAL_REPLAY_FAILED') from ex
                if current!=dossier['result']['economic_result']:
                    raise HTTPException(409, 'UNDERLYING_FINANCIAL_REPLAY_DIVERGED')
        capital=CapitalScreen.model_validate(x.snapshot['capital']) if x.snapshot['capital'] else None
        replay=build_snapshot(x.reference_code,x.title,x.purpose,stored_ids,stored_fids,
              [ProgrammeLink.model_validate(z) for z in x.snapshot['links']],capital,studies,dossiers,
              [HeatScenarioScreen.model_validate(z) for z in x.snapshot.get('heat_screenings',[])])
        if sha(replay)!=x.snapshot_sha256:
            raise HTTPException(409,'PROGRAMME_REPRODUCTION_MISMATCH')
        return replay

    @router.get('/v74/meta/readiness')
    def meta():
        return {'release':'7.4','production_ready':False,'region':'MAGADAN_RESEARCH_CONCEPT',
                'six_modules_research_connected':True,'immutable_programme_snapshots':True,
                'cross_module_links':'SEMANTIC_ONLY_NO_NUMERICAL_COUPLING',
                'WBS_financial_screening':'SYNTHETIC_NO_APPROVED_ESTIMATE',
                'postgresql_native_RLS':'NOT_ACCEPTED',
                'field_data_magadan':'NOT_AVAILABLE',
                'can_approve_real_investments':False}

    @router.post('/v74/orgs/{org_id}/capital-screen',status_code=200)
    def capital_screen(org_id:str,body:CapitalScreen,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'economist','engineer','manager','auditor'},u,db)
        return screen_capital(body)

    @router.post('/v74/orgs/{org_id}/programmes',status_code=201)
    def create(org_id:str,body:ProgrammeNew,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'economist'},u,db)
        if db.scalar(select(ResearchProgramme).where(ResearchProgramme.org_id==org_id,
                     ResearchProgramme.reference_code==body.reference_code)):
            raise HTTPException(409,'RESEARCH_PROGRAMME_REFERENCE_ALREADY_USED')
        studies=load_studies(db,org_id,body.study_ids)
        dossiers=load_financial_dossiers(db,org_id,body.financial_dossier_ids)
        try:
            snapshot=build_snapshot(body.reference_code,body.title,body.purpose,
                body.study_ids,body.financial_dossier_ids,body.links,body.capital,studies,dossiers,body.heat_screenings)
        except ValueError as ex:
            raise HTTPException(422,{'code':'RESEARCH_PROGRAMME_INCOMPATIBLE','detail':str(ex)}) from None
        if len(canonical(snapshot).encode('utf-8'))>350000:
            raise HTTPException(413,'PROGRAMME_PACKAGE_TOO_LARGE')
        x=ResearchProgramme(org_id=org_id,reference_code=body.reference_code,
            title=body.title,purpose=body.purpose,capital_input=body.capital.model_dump(mode='json') if body.capital else None,
            snapshot=snapshot,snapshot_sha256=sha(snapshot),created_by=u.id)
        try:
            db.add(x);db.flush()
            for id in body.study_ids:
                db.add(ResearchProgrammeStudy(org_id=org_id,programme_id=x.id,study_id=id))
            for id in body.financial_dossier_ids:
                db.add(ResearchProgrammeFinance(org_id=org_id,programme_id=x.id,dossier_id=id))
            for e in body.links:
                db.add(ResearchProgrammeLink(org_id=org_id,programme_id=x.id,
                    from_study_id=e.from_study_id,to_study_id=e.to_study_id,relationship=e.relationship))
            db.flush()
            if db.bind.dialect.name!='postgresql':
                record_audit(db,org_id,u.id,'research.programme.synthetic.created','research_programme',x.id,
                   {'sha256':x.snapshot_sha256,'reference_code':x.reference_code,'scope':'LAB_ONLY'},audit_secret)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409,'PROGRAMME_REFERENCE_OR_CROSS_TENANT_RELATION_REJECTED') from None
        return {'id':x.id,'reference_code':x.reference_code,'snapshot_sha256':x.snapshot_sha256,
                'summary':snapshot['screening'],'production_ready':False,'industrial_approval_eligible':False}

    @router.get('/v74/orgs/{org_id}/programmes')
    def listing(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        rows=db.scalars(select(ResearchProgramme).where(ResearchProgramme.org_id==org_id)
              .order_by(ResearchProgramme.created_at.desc()).limit(200)).all()
        return [{'id':r.id,'reference_code':r.reference_code,'title':r.title,
                 'snapshot_sha256':r.snapshot_sha256,'status':'SYNTHETIC_NON_AUTHORITATIVE'} for r in rows]

    @router.get('/v74/orgs/{org_id}/programmes/{programme_id}')
    def detail(org_id:str,programme_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        x=get_programme(db,org_id,programme_id)
        replay=reconstruct(db,org_id,x)
        return {'id':x.id,'snapshot':replay,'snapshot_sha256':x.snapshot_sha256,
                'industrial_approval_eligible':False}

    @router.post('/v74/orgs/{org_id}/programmes/{programme_id}/reproduce')
    def reproduce(org_id:str,programme_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'auditor','engineer'},u,db)
        x=get_programme(db,org_id,programme_id)
        replay=reconstruct(db,org_id,x,deep_verify=True)
        return {'id':x.id,'reproduced':True,'engineering_models_reexecuted':True,
                'financial_dossiers_recalculated':True,'source_count':len(replay['study_ids']),
                'financial_dossier_count':len(replay['financial_dossier_ids']),
                'programme_sha256':x.snapshot_sha256,
                'independent_engineering_validation':False,
                'industrial_approval_eligible':False}

    app.include_router(router)
