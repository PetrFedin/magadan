"""HydroKontur V7 laboratory API. No SCADA writes or field access."""
import os,json,hashlib,hmac,time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Literal
from decimal import Decimal
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict, ValidationError
from argon2 import PasswordHasher, exceptions as argonerr
import jwt
from jwt.exceptions import PyJWTError
from .storage import (setup_engine,new_id,Organization,User,Membership,Asset,Evidence,EvidenceReview,
                      ModelVersion,ModelReview,CalculationRun,Initiative,InitiativeEvidence,Transition,AuditEvent,StudyRun)
from .engineering import GridCase, balanced_two_bus, CalculationError
from .evidence_schemas import validate_payload, FinancialReport, financial_npv

ROLE_SET={'engineer','economist','manager','auditor','admin','viewer'}
BASIC_VIEW=ROLE_SET
WRITE_ASSETS={'admin','engineer'}
HASHER=PasswordHasher()
DUMMY_HASH=HASHER.hash('This-is-not-a-login-account-random-dummy-value-2026')
BEARER=HTTPBearer(auto_error=False)


def canonical(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def sha(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def execution_provenance():
    import importlib.metadata
    import platform
    from . import engineering
    digest=hashlib.sha256()
    for source in (Path(engineering.__file__),Path(__file__)):
        digest.update(source.name.encode());digest.update(source.read_bytes())
    return {'implementation_sha256':digest.hexdigest(),'python':platform.python_version(),
            'scipy':importlib.metadata.version('scipy'),'numpy':importlib.metadata.version('numpy'),
            'algorithm':'balanced_two_bus_AC_PQ_lab_v1'}

def checked_result(case):
    result=balanced_two_bus(case)
    result['execution_provenance']=execution_provenance()
    return result

def deny(message='Not found'):raise HTTPException(status_code=404,detail=message)
def forbidden(message='Permission denied'):raise HTTPException(status_code=403,detail=message)

def record_audit(db,org_id,actor_id,event_type,object_type,object_id,payload,secret):
    if db.bind.dialect.name == 'postgresql':
        from .pg_security import append_pg_audit
        return append_pg_audit(db,org_id,event_type,object_type,object_id,payload)
    # PostgreSQL: SELECT ... FOR UPDATE serializes per-organization chain.
    org=db.execute(select(Organization).where(Organization.id==org_id).with_for_update()).scalar_one()
    seq=org.audit_seq+1; previous=org.audit_tip; ms=int(time.time()*1000)
    data={'org_id':org_id,'seq':seq,'actor_id':actor_id,'event_type':event_type,
          'object_type':object_type,'object_id':object_id,'payload':payload,
          'previous_hash':previous,'timestamp_ms':ms}
    digest=hmac.new(secret.encode(),canonical(data).encode(),'sha256').hexdigest()
    row=AuditEvent(org_id=org_id,seq=seq,actor_id=actor_id,event_type=event_type,
                   object_type=object_type,object_id=object_id,payload=payload,
                   previous_hash=previous,event_hash=digest,timestamp_ms=ms)
    db.add(row);org.audit_seq=seq;org.audit_tip=digest;db.flush()
    return digest

def audit_report(db,org_id,secret):
    if db.bind.dialect.name == 'postgresql':
        return db.scalar(text('SELECT hk_security.verify_audit(:org)'), {'org':org_id})
    org=db.get(Organization,org_id)
    events=db.scalars(select(AuditEvent).where(AuditEvent.org_id==org_id).order_by(AuditEvent.seq)).all()
    prev='GENESIS'
    for ix,e in enumerate(events,1):
        data={'org_id':e.org_id,'seq':e.seq,'actor_id':e.actor_id,'event_type':e.event_type,
              'object_type':e.object_type,'object_id':e.object_id,'payload':e.payload,
              'previous_hash':e.previous_hash,'timestamp_ms':e.timestamp_ms}
        expected=hmac.new(secret.encode(),canonical(data).encode(),'sha256').hexdigest()
        if e.seq!=ix or e.previous_hash!=prev or not hmac.compare_digest(expected,e.event_hash):
            return {'valid':False,'checked':ix-1,'reason':'CHAIN_INTEGRITY_FAILURE','at_sequence':ix}
        prev=e.event_hash
    if org.audit_seq!=len(events) or org.audit_tip!=prev:
        return {'valid':False,'checked':len(events),'reason':'CHAIN_TIP_MISMATCH'}
    return {'valid':True,'checked':len(events),'tip':prev,'property':'HMAC tamper-evident; NOT externally anchored WORM'}

def review_is_accepted(db,review_cls,idfield,key,org_id):
    q=select(review_cls).where(review_cls.org_id==org_id,getattr(review_cls,idfield)==key).order_by(review_cls.created_at.desc(),review_cls.id.desc())
    row=db.scalars(q).first()
    return bool(row and row.accepted)

def require_evidence(db,org_id,eid,asset_id=None):
    e=db.scalar(select(Evidence).where(Evidence.id==eid,Evidence.org_id==org_id))
    if not e or (asset_id and e.asset_id!=asset_id):deny()
    return e

def require_run(db,org_id,rid,asset_id=None):
    r=db.scalar(select(CalculationRun).where(CalculationRun.id==rid,CalculationRun.org_id==org_id))
    if not r or (asset_id and r.asset_id!=asset_id):deny()
    return r

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Login(Strict):
    email:str=Field(min_length=3,max_length=256)
    password:str=Field(min_length=1,max_length=1024)
class AssetNew(Strict):
    name:str=Field(min_length=3,max_length=160)
    classification:Literal['LAB_REFERENCE']='LAB_REFERENCE'
class EvidenceNew(Strict):
    asset_id:str
    kind:Literal['grid_input','engineering_report','financial_report','approval_memo','execution_proof','outcome_report']
    source_ref:str=Field(min_length=5,max_length=256)
    payload:dict
class ReviewNew(Strict):
    accepted:bool
    note:str=Field(min_length=8,max_length=1000)
class ModelNew(Strict):
    asset_id:str
    algorithm:Literal['balanced_two_bus_AC_PQ_lab_v1']
    params:dict=Field(default_factory=dict)
class RunNew(Strict):
    asset_id:str
    evidence_id:str
    model_id:str
class InitiativeNew(Strict):
    asset_id:str
    run_id:str
    title:str=Field(min_length=6,max_length=160)
    effect_key:str=Field(min_length=4,max_length=80)
class AttachEvidence(Strict):evidence_id:str
class TransitionNew(Strict):
    to_state:Literal['engineering_review','financial_review','approval_pending','approved','in_execution','verification_pending','verified']
    expected_revision:int=Field(ge=0)

WORKFLOW={
    'draft':('engineering_review','engineer',None),
    'engineering_review':('financial_review','engineer','engineering_report'),
    'financial_review':('approval_pending','economist','financial_report'),
    'approval_pending':('approved','manager','approval_memo'),
    'approved':('in_execution','manager',None),
    'in_execution':('verification_pending','engineer','execution_proof'),
    'verification_pending':('verified','auditor','outcome_report')}


def create_app(database_url=None,jwt_secret=None,audit_secret=None, *, oidc_service=None, allow_test_bearer=False):
    db_url=database_url or os.environ.get('HYDRO_DATABASE_URL','sqlite:///./hydro_v7_lab.db')
    jwt_secret=jwt_secret or os.environ.get('HYDRO_JWT_SECRET')
    audit_secret=audit_secret or os.environ.get('HYDRO_AUDIT_SECRET')
    is_pg = db_url.startswith('postgresql+psycopg://')
    if not is_pg and not db_url.startswith('sqlite'):
        raise RuntimeError('Unsupported database backend')
    if is_pg and oidc_service is None:
        raise RuntimeError('PostgreSQL requires the OIDC session boundary; local password login is disabled')
    if allow_test_bearer and (oidc_service is None or not oidc_service.config.allow_loopback_http):
        raise RuntimeError('Opaque bearer test access requires explicit loopback identity mode')
    if not jwt_secret or len(jwt_secret)<32 or not audit_secret or len(audit_secret)<32 or jwt_secret==audit_secret:
        raise RuntimeError('Separate JWT and AUDIT secrets >=32 characters are mandatory; never hardcode credentials')
    if is_pg:
        from .pg_security import setup_postgres
        engine,SessionLocal=setup_postgres(db_url)
    else:
        engine,SessionLocal=setup_engine(db_url)
    app=FastAPI(title='HydroKontur Magadan V8.3.2 / controlled engineering lab',version='0.8.3.2-lab',
                description='No industrial connections, not a production authorization or SCADA system')
    app.state.engine=engine;app.state.SessionLocal=SessionLocal
    app.mount('/lab-assets',StaticFiles(directory=str(Path(__file__).parent.parent/'ui')),name='lab-assets')
    @app.get('/lab',include_in_schema=False)
    def laboratory_ui():return FileResponse(str(Path(__file__).parent.parent/'ui'/'index.html'))
    @app.middleware('http')
    async def security_headers(request,call_next):
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
        return response

    if oidc_service is not None:
        from .identity import register_oidc_routes
        register_oidc_routes(app, oidc_service)

    from sqlalchemy.exc import DBAPIError
    @app.exception_handler(DBAPIError)
    async def database_boundary_error(request, exc):
        code = getattr(exc.orig, 'sqlstate', None) or getattr(exc.orig, 'pgcode', None)
        if code in ('28000','28P01'):
            status, detail = 401, 'Session rejected'
        elif code == '42501':
            status, detail = 404, 'Object or operation not accessible'
        elif code in ('23505','23503','23514','40001','40P01'):
            status, detail = 409, 'Version, evidence, dependency or audit gate rejected the operation'
        else:
            status, detail = 503, 'Database operation unavailable'
        return JSONResponse({'detail':detail}, status_code=status)

    def get_db(request: Request):
        with SessionLocal() as db:
            if is_pg:
                token = request.cookies.get(oidc_service.config.cookie('session'), '')
                if not token and allow_test_bearer:
                    token = request.headers.get('Authorization','').removeprefix('Bearer ')
                db.info.update(opaque_token=token, org_id=request.path_params.get('org_id',''))
            yield db

    def current_user(request: Request, cred:HTTPAuthorizationCredentials|None=Depends(BEARER),db:Session=Depends(get_db)):
        if oidc_service is not None:
            from .identity import IdentityError, token_hash
            c = oidc_service.config
            raw = request.cookies.get(c.cookie('session'), '')
            is_cookie = bool(raw)
            if not raw and allow_test_bearer and cred:
                raw = cred.credentials
            try:
                identity = oidc_service.store.resolve(raw, int(time.time()))
            except IdentityError:
                raise HTTPException(401,'Invalid server session') from None
            if is_cookie and request.method not in ('GET','HEAD','OPTIONS'):
                csrf = request.headers.get('X-CSRF-Token', '')
                if request.headers.get('Origin') != c.app_origin or not csrf or not hmac.compare_digest(token_hash(csrf), identity.csrf_hash):
                    raise HTTPException(403,'CSRF verification failed')
            request.state.identity_session = identity
            request.state.raw_session = raw
            u = db.get(User, identity.user_id)
            if not u or not u.active:
                raise HTTPException(401,'Invalid server session')
            return u
        if not cred or cred.scheme.lower()!='bearer':raise HTTPException(401,'Bearer token required')
        try:
            claims=jwt.decode(cred.credentials,jwt_secret,algorithms=['HS256'],issuer='hydrokontur-lab',
                              audience='hydrokontur-api',options={'require':['exp','iat','sub','iss','aud','ver','jti']})
        except (PyJWTError,ValueError):raise HTTPException(401,'Invalid authentication')
        u=db.get(User,claims['sub'])
        if not u or not u.active or u.token_version!=claims['ver']:raise HTTPException(401,'Invalid authentication')
        return u

    def access(org_id:str,roles:set,user:User,db:Session):
        m=db.scalar(select(Membership).where(Membership.org_id==org_id,Membership.user_id==user.id,
                                             Membership.active==True))
        if not m:deny() # avoid exposing even existence of tenant
        if m.role not in roles:forbidden()
        return m
    def asset(db,org_id,asset_id):
        a=db.scalar(select(Asset).where(Asset.org_id==org_id,Asset.id==asset_id))
        if not a:deny()
        return a
    def initiative(db,org_id,iid):
        i=db.scalar(select(Initiative).where(Initiative.id==iid,Initiative.org_id==org_id))
        if not i:deny()
        return i

    # V7.2 exploratory multi-domain studies. These cannot enter the V7 approval chain.
    from .studies_api import install_study_routes
    install_study_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical)

    # V7.3 synthetic feeder research and evidence-linked economic dossiers.
    from .grid_dossiers_api import install_radial_economics_routes
    install_radial_economics_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical)

    # V7.4 immutable research programme: all six study lanes, WBS and evidence links.
    from .programme_api_v74 import install_programme_routes
    install_programme_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical)

    # V7.5 physical handoffs: historical forecast->cascade and turbine->maintenance.
    # This is NOT an industrial engineering or investment approval bridge.
    from .handoff_api_v75 import install_handoff_routes
    install_handoff_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical)

    from .assurance_api_v76 import install_assurance_routes
    install_assurance_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical)
    from .reference_api_v77 import install_reference_routes
    install_reference_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical)
    from .sensitivity_api_v77 import install_sensitivity_routes
    install_sensitivity_routes(app,get_db,current_user,access,sha)

    # V7.8: physically sourced annual avoided-loss economics; lab-only.
    from .grid_cashflow_api_v78 import install_grid_cashflow_routes
    install_grid_cashflow_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical)

    # V7.9 conservative, cross-module lab benefit ownership.
    # Existing legacy financial dossiers are NOT automatically reconciled.
    from .benefit_api_v79 import install_benefit_routes
    install_benefit_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical)

    from .measurement_api_v79 import install_mv_routes
    install_mv_routes(app,get_db,current_user,access,asset,record_audit,audit_secret,sha,canonical)

    # V8.0 canonical laboratory measurement boundaries; no corporate recognition.
    from .boundary_api_v8 import install_boundary_routes
    install_boundary_routes(app,get_db,current_user,access,asset,record_audit,audit_secret)

    from .forecast_api_v82 import install_forecast_v82_routes
    install_forecast_v82_routes(app,get_db,current_user,access,asset,sha,canonical)

    # V8.3 1-day forecast -> two-reservoir water balance and stage/efficiency.
    # No operational/financial actions; both lab assets require tenant RBAC.
    from .cascade_api_v83 import install_cascade_v83_routes
    install_cascade_v83_routes(app,get_db,current_user,access,asset,sha,canonical)

    # V8.8 three synthetic regional energy scenarios, conditional investment NPV.
    # Stateless research only; no real connectivity or financial recognition.
    from .regional_energy_api_v88 import install_regional_energy_v88_routes
    install_regional_energy_v88_routes(app,get_db,current_user,access,sha,canonical)

    @app.get('/health')
    def health():return {'service':'hydrokontur-v75-lab','status':'ok','production_ready':False}

    @app.post('/v7/auth/login')
    def login(body:Login,db:Session=Depends(get_db)):
        if oidc_service is not None:raise HTTPException(404,'Password login disabled; use corporate sign-in')
        u=db.scalar(select(User).where(User.email==body.email.strip().lower()))
        try: password_ok=HASHER.verify(u.password_hash if u and u.active else DUMMY_HASH,body.password)
        except (argonerr.VerificationError,argonerr.InvalidHashError):password_ok=False
        valid=bool(u and u.active and password_ok)
        if not valid:
            # Production requires distributed brute-force controls at IdP or gateway.
            raise HTTPException(401,'Invalid credentials')
        current=datetime.now(timezone.utc)
        payload={'sub':u.id,'ver':u.token_version,'jti':new_id(),'iss':'hydrokontur-lab',
                 'aud':'hydrokontur-api','iat':current,'exp':current+timedelta(minutes=15)}
        return {'access_token':jwt.encode(payload,jwt_secret,algorithm='HS256'),'token_type':'bearer','expires_in':900}

    @app.post('/v7/auth/logout')
    def logout(request: Request,u:User=Depends(current_user),db:Session=Depends(get_db)):
        if oidc_service is not None:
            c=oidc_service.config
            oidc_service.store.revoke(request.state.raw_session)
            response=JSONResponse({'revoked':True,'scope':'local_session_only','idp_global_logout':False})
            for suffix in ('session','csrf'):
                response.delete_cookie(c.cookie(suffix),path='/',secure=c.secure,samesite='lax',httponly=suffix=='session')
            return response
        u.token_version+=1;db.commit()  # revoke all user's existing tokens
        return {'revoked':True,'scope':'all_active_user_tokens'}

    @app.get('/v7/me')
    def me(u:User=Depends(current_user),db:Session=Depends(get_db)):
        memberships=db.scalars(select(Membership).where(Membership.user_id==u.id,Membership.active==True)).all()
        return {'user_id':u.id,'email':u.email,'organizations':[{'org_id':m.org_id,'role':m.role} for m in memberships]}

    @app.get('/v7/orgs/{org_id}/assets')
    def assets(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,BASIC_VIEW,u,db)
        return [{'id':a.id,'name':a.name,'classification':a.classification} for a in db.scalars(select(Asset).where(Asset.org_id==org_id).order_by(Asset.name))]

    @app.post('/v7/orgs/{org_id}/assets',status_code=201)
    def add_asset(org_id:str,body:AssetNew,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,WRITE_ASSETS,u,db)
        a=Asset(org_id=org_id,name=body.name,classification=body.classification)
        db.add(a);db.flush()
        record_audit(db,org_id,u.id,'asset.created','asset',a.id,{'name':a.name,'classification':a.classification},audit_secret)
        db.commit()
        return {'id':a.id,'org_id':org_id,'name':a.name}

    @app.post('/v7/orgs/{org_id}/evidence',status_code=201)
    def add_evidence(org_id:str,body:EvidenceNew,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor'},u,db)
        a=asset(db,org_id,body.asset_id)
        if len(canonical(body.payload).encode())>524288:raise HTTPException(413,'Evidence payload exceeds 512KB')
        if body.kind=='grid_input':
            access(org_id,{'engineer'},u,db)
        # Enforce distinct schemas for supporting documents; arbitrary JSON is not a valid proof.
        try:
            payload=validate_payload(body.kind,body.payload)
        except ValidationError as err:
            raise HTTPException(status_code=422,detail={'code':'EVIDENCE_SCHEMA_INVALID','fields':['.'.join(map(str,v['loc'])) for v in err.errors()]})
        if body.kind in ('engineering_report','execution_proof'):
            access(org_id,{'engineer'},u,db)
        if body.kind=='financial_report':access(org_id,{'economist'},u,db)
        if body.kind=='approval_memo':access(org_id,{'manager'},u,db)
        if body.kind=='outcome_report':access(org_id,{'auditor'},u,db)
        fingerprint=sha({'kind':body.kind,'source_ref':body.source_ref,'asset_id':a.id,'payload':payload})
        e=Evidence(org_id=org_id,asset_id=a.id,kind=body.kind,source_ref=body.source_ref,
                   payload=payload,content_sha256=fingerprint,created_by=u.id)
        db.add(e);db.flush()
        record_audit(db,org_id,u.id,'evidence.submitted','evidence',e.id,{'sha256':fingerprint,'kind':e.kind,'asset_id':a.id},audit_secret)
        db.commit()
        return {'id':e.id,'status':'pending_independent_review','sha256':fingerprint,'kind':e.kind}

    @app.post('/v7/orgs/{org_id}/evidence/{evidence_id}/review')
    def review_evidence(org_id:str,evidence_id:str,body:ReviewNew,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'auditor'},u,db)
        e=require_evidence(db,org_id,evidence_id)
        if e.created_by==u.id:forbidden('Cannot review own evidence')
        if db.scalar(select(EvidenceReview).where(EvidenceReview.org_id==org_id,EvidenceReview.evidence_id==e.id)):
            raise HTTPException(409,'Evidence already reviewed; create corrected evidence instead')
        review=EvidenceReview(org_id=org_id,evidence_id=e.id,actor_id=u.id,accepted=body.accepted,note=body.note)
        db.add(review);db.flush()
        record_audit(db,org_id,u.id,'evidence.reviewed','evidence',e.id,{'accepted':body.accepted,'review_id':review.id},audit_secret)
        db.commit()
        return {'evidence_id':e.id,'accepted':body.accepted}

    @app.get('/v7/orgs/{org_id}/evidence')
    def list_evidence(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,BASIC_VIEW,u,db)
        return [{'id':e.id,'asset_id':e.asset_id,'kind':e.kind,
                 'sha256':e.content_sha256,'source_ref':e.source_ref,
                 'status':'accepted' if review_is_accepted(db,EvidenceReview,'evidence_id',e.id,org_id) else (
                      'rejected' if db.scalar(select(EvidenceReview).where(EvidenceReview.org_id==org_id,EvidenceReview.evidence_id==e.id)) else 'pending')}
                for e in db.scalars(select(Evidence).where(Evidence.org_id==org_id).order_by(Evidence.created_at.desc()))]

    @app.get('/v7/orgs/{org_id}/models')
    def list_models(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,BASIC_VIEW,u,db)
        return [{'id':m.id,'algorithm':m.algorithm,'asset_id':m.asset_id,'sha256':m.content_sha256,
                 'status':'accepted' if review_is_accepted(db,ModelReview,'model_id',m.id,org_id) else (
                     'rejected' if db.scalar(select(ModelReview).where(ModelReview.org_id==org_id,ModelReview.model_id==m.id)) else 'pending')}
                for m in db.scalars(select(ModelVersion).where(ModelVersion.org_id==org_id).order_by(ModelVersion.created_at.desc()))]

    @app.get('/v7/orgs/{org_id}/runs')
    def list_runs(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,BASIC_VIEW,u,db)
        return [{'id':r.id,'asset_id':r.asset_id,'model_id':r.model_id,'reference_name':r.result.get('reference_name','run')}
                for r in db.scalars(select(CalculationRun).where(CalculationRun.org_id==org_id).order_by(CalculationRun.created_at.desc()))]

    @app.post('/v7/orgs/{org_id}/models',status_code=201)
    def add_model(org_id:str,body:ModelNew,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer'},u,db);asset(db,org_id,body.asset_id)
        if body.params not in ({},{'solver':'scipy-root + analytic-high-voltage'}):
            raise HTTPException(422,'Unsupported lab model specification')
        pinned_params={**body.params,'execution_provenance':execution_provenance()}
        digest=sha({'org_id':org_id,'asset_id':body.asset_id,'algorithm':body.algorithm,'params':pinned_params})
        m=ModelVersion(org_id=org_id,asset_id=body.asset_id,algorithm=body.algorithm,params=pinned_params,
                       content_sha256=digest,created_by=u.id)
        db.add(m);db.flush()
        record_audit(db,org_id,u.id,'model.version.created','model_version',m.id,{'sha256':digest,'algorithm':m.algorithm},audit_secret)
        db.commit()
        return {'id':m.id,'sha256':digest,'review':'pending'}

    @app.post('/v7/orgs/{org_id}/models/{model_id}/review')
    def review_model(org_id:str,model_id:str,body:ReviewNew,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'auditor'},u,db)
        m=db.scalar(select(ModelVersion).where(ModelVersion.id==model_id,ModelVersion.org_id==org_id))
        if not m:deny()
        if u.id==m.created_by:forbidden('Cannot approve own model')
        if db.scalar(select(ModelReview).where(ModelReview.org_id==org_id,ModelReview.model_id==model_id)):
            raise HTTPException(409,'Model already reviewed; create new version instead')
        r=ModelReview(org_id=org_id,model_id=model_id,actor_id=u.id,accepted=body.accepted,note=body.note)
        db.add(r);db.flush()
        record_audit(db,org_id,u.id,'model.version.reviewed','model_version',model_id,{'accepted':body.accepted,'review_id':r.id},audit_secret)
        db.commit();return {'model_id':model_id,'accepted':body.accepted}

    @app.post('/v7/orgs/{org_id}/runs',status_code=201)
    def run(org_id:str,body:RunNew,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer'},u,db);asset(db,org_id,body.asset_id)
        e=require_evidence(db,org_id,body.evidence_id,body.asset_id)
        m=db.scalar(select(ModelVersion).where(ModelVersion.id==body.model_id,ModelVersion.org_id==org_id,ModelVersion.asset_id==body.asset_id))
        if not m:deny()
        if e.kind!='grid_input':raise HTTPException(422,'Expected reviewed grid_input')
        if not review_is_accepted(db,EvidenceReview,'evidence_id',e.id,org_id):raise HTTPException(409,'Evidence requires independent acceptance')
        if not review_is_accepted(db,ModelReview,'model_id',m.id,org_id):raise HTTPException(409,'Model requires independent acceptance')
        if m.algorithm!='balanced_two_bus_AC_PQ_lab_v1':raise HTTPException(422,'Unknown solver')
        expected_e=sha({'kind':e.kind,'source_ref':e.source_ref,'asset_id':e.asset_id,'payload':e.payload})
        expected_m=sha({'org_id':org_id,'asset_id':m.asset_id,'algorithm':m.algorithm,'params':m.params})
        if expected_e!=e.content_sha256 or expected_m!=m.content_sha256:
            raise HTTPException(409,'SOURCE_OR_MODEL_INTEGRITY_FAILURE')
        if m.params.get('execution_provenance')!=execution_provenance():
            raise HTTPException(409,'REVIEW_NEW_MODEL_FOR_CHANGED_RUNTIME')
        # Rebuild and validate trusted submitted payload, never accept client-supplied computed results.
        case=GridCase.model_validate(e.payload)
        try:result=checked_result(case)
        except CalculationError as err:raise HTTPException(422,str(err))
        fingerprint=sha({'model':m.content_sha256,'evidence':e.content_sha256,'payload':e.payload})
        run=CalculationRun(org_id=org_id,asset_id=body.asset_id,model_id=m.id,evidence_id=e.id,
                           input_sha256=fingerprint,result_sha256=sha(result),result=result,created_by=u.id)
        db.add(run);db.flush()
        record_audit(db,org_id,u.id,'calculation.completed','calculation_run',run.id,
                     {'model_sha256':m.content_sha256,'evidence_sha256':e.content_sha256,'result_sha256':run.result_sha256},audit_secret)
        db.commit()
        return {'id':run.id,'model_id':m.id,'evidence_id':e.id,'input_sha256':fingerprint,
                'result_sha256':run.result_sha256,'result':result}

    @app.get('/v7/orgs/{org_id}/runs/{run_id}')
    def get_run(org_id:str,run_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,BASIC_VIEW,u,db)
        r=require_run(db,org_id,run_id)
        return {'id':r.id,'asset_id':r.asset_id,'result':r.result,'input_sha256':r.input_sha256,
                'result_sha256':r.result_sha256,'model_id':r.model_id,'evidence_id':r.evidence_id}

    @app.post('/v71/orgs/{org_id}/runs/{run_id}/reproduce')
    def reproduce(org_id:str,run_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','auditor'},u,db)
        r=require_run(db,org_id,run_id)
        e=require_evidence(db,org_id,r.evidence_id,r.asset_id)
        m=db.scalar(select(ModelVersion).where(ModelVersion.id==r.model_id,ModelVersion.org_id==org_id,ModelVersion.asset_id==r.asset_id))
        if not m:deny()
        expected_e=sha({'kind':e.kind,'source_ref':e.source_ref,'asset_id':e.asset_id,'payload':e.payload})
        expected_m=sha({'org_id':org_id,'asset_id':m.asset_id,'algorithm':m.algorithm,'params':m.params})
        expected_input=sha({'model':m.content_sha256,'evidence':e.content_sha256,'payload':e.payload})
        if expected_e!=e.content_sha256 or expected_m!=m.content_sha256 or expected_input!=r.input_sha256 or sha(r.result)!=r.result_sha256:
            raise HTTPException(409,'REPRODUCTION_INTEGRITY_FAILURE')
        if r.result.get('execution_provenance')!=execution_provenance():
            raise HTTPException(409,'PINNED_RUNTIME_NOT_AVAILABLE')
        computed=checked_result(GridCase.model_validate(e.payload))
        if sha(computed)!=r.result_sha256:
            raise HTTPException(409,'REPRODUCTION_DIFFERENCE_REQUIRES_REVIEW')
        from .engineering_reference import reference_sweep
        reference=reference_sweep(GridCase.model_validate(e.payload))
        delta=abs(reference['line_loss_p_mw']-computed['line_loss_p_mw'])
        if delta>1e-8:raise HTTPException(409,'MATHEMATICAL_REFERENCE_MISMATCH')
        report={'run_id':r.id,'exact_reproduction':True,'result_sha256':r.result_sha256,
                'independent_implementation_difference_mw':delta,
                'independent_specialist_verified':False,'magadan_field_validation':False}
        record_audit(db,org_id,u.id,'calculation.reproduced','calculation_run',r.id,report,audit_secret)
        db.commit()
        return report

    @app.post('/v7/orgs/{org_id}/initiatives',status_code=201)
    def add_initiative(org_id:str,body:InitiativeNew,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer'},u,db);asset(db,org_id,body.asset_id)
        require_run(db,org_id,body.run_id,body.asset_id)
        exists=db.scalar(select(Initiative).where(Initiative.org_id==org_id,Initiative.effect_key==body.effect_key))
        if exists:raise HTTPException(409,'Duplicate benefit key in the same organization')
        i=Initiative(org_id=org_id,asset_id=body.asset_id,run_id=body.run_id,
                     title=body.title,effect_key=body.effect_key,created_by=u.id)
        db.add(i);db.flush()
        record_audit(db,org_id,u.id,'initiative.created','initiative',i.id,
                     {'run_id':i.run_id,'effect_key':i.effect_key},audit_secret)
        db.commit()
        return {'id':i.id,'state':i.state,'revision':i.revision,'run_id':i.run_id}

    @app.get('/v7/orgs/{org_id}/initiatives')
    def list_initiatives(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,BASIC_VIEW,u,db)
        return [{'id':i.id,'title':i.title,'asset_id':i.asset_id,'state':i.state,'revision':i.revision,'effect_key':i.effect_key} for i in db.scalars(select(Initiative).where(Initiative.org_id==org_id).order_by(Initiative.title))]

    @app.post('/v7/orgs/{org_id}/initiatives/{iid}/evidence')
    def attach(org_id:str,iid:str,body:AttachEvidence,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'engineer','economist','manager','auditor'},u,db)
        i=initiative(db,org_id,iid)
        if i.state=='verified':raise HTTPException(409,'Verified initiative is closed')
        e=require_evidence(db,org_id,body.evidence_id,i.asset_id)
        if not review_is_accepted(db,EvidenceReview,'evidence_id',e.id,org_id):raise HTTPException(409,'Evidence not accepted')
        existing=db.scalar(select(InitiativeEvidence).where(InitiativeEvidence.org_id==org_id,
                               InitiativeEvidence.initiative_id==iid,InitiativeEvidence.evidence_id==e.id))
        if existing:raise HTTPException(409,'Already attached')
        if e.kind in ('engineering_report','financial_report','outcome_report') and e.payload['run_id']!=i.run_id:
            raise HTTPException(409,'Document references a different calculation version')
        match_roles={'engineering_report':{'engineer'},'financial_report':{'economist'},'approval_memo':{'manager'},
                     'execution_proof':{'engineer'},'outcome_report':{'auditor'},'grid_input':{'engineer'}}
        access(org_id,match_roles[e.kind],u,db)
        ref=InitiativeEvidence(org_id=org_id,initiative_id=i.id,evidence_id=e.id)
        db.add(ref);db.flush()
        record_audit(db,org_id,u.id,'evidence.linked','initiative',i.id,{'evidence_id':e.id,'kind':e.kind},audit_secret)
        db.commit();return {'initiative_id':i.id,'evidence_id':e.id,'linked':True}

    @app.post('/v7/orgs/{org_id}/initiatives/{iid}/transition')
    def transition(org_id:str,iid:str,body:TransitionNew,request: Request,u:User=Depends(current_user),db:Session=Depends(get_db)):
        if oidc_service is not None and body.to_state in ('approved','in_execution','verified'):
            identity=request.state.identity_session
            if time.time()-identity.auth_time>oidc_service.config.max_auth_age:
                raise HTTPException(401,'FRESH_CORPORATE_AUTHENTICATION_REQUIRED')
        if is_pg and body.to_state in ('approved','in_execution','verified'):
            from .pg_security import pg_audit_status
            if not pg_audit_status(db,org_id)['externally_sealed']:
                raise HTTPException(409,'AUDIT_SEAL_REQUIRED: prior events have no verified external receipt')
        # Lock initiative row in PG; SQLite serializes writes, but cross-worker race needs PG.
        i=db.scalar(select(Initiative).where(Initiative.org_id==org_id,Initiative.id==iid).with_for_update())
        if not i:deny()
        bound_run=require_run(db,org_id,i.run_id,i.asset_id)
        if sha(bound_run.result)!=bound_run.result_sha256:
            raise HTTPException(409,'CALCULATION_INTEGRITY_FAILURE')
        expected=WORKFLOW.get(i.state)
        if not expected or body.to_state!=expected[0]:raise HTTPException(409,'Invalid state transition')
        access(org_id,{expected[1]},u,db)
        if body.expected_revision!=i.revision:raise HTTPException(409,'STALE_REVISION')
        # No project owner may self-approve technically or financially.
        if i.state=='engineering_review' and u.id==i.created_by:forbidden('Independent engineering review required')
        if i.state=='financial_review' and u.id in {i.created_by,i.engineer_approver}:forbidden('Independent financial review required')
        if i.state=='approval_pending' and u.id in {i.created_by,i.engineer_approver,i.finance_approver}:forbidden('Separate manager approval required')
        if i.state=='verification_pending':
            if u.id==i.created_by:forbidden('Independent outcome verification required')
            reports=db.scalars(select(Evidence).join(InitiativeEvidence,InitiativeEvidence.evidence_id==Evidence.id)
                .where(InitiativeEvidence.org_id==org_id,InitiativeEvidence.initiative_id==i.id,
                       Evidence.org_id==org_id,Evidence.kind=='outcome_report')).all()
            if any(e.created_by==u.id for e in reports):forbidden('Outcome author cannot verify their own conclusion')
        kind=expected[2]
        if kind:
            links=db.scalars(select(Evidence).join(InitiativeEvidence,InitiativeEvidence.evidence_id==Evidence.id)
                .where(InitiativeEvidence.org_id==org_id,InitiativeEvidence.initiative_id==i.id,Evidence.org_id==org_id,Evidence.kind==kind)).all()
            if not any(review_is_accepted(db,EvidenceReview,'evidence_id',e.id,org_id) for e in links):
                raise HTTPException(409,f'Missing independently accepted evidence: {kind}')
        old=i.state;i.state=body.to_state;i.revision+=1
        if old=='engineering_review':i.engineer_approver=u.id
        if old=='financial_review':i.finance_approver=u.id
        db.flush()
        ah=record_audit(db,org_id,u.id,'initiative.transition','initiative',i.id,
                        {'from':old,'to':i.state,'revision':i.revision,'required_evidence':kind},audit_secret)
        tr=Transition(org_id=org_id,initiative_id=i.id,from_state=old,to_state=i.state,
                      revision=i.revision,actor_id=u.id,audit_hash=ah)
        db.add(tr);db.commit()
        return {'id':i.id,'state':i.state,'revision':i.revision,'audit_hash':ah}

    @app.get('/v7/orgs/{org_id}/initiatives/{iid}/dossier')
    def dossier(org_id:str,iid:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,BASIC_VIEW,u,db);i=initiative(db,org_id,iid)
        r=require_run(db,org_id,i.run_id,i.asset_id)
        links=db.scalars(select(Evidence).join(InitiativeEvidence,InitiativeEvidence.evidence_id==Evidence.id)
                .where(InitiativeEvidence.org_id==org_id,InitiativeEvidence.initiative_id==iid,Evidence.org_id==org_id)).all()
        ts=db.scalars(select(Transition).where(Transition.org_id==org_id,Transition.initiative_id==iid).order_by(Transition.revision)).all()
        if sha(r.result)!=r.result_sha256:
            raise HTTPException(409,'CALCULATION_INTEGRITY_FAILURE')
        sealing={'externally_sealed':False,'corporate_worm_verified':False,'status':'LAB_NOT_EXTERNALLY_SEALED'}
        if is_pg:
            from .pg_security import pg_audit_status
            sealing=pg_audit_status(db,org_id)
        return {'assurance':{'external_audit':sealing,'business_state_is_not_a_seal':True,
                'industrial_acceptance':False,'independent_engineer_signoff':False,'magadan_field_data_authorized':False},
                'initiative':{'id':i.id,'title':i.title,'state':i.state,'revision':i.revision,'effect_key':i.effect_key},
                'calculation':{'id':r.id,'input_sha256':r.input_sha256,'result_sha256':r.result_sha256,'result':r.result},
                'evidence':[{'id':e.id,'kind':e.kind,'sha256':e.content_sha256,
                             'financial_npv_rub':financial_npv(FinancialReport.model_validate(e.payload)) if e.kind=='financial_report' else None,
                             'accepted':review_is_accepted(db,EvidenceReview,'evidence_id',e.id,org_id)} for e in links],
                'transitions':[{'from':t.from_state,'to':t.to_state,'actor_id':t.actor_id,'revision':t.revision,'audit_hash':t.audit_hash} for t in ts]}

    @app.get('/v7/orgs/{org_id}/audit/verify')
    def verify_audit(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'auditor','admin'},u,db)
        return audit_report(db,org_id,audit_secret)

    @app.get('/v7/orgs/{org_id}/audit/export')
    def export_audit(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'auditor','admin'},u,db)
        verification=audit_report(db,org_id,audit_secret)
        es=db.scalars(select(AuditEvent).where(AuditEvent.org_id==org_id).order_by(AuditEvent.seq)).all()
        return {'verification':verification,'events':[
            {'seq':x.seq,'actor_id':x.actor_id,'event_type':x.event_type,'object_type':x.object_type,
             'object_id':x.object_id,'payload':x.payload,'previous_hash':x.previous_hash,
             'event_hash':x.event_hash,'timestamp_ms':x.timestamp_ms} for x in es]}

    @app.get('/v71/orgs/{org_id}/audit/delivery')
    def audit_delivery(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'auditor','admin','manager'},u,db)
        if not is_pg:
            return {'status':'NOT_CONNECTED','external_worm_verified':False}
        from .pg_security import pg_audit_status
        return pg_audit_status(db,org_id)

    @app.get('/v71/meta/readiness')
    def readiness():
        return {'version':'0.7.2','database_backend':'postgresql' if is_pg else 'sqlite_lab',
            'oidc_adapter_configured':oidc_service is not None,'corporate_idp_verified':False,
            'native_postgres_acceptance':'REQUIRES_NATIVE_TEST_REPORT',
            'external_worm_acceptance':'REQUIRES_DEPLOYED_RETENTION_TEST',
            'magadan_field_data_authorized':False,'independent_engineer_signoff':False,
            'production_ready':False,'six_domain_studies':'SYNTHETIC_ONLY',
            'study_workflow_promotion':'PROHIBITED'}

    @app.get('/v7/meta/limitations')
    def limitations():
        return {'scope':'laboratory-only','field_data':'not connected',
                'validation':'AC solver compared with internal independent analytic derivation; no external engineer sign-off',
                'authentication':'OIDC adapter with server sessions; corporate provider unverified' if oidc_service else 'Legacy local laboratory JWT',
                'database':'PostgreSQL RLS runtime configured; native acceptance report required' if is_pg else 'SQLite laboratory; NOT RLS proof',
                'audit':'Transactional PG outbox + external signed receipts; production WORM not certified' if is_pg else 'SQLite HMAC laboratory',
                'industrial_commands':'none'}
    return app
