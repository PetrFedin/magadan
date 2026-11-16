"""V7.6: tenant-protected synthetic value assurance on version-pinned evidence.

NO industrial approval route, no actual Magadan asset access, no implied grants.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field,model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .storage import User,StudyRun,ResearchHandoff,ResearchProgramme,ResearchProgrammeStudy,AssurancePackV76,GridAnnualDossierV78
from .studies import Strict,ForecastCase,CascadeCase
from .studies_api import algorithm_hash
from .handoff_api_v75 import HandoffNew,handoff_engine_hash
from .coupling_v75 import couple_forecast_to_cascade,build_maintenance_decision
from .programme_v74 import CapitalScreen
from .assurance_v76 import RoutingSpecification,AnnualValueModel,routed_ensemble,discounted_value_model

class AssuranceNewV76(Strict):
    reference_code:str=Field(min_length=10,max_length=100,pattern=r'^LAB-[A-Za-z0-9_-]+$')
    programme_id:str=Field(min_length=1,max_length=100)
    handoff_ids:list[str]=Field(min_length=1,max_length=8)
    routing_handoff_id:str|None=None
    routing:RoutingSpecification|None=None
    finance:AnnualValueModel
    scope:Literal['SYNTHETIC_DECISION_EVIDENCE_NOT_APPROVAL']='SYNTHETIC_DECISION_EVIDENCE_NOT_APPROVAL'

    @model_validator(mode='after')
    def semantics(self):
        if len(self.handoff_ids)!=len(set(self.handoff_ids)):
            raise ValueError('DUPLICATE_HANDOFF_ID')
        if bool(self.routing_handoff_id)!=bool(self.routing):
            raise ValueError('ROUTING_SETTINGS_REQUIRE_HANDOFF_REFERENCE')
        if self.routing_handoff_id and self.routing_handoff_id not in self.handoff_ids:
            raise ValueError('ROUTING_HANDOFF_MUST_BE_ATTACHED')
        return self


def engine_fingerprint()->str:
    h=sha256()
    for name in ('assurance_v76.py','assurance_api_v76.py'):
        f=Path(__file__).with_name(name)
        h.update(name.encode());h.update(f.read_bytes())
    return h.hexdigest()


def install_assurance_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical):
    router=APIRouter()

    def load_source_study(db:Session,org_id:str,sid:str):
        study=db.scalar(select(StudyRun).where(StudyRun.org_id==org_id,StudyRun.id==sid))
        if study is None:raise HTTPException(404,'Study source not available')
        if asset(db,org_id,study.asset_id).classification!='LAB_REFERENCE':
            raise HTTPException(409,'ASSURANCE_REQUIRES_LAB_REFERENCE_ASSET')
        source={'org_id':study.org_id,'asset_id':study.asset_id,'module':study.module,
                'source_ref':study.source_ref,'scenario_group':study.scenario_group,'case':study.case_payload}
        if not study.source_ref.startswith('SYNTHETIC-') or sha(source)!=study.input_sha256 or sha(study.result)!=study.result_sha256 or study.engine_sha256!=algorithm_hash():
            raise HTTPException(409,'ASSURANCE_STUDY_PROVENANCE_FAILED')
        return study

    def checked_handoff(db:Session,org_id:str,hid:str,programme:ResearchProgramme,attached:set[str]):
        h=db.scalar(select(ResearchHandoff).where(ResearchHandoff.org_id==org_id,ResearchHandoff.id==hid))
        if h is None:raise HTTPException(404,'Handoff not available')
        if h.programme_id!=programme.id:raise HTTPException(409,'HANDOFF_NOT_PINNED_TO_SELECTED_PROGRAMME')
        if sha(h.snapshot)!=h.snapshot_sha256 or sha(h.input_payload)!=h.input_sha256 or h.engine_sha256!=handoff_engine_hash():
            raise HTTPException(409,'HANDOFF_DOCUMENT_OR_ENGINE_CHANGED')
        if h.snapshot.get('pinned_engine_sha256')!=h.engine_sha256 or h.snapshot.get('result_sha256')!=sha(h.snapshot.get('result')):
            raise HTTPException(409,'HANDOFF_RESULT_FINGERPRINT_MISMATCH')
        if h.snapshot.get('industrial_approval_eligible') is not False:
            raise HTTPException(409,'UNSUPPORTED_INDUSTRIAL_HANDOFF')
        if h.input_payload.get('programme_sha256')!=programme.snapshot_sha256:
            raise HTTPException(409,'HANDOFF_PROGRAMME_VERSION_MISMATCH')
        try:
            contract=HandoffNew.model_validate(h.input_payload['inputs'])
        except (ValueError,KeyError,TypeError):
            raise HTTPException(409,'HANDOFF_INPUT_CONTRACT_INVALID') from None
        if contract.kind!=h.kind or contract.programme_id!=programme.id or contract.left_study_id!=h.left_study_id or contract.right_study_id!=h.right_study_id:
            raise HTTPException(409,'HANDOFF_DATABASE_RELATION_CHANGED')
        source_ids=[h.left_study_id]+([h.right_study_id] if h.right_study_id else [])
        if not set(source_ids).issubset(attached):raise HTTPException(409,'HANDOFF_STUDIES_NOT_ATTACHED_TO_PROGRAMME')
        studies=[load_source_study(db,org_id,id) for id in source_ids]
        if any(s.asset_id!=h.asset_id for s in studies):raise HTTPException(409,'HANDOFF_ASSET_MISMATCH')
        pins=[{'id':s.id,'org_id':s.org_id,'asset_id':s.asset_id,'module':s.module,'input_sha256':s.input_sha256,
               'result_sha256':s.result_sha256,'engine_sha256':s.engine_sha256} for s in studies]
        if pins!=h.snapshot.get('source_pins') or pins!=h.input_payload.get('source_pins'):
            raise HTTPException(409,'HANDOFF_SOURCE_PINS_CHANGED')
        if contract.kind=='forecast_to_cascade':
            if [s.module for s in studies]!=['hydroforecast','cascade'] or studies[0].scenario_group!=studies[1].scenario_group:
                raise HTTPException(409,'HANDOFF_MODEL_TYPES_CHANGED')
            reproduced=couple_forecast_to_cascade(ForecastCase.model_validate(studies[0].case_payload),
                 CascadeCase.model_validate(studies[1].case_payload),contract.forecast_bridge)
        elif contract.kind=='turbine_to_maintenance':
            if [s.module for s in studies]!=['turbine']:raise HTTPException(409,'HANDOFF_MODEL_TYPES_CHANGED')
            reproduced=build_maintenance_decision(studies[0].result['result'],contract.maintenance_bridge)
        else:raise HTTPException(409,'UNKNOWN_HANDOFF_KIND')
        if reproduced!=h.snapshot['result']:
            raise HTTPException(409,'HANDOFF_RECOMPUTATION_MISMATCH')
        return h,studies

    def build(db:Session,org_id:str,body:AssuranceNewV76):
        programme=db.scalar(select(ResearchProgramme).where(ResearchProgramme.org_id==org_id,ResearchProgramme.id==body.programme_id))
        if programme is None:raise HTTPException(404,'Research programme not available')
        if sha(programme.snapshot)!=programme.snapshot_sha256:
            raise HTTPException(409,'ASSURANCE_PARENT_PROGRAMME_CHANGED')
        if programme.capital_input is None or programme.snapshot.get('capital')!=programme.capital_input:
            raise HTTPException(409,'ASSURANCE_REQUIRES_PINNED_WBS_IN_PARENT')
        if programme.snapshot.get('cannot_be_used_for_field_approval') is not True:
            raise HTTPException(409,'ASSURANCE_RESEARCH_STATUS_REQUIRED')
        attached=set(db.scalars(select(ResearchProgrammeStudy.study_id).where(ResearchProgrammeStudy.org_id==org_id,
                               ResearchProgrammeStudy.programme_id==programme.id)).all())
        if set(programme.snapshot.get('study_ids',[]))!=attached:
            raise HTTPException(409,'PROGRAMME_STUDY_LINKS_CHANGED')
        sources={};verified={}
        for hid in body.handoff_ids:
            h,studies=checked_handoff(db,org_id,hid,programme,attached)
            sources[hid]={'kind':h.kind,'handoff_sha256':h.snapshot_sha256,'handoff_engine_sha256':h.engine_sha256,
                          'study_pins':[{'id':s.id,'input_sha256':s.input_sha256,'result_sha256':s.result_sha256} for s in studies]}
            verified[hid]=(h,studies)
        try:
            capital=CapitalScreen.model_validate(programme.capital_input)
            financial=discounted_value_model(body.finance,capital)
            routing=None
            if body.routing_handoff_id:
                h,s=verified[body.routing_handoff_id]
                if h.kind!='forecast_to_cascade':raise ValueError('ROUTING_REQUIRES_FORECAST_BRIDGE')
                routing=routed_ensemble(ForecastCase.model_validate(s[0].case_payload),
                                        CascadeCase.model_validate(s[1].case_payload),body.routing)
        except (ValueError,ArithmeticError) as ex:
            raise HTTPException(422,{'code':'INVALID_LAB_ASSURANCE','detail':str(ex)[:240]}) from None
        source_bundle_sha256=sha({'programme_id':programme.id,'handoff_ids':sorted(body.handoff_ids)})
        snapshot={'release':'7.6-LAB', 'source_bundle_sha256':source_bundle_sha256,'org_id':org_id,'reference_code':body.reference_code,
                  'programme_id':programme.id,'programme_sha256':programme.snapshot_sha256,
                  'handoffs':sources,'financial':financial,'routed_ensemble':routing,
                  'engine_sha256':engine_fingerprint(),
                  'status':'RESEARCH_REVIEW_ONLY_NOT_AN_APPROVED_INVESTMENT',
                  'gates_not_closed':['NATIVE_POSTGRESQL_RLS_NOT_ACCEPTED','EXTERNAL_AUDIT_WORM_NOT_ACCEPTED',
                    'CORPORATE_IDP_MFA_NOT_ACCEPTED','REAL_MAGADAN_DATA_NOT_AUTHORIZED',
                    'INDEPENDENT_ENGINEER_AND_FINANCE_NOT_ACCEPTED',
                    'SITE_SPECIFIC_PERMITS_AND_COST_ESTIMATE_NOT_ACCEPTED'],
                  'industrial_approval_eligible':False}
        return snapshot

    @router.get('/v76/meta/readiness')
    def readiness():
        return {'version':'7.6','laboratory':True,'postgresql_rls_native':'NOT_ACCEPTED',
                'corporate_sso':'NOT_CONNECTED','real_field_data':'NOT_AVAILABLE',
                'routed_ensemble':'SYNTHETIC_LINEAR_TANK_NOT_CALIBRATED',
                'annual_investment':'SYNTHETIC_WBS_AND_EXPLICIT_BENEFITS',
                'production_ready':False,'may_authorize_investments':False}

    @router.post('/v76/orgs/{org_id}/assurance-packs',status_code=201)
    def create(org_id:str,body:AssuranceNewV76,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'economist'},u,db)
        snapshot=build(db,org_id,body)
        if db.scalar(select(GridAnnualDossierV78.id).where(GridAnnualDossierV78.org_id==org_id,
            GridAnnualDossierV78.benefit_key==body.finance.benefit_key)):
            raise HTTPException(409,'BENEFIT_ALREADY_USED_IN_V78_GRID_DCF')
        payload=body.model_dump(mode='json')
        if len(canonical(snapshot).encode('utf-8'))>375000 or len(canonical(payload).encode('utf-8'))>75000:
            raise HTTPException(413,'ASSURANCE_PACKAGE_TOO_LARGE')
        row=AssurancePackV76(org_id=org_id,programme_id=body.programme_id,reference_code=body.reference_code,
                             benefit_key=body.finance.benefit_key,source_bundle_sha256=snapshot['source_bundle_sha256'],input_payload=payload,input_sha256=sha(payload),
                             snapshot=snapshot,snapshot_sha256=sha(snapshot),engine_sha256=engine_fingerprint(),created_by=u.id)
        try:
            db.add(row);db.flush()
            if db.bind.dialect.name!='postgresql':
                record_audit(db,org_id,u.id,'assurance.pack.lab.created','assurance_pack_v76',row.id,
                             {'snapshot_sha256':row.snapshot_sha256,'programme_id':body.programme_id},audit_secret)
            db.commit()
        except IntegrityError:
            db.rollback();raise HTTPException(409,'DUPLICATE_REFERENCE_OR_BENEFIT_KEY') from None
        return {'id':row.id,'snapshot_sha256':row.snapshot_sha256,
                'financial':snapshot['financial'],'routing_status':snapshot['routed_ensemble']['status'] if snapshot['routed_ensemble'] else None,
                'industrial_approval_eligible':False}

    def retrieve(db,org_id,pack_id):
        row=db.scalar(select(AssurancePackV76).where(AssurancePackV76.org_id==org_id,AssurancePackV76.id==pack_id))
        if row is None:raise HTTPException(404,'Assurance pack not available')
        if sha(row.snapshot)!=row.snapshot_sha256 or sha(row.input_payload)!=row.input_sha256 or row.engine_sha256!=engine_fingerprint() or row.source_bundle_sha256!=row.snapshot.get('source_bundle_sha256'):
            raise HTTPException(409,'ASSURANCE_PACK_INTEGRITY_OR_ENGINE_CHANGED')
        if row.snapshot.get('industrial_approval_eligible') is not False:
            raise HTTPException(409,'ASSURANCE_PACK_ILLEGAL_APPROVAL_FLAG')
        return row

    @router.get('/v76/orgs/{org_id}/assurance-packs')
    def list_packs(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        rows=db.scalars(select(AssurancePackV76).where(AssurancePackV76.org_id==org_id)
                        .order_by(AssurancePackV76.created_at.desc()).limit(100)).all()
        return [{'id':x.id,'reference_code':x.reference_code,'programme_id':x.programme_id,
                 'snapshot_sha256':x.snapshot_sha256,'industrial_approval_eligible':False} for x in rows]

    @router.get('/v76/orgs/{org_id}/assurance-packs/{pack_id}')
    def detail(org_id:str,pack_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor','admin','viewer'},u,db)
        row=retrieve(db,org_id,pack_id)
        return {'id':row.id,'snapshot':row.snapshot,'snapshot_sha256':row.snapshot_sha256}

    @router.post('/v76/orgs/{org_id}/assurance-packs/{pack_id}/reproduce')
    def reproduce(org_id:str,pack_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','auditor'},u,db)
        row=retrieve(db,org_id,pack_id)
        body=AssuranceNewV76.model_validate(row.input_payload)
        if body.programme_id!=row.programme_id or body.reference_code!=row.reference_code or body.finance.benefit_key!=row.benefit_key:
            raise HTTPException(409,'ASSURANCE_PACK_RELATIONAL_MISMATCH')
        reconstructed=build(db,org_id,body)
        if reconstructed!=row.snapshot or sha(reconstructed)!=row.snapshot_sha256:
            raise HTTPException(409,'ASSURANCE_PACK_RECOMPUTATION_DIVERGED')
        return {'reproduced':True,'pack_id':row.id,'snapshot_sha256':row.snapshot_sha256,
                'source_handoffs_recomputed':len(body.handoff_ids),'independent_field_validation':False,
                'industrial_approval_eligible':False}

    app.include_router(router)
