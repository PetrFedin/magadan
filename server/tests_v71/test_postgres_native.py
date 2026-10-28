"""NATIVE PostgreSQL acceptance suite. Never substitute SQLite or mock SQL.
Run: HYDRO_NATIVE_TESTS_REQUIRED=1 HYDRO_NATIVE_CONFIG=/tmp/hydro-native.json
     PYTHONPATH=server pytest -q server/tests_v71/test_postgres_native.py
"""
import json,os,secrets,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import pytest

CONFIG=os.environ.get('HYDRO_NATIVE_CONFIG')
if not CONFIG:
    if os.environ.get('HYDRO_NATIVE_TESTS_REQUIRED')=='1':
        raise RuntimeError('NATIVE_ACCEPTANCE_BLOCKED: dedicated PostgreSQL configuration is missing')
    pytest.skip('Native PostgreSQL is not configured; this is NOT an RLS pass',allow_module_level=True)
try:
    import psycopg
except ImportError:
    if os.environ.get('HYDRO_NATIVE_TESTS_REQUIRED')=='1':
        raise RuntimeError('NATIVE_ACCEPTANCE_BLOCKED: psycopg is not installed')
    pytest.skip('Native PostgreSQL driver missing; NOT an RLS pass',allow_module_level=True)
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import DBAPIError
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hydro_api.identity import OidcConfig,OidcService,AuthStore,IdentityMapping
from hydro_api.main import create_app
from hydro_api.storage import Organization,User,Membership
from hydro_api.audit_delivery import AuditExporter,LocalReceiptStore,ReceiptSigner,create_audit_receiver

cfg=json.loads(Path(CONFIG).read_text())
pytestmark=pytest.mark.native_pg

@pytest.fixture(scope='module')
def native(tmp_path_factory):
    admin=create_engine(cfg['admin_url'].replace('postgresql://','postgresql+psycopg://',1))
    appengine=create_engine(cfg['app_url'],pool_size=1,max_overflow=0)
    auth=AuthStore(cfg['auth_url'])
    oidc_cfg=OidcConfig(issuer='http://localhost:8999',client_id='native-acceptance',
       redirect_uri='http://testserver/v71/auth/callback',app_origin='http://testserver',
       required_acr=('urn:lab:mfa',),allow_loopback_http=True)
    identity=OidcService(oidc_cfg,auth)
    app=create_app(cfg['app_url'],jwt_secret=secrets.token_urlsafe(40),audit_secret=secrets.token_urlsafe(40),
                   oidc_service=identity,allow_test_bearer=True)
    client=TestClient(app)
    key=Ed25519PrivateKey.generate();transport=secrets.token_urlsafe(40)
    receiver=TestClient(create_audit_receiver(LocalReceiptStore(tmp_path_factory.mktemp('external-audit')),ReceiptSigner(key,database_receipt_key=bytes.fromhex(cfg['audit_receipt_key_hex'])),transport))
    exporter=AuditExporter(create_engine(cfg['export_url']),'http://testserver',transport,key.public_key(),
                          require_compliance=False,client=receiver,allow_loopback_http=True)
    def drain():
        for _ in range(10000):
            result=exporter.run_once()
            if result['status']=='idle':return
            assert result['status']=='delivered',result
        raise AssertionError('Outbox did not drain')
    return locals()

@pytest.fixture
def n(native):
    p=native;suffix=uuid4().hex[:10];org='magadan-synthetic-'+suffix;other='other-synthetic-'+suffix
    tokens={};ids={};factory=sessionmaker(p['admin'])
    with factory.begin() as db:
        db.add_all([Organization(id=org,name='Magadan synthetic acceptance only'),Organization(id=other,name='Other synthetic organization')]);db.flush()
        for name,role in [('engineer','engineer'),('reviewer','engineer'),('economist','economist'),('manager','manager'),('auditor','auditor'),('auditor2','auditor'),('viewer','viewer'),('other','engineer')]:
            uid=uuid4().hex;ids[name]=uid
            db.add(User(id=uid,email=uid+'@lab.invalid',password_hash='!OIDC_ONLY',active=True,token_version=0));db.flush()
            db.add(Membership(org_id=other if name=='other' else org,user_id=uid,role=role,active=True))
            db.add(IdentityMapping(id=uuid4().hex,issuer=p['oidc_cfg'].issuer,subject=uid,user_id=uid))
    now=int(time.time())
    for name,uid in ids.items():
        tokens[name]=p['auth'].issue({'iss':p['oidc_cfg'].issuer,'sub':uid,'auth_time':now,'acr':'urn:lab:mfa','exp':now+900},p['oidc_cfg'],now)[0]
    def h(name):return {'Authorization':'Bearer '+tokens[name]}
    base=f'/v7/orgs/{org}'
    r=p['client'].post(base+'/assets',headers=h('engineer'),json={'name':'Synthetic 20kV feeder'})
    assert r.status_code==201,r.text
    asset=r.json()['id']
    return {**p,**locals()}


def bind(c,n,actor='engineer',org=None):
    c.execute(text('SELECT hk_security.bind_session(:token,:org)'),{'token':n['tokens'][actor],'org':org or n['org']})


def test_actual_server_version_and_role(n):
    with n['appengine'].connect() as c:
        row=c.execute(text('SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
        assert tuple(row)==('hk_app',False,False)
        assert c.scalar(text('SHOW server_version_num')) >= '170000'


def test_no_context_is_default_deny(n):
    with n['appengine'].connect() as c:
        assert c.execute(text('SELECT id FROM assets')).all()==[]


def test_plain_guc_spoof_is_denied(n):
    with n['appengine'].begin() as c:
        for key,value in [('hk.org',n['org']),('hk.actor',n['ids']['engineer']),('hk.signature','forged')]:
            c.execute(text('SELECT set_config(:k,:v,true)'),{'k':key,'v':value})
        assert c.execute(text('SELECT id FROM assets')).all()==[]


def test_valid_context_cannot_be_changed_to_other_user(n):
    with n['appengine'].begin() as c:
        bind(c,n)
        c.execute(text("SELECT set_config('hk.actor',:id,true)"),{'id':n['ids']['other']})
        assert c.execute(text('SELECT id FROM assets')).all()==[]


def test_wrong_tenant_session_bind_rejected(n):
    with pytest.raises(DBAPIError):
        with n['appengine'].begin() as c:bind(c,n,org=n['other'])


def test_transaction_context_does_not_leak_to_next_borrower(n):
    with n['appengine'].begin() as c:
        bind(c,n);assert c.scalar(text('SELECT count(*) FROM assets'))==1
    with n['appengine'].begin() as c:
        assert c.scalar(text('SELECT count(*) FROM assets'))==0


def test_api_cross_tenant_ids_denied(n):
    c=n['client'];assert c.get(n['base']+'/assets',headers=n['h']('engineer')).status_code==200
    assert c.get('/v7/orgs/'+n['other']+'/assets',headers=n['h']('engineer')).status_code==404


def test_membership_revocation_affects_existing_context(n):
    with n['appengine'].begin() as c:
        bind(c,n);assert c.scalar(text('SELECT count(*) FROM assets'))==1
        with n['admin'].begin() as a:
            a.execute(text('UPDATE memberships SET active=false WHERE user_id=:u AND org_id=:o'),{'u':n['ids']['engineer'],'o':n['org']})
        assert c.scalar(text('SELECT count(*) FROM assets'))==0


def test_session_revocation_affects_existing_context(n):
    with n['appengine'].begin() as c:
        bind(c,n);assert c.scalar(text('SELECT count(*) FROM assets'))==1
        n['auth'].revoke(n['tokens']['engineer'])
        assert c.scalar(text('SELECT count(*) FROM assets'))==0


def test_cross_tenant_insert_and_truncate_are_denied(n):
    with pytest.raises(DBAPIError):
        with n['appengine'].begin() as c:
            bind(c,n)
            c.execute(text("INSERT INTO assets(id,org_id,name,classification) VALUES(:id,:o,'forged','LAB_REFERENCE')"),{'id':uuid4().hex,'o':n['other']})
    with pytest.raises(DBAPIError):
        with n['appengine'].begin() as c:bind(c,n);c.execute(text('TRUNCATE assets CASCADE'))


def test_runtime_cannot_read_private_sessions_or_change_roles(n):
    for stmt in ['SELECT * FROM hk_auth.sessions','ALTER ROLE hk_app BYPASSRLS', 'SET ROLE hk_owner']:
        with pytest.raises(DBAPIError):
            with n['appengine'].begin() as c:bind(c,n);c.execute(text(stmt))


def test_automatic_audit_and_outbox_rollback_together(n):
    uid=uuid4().hex
    with n['appengine'].connect() as c:
        tx=c.begin();bind(c,n)
        before=c.scalar(text('SELECT count(*) FROM audit_events'))
        c.execute(text("INSERT INTO assets(id,org_id,name,classification) VALUES(:id,:o,'rollback','LAB_REFERENCE')"),{'id':uid,'o':n['org']})
        assert c.scalar(text('SELECT count(*) FROM audit_events'))==before+1
        tx.rollback()
        with c.begin():
            bind(c,n)
            assert c.scalar(text('SELECT count(*) FROM audit_events'))==before
            assert c.scalar(text('SELECT count(*) FROM assets WHERE id=:id'),{'id':uid})==0


def test_append_only_and_outbox_ack_not_api_writable(n):
    for stmt in ["UPDATE audit_events SET event_type='forged'",'DELETE FROM audit_events','UPDATE audit_outbox SET delivered_at=now()']:
        with pytest.raises(DBAPIError):
            with n['appengine'].begin() as c:bind(c,n);c.execute(text(stmt))


def test_exporter_cannot_change_engineering_data(n):
    with pytest.raises(DBAPIError):
        with n['exporter'].engine.begin() as c:c.execute(text("UPDATE assets SET name='forged'"))


def test_sealed_lab_receipt_still_fails_compliance_policy(n):
    n['drain']()
    with n['appengine'].begin() as c:
        bind(c,n,'auditor')
        assert c.scalar(text('SELECT count(*) FROM audit_receipts'))>0
        assert c.scalar(text('SELECT hk_security.audit_ready(:o)'),{'o':n['org']}) is False
        assert c.scalar(text('SELECT hk_security.verify_audit(:o)'),{'o':n['org']})['valid'] is True


def prepare_run(n):
    c=n['client'];h=n['h'];b=n['base'];a=n['asset']
    case={'source_voltage_kv_ll':20,'load_p_mw':5,'load_q_mvar':2,'line_r_ohm_per_phase':.3,'line_x_ohm_per_phase':.4,'period_hours':100,'reference_name':'Synthetic native acceptance, not a Magadan field model'}
    r=c.post(b+'/evidence',headers=h('engineer'),json={'asset_id':a,'kind':'grid_input','source_ref':'SYNTHETIC-NATIVE-REFERENCE','payload':case});assert r.status_code==201,r.text
    eid=r.json()['id'];assert c.post(b+f'/evidence/{eid}/review',headers=h('auditor'),json={'accepted':True,'note':'Independent synthetic input check'}).status_code==200
    r=c.post(b+'/models',headers=h('engineer'),json={'asset_id':a,'algorithm':'balanced_two_bus_AC_PQ_lab_v1','params':{}});assert r.status_code==201,r.text
    mid=r.json()['id'];assert c.post(b+f'/models/{mid}/review',headers=h('auditor'),json={'accepted':True,'note':'Independent synthetic model check'}).status_code==200
    r=c.post(b+'/runs',headers=h('engineer'),json={'asset_id':a,'evidence_id':eid,'model_id':mid});assert r.status_code==201,r.text
    rid=r.json()['id']
    r=c.post(b+'/initiatives',headers=h('engineer'),json={'asset_id':a,'run_id':rid,'title':'Synthetic acceptance investment','effect_key':uuid4().hex});assert r.status_code==201,r.text
    return rid,r.json()['id'],eid,mid


def test_parallel_same_revision_only_one_transition(n):
    rid,iid,_,_=prepare_run(n)
    def attempt(_):
        with TestClient(n['app']) as c:
            return c.post(n['base']+f'/initiatives/{iid}/transition',headers=n['h']('engineer'),json={'to_state':'engineering_review','expected_revision':0}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(attempt,range(2)))
    assert sorted(codes)==[200,409]


def test_direct_sql_cannot_skip_evidence_workflow(n):
    _,iid,_,_=prepare_run(n)
    with pytest.raises(DBAPIError):
        with n['appengine'].begin() as c:
            bind(c,n,'manager')
            c.execute(text("UPDATE initiatives SET state='approved',revision=1 WHERE id=:id"),{'id':iid})


def test_composite_foreign_key_blocks_wrong_asset(n):
    rid,iid,eid,mid=prepare_run(n)
    r=n['client'].post(n['base']+'/assets',headers=n['h']('engineer'),json={'name':'Second unrelated synthetic feeder'})
    a2=r.json()['id']
    with pytest.raises(DBAPIError):
        with n['appengine'].begin() as c:
            bind(c,n)
            c.execute(text("""INSERT INTO calculation_runs(id,org_id,asset_id,model_id,evidence_id,input_sha256,result_sha256,result,created_by,created_at)
            VALUES(:id,:o,:a,:m,:e,:h,:h,'{}',:u,now())"""),
            {'id':uuid4().hex,'o':n['org'],'a':a2,'m':mid,'e':eid,'h':'0'*64,'u':n['ids']['engineer']})


def test_exporter_cannot_forge_a_receipt_with_its_database_credentials(n):
    with n['appengine'].begin() as c:
        bind(c,n,'auditor')
        event=c.execute(text('SELECT id,event_hash FROM audit_events ORDER BY seq LIMIT 1')).first()
    with pytest.raises(DBAPIError):
        with n['exporter'].engine.begin() as c:
            c.execute(text("""INSERT INTO audit_receipts(event_id,org_id,event_hash,envelope_sha256,receipt)
                         VALUES(:e,:o,:h,:b,CAST(:r AS jsonb))"""),
                      {'e':event.id,'o':n['org'],'h':event.event_hash,'b':'0'*64,
                       'r':json.dumps({'receipt':{'retention_mode':'COMPLIANCE'},'signature':'forged'})})


def test_seven_stage_workflow_with_explicit_lab_receipts(n):
    # Native transactional workflow only. LAB_FILE is not WORM; this policy
    # exception is scoped to this disposable test database and restored below.
    c=n['client'];h=n['h'];b=n['base']
    with n['admin'].begin() as db:
        old=db.scalar(text('SELECT require_compliance FROM hk_private.policy WHERE singleton'))
        db.execute(text('UPDATE hk_private.policy SET require_compliance=false WHERE singleton'))
    try:
        rid,iid,_,_=prepare_run(n)
        def move(actor,to,rev):
            n['drain']()
            r=c.post(b+f'/initiatives/{iid}/transition',headers=h(actor),json={'to_state':to,'expected_revision':rev})
            assert r.status_code==200,r.text
        def proof(kind,author,payload):
            r=c.post(b+'/evidence',headers=h(author),json={'asset_id':n['asset'],'kind':kind,
                  'source_ref':'SYNTHETIC-NATIVE/'+kind,'payload':payload})
            assert r.status_code==201,r.text
            eid=r.json()['id'];reviewer='auditor2' if author=='auditor' else 'auditor'
            r=c.post(b+f'/evidence/{eid}/review',headers=h(reviewer),json={'accepted':True,'note':'Synthetic test protocol evidence only'})
            assert r.status_code==200,r.text
            r=c.post(b+f'/initiatives/{iid}/evidence',headers=h(author),json={'evidence_id':eid})
            assert r.status_code==200,r.text
        move('engineer','engineering_review',0)
        proof('engineering_report','reviewer',{'run_id':rid,'finding':'Synthetic calculation checked, no field acceptance',
          'methodology_ref':'LAB-2BUS-ONLY','signed_document_ref':'NOT-AN-ENGINEER-SIGNATURE'})
        move('reviewer','financial_review',1)
        proof('financial_report','economist',{'run_id':rid,'currency':'RUB','initial_capex_rub':'28000000',
          'annual_net_benefit_rub':'9200000','discount_rate':'0.12','horizon_years':8,
          'methodology_ref':'LAB-NPV-ONLY','assumption_status':'SYNTHETIC'})
        move('economist','approval_pending',2)
        proof('approval_memo','manager',{'decision_ref':'SYNTHETIC-NATIVE-DECISION','authorized_body':'Test role only',
              'decision':'approved','approval_date':'2026-10-22'})
        move('manager','approved',3)
        # The just-created approval is not externally sealed until delivery.
        r=c.get(b+f'/initiatives/{iid}/dossier',headers=h('manager'))
        assert r.json()['assurance']['external_audit']['externally_sealed'] is False
        move('manager','in_execution',4)
        proof('execution_proof','engineer',{'work_package_ref':'SYNTHETIC-TEST-WORK',
              'completion_date':'2026-10-22','acceptance_document_ref':'SYNTHETIC-TEST-ACT'})
        move('engineer','verification_pending',5)
        proof('outcome_report','auditor',{'run_id':rid,'verification_method':'Synthetic mathematical comparison only',
          'observed_loss_mw':'0.02','observation_ref':'SYNTHETIC-TEST-NOT-FIELD',
          'period_start':'2026-01-01','period_end':'2026-10-22'})
        move('auditor2','verified',6);n['drain']()
        r=c.get(b+f'/initiatives/{iid}/dossier',headers=h('auditor2'));assert r.status_code==200,r.text
        assert r.json()['initiative']['revision']==7
        assert r.json()['assurance']['external_audit']['externally_sealed'] is True
        assert r.json()['assurance']['industrial_acceptance'] is False
    finally:
        with n['admin'].begin() as db:
            db.execute(text('UPDATE hk_private.policy SET require_compliance=:old WHERE singleton'),{'old':old})

# V7.2 extension: intentionally executed ONLY when native PostgreSQL acceptance
# is available. These assertions must never be replaced by SQLite mocks.
def test_v72_native_studies_force_rls_and_isolation(n):
    with n['appengine'].connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM public.study_runs')).scalar_one()==0
        policy=conn.execute(text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='public.study_runs'::regclass")).one()
        assert tuple(policy)==(True,True)
    request={'asset_id':n['asset'],'module':'gridloss','source_ref':'SYNTHETIC-NATIVE72',
             'scenario_group':'native-lab','scope':'SYNTHETIC_LAB_ONLY',
             'case':{'reference_name':'Synthetic native test feeder',
                     'source_voltage_kv_ll':20,'load_p_mw':5,'load_q_mvar':2,
                     'line_r_ohm_per_phase':0.3,'line_x_ohm_per_phase':0.4,'period_hours':100}}
    c=n['client']
    resp=c.post(f"/v72/orgs/{n['org']}/studies",headers=n['h']('engineer'),json=request)
    assert resp.status_code==201,resp.text
    sid=resp.json()['id']
    assert resp.json()['allowed_as_industrial_decision_evidence'] is False
    assert c.get(f"/v72/orgs/{n['org']}/studies/{sid}",headers=n['h']('viewer')).status_code==200
    assert c.get(f"/v72/orgs/{n['other']}/studies/{sid}",headers=n['h']('other')).status_code==404
    with n['appengine'].begin() as conn:
        bind(conn,n)
        assert conn.execute(text('SELECT count(*) FROM public.study_runs WHERE id=:id'),{'id':sid}).scalar_one()==1
        assert conn.execute(text('SELECT count(*) FROM public.audit_outbox WHERE org_id=:o'),{'o':n['org']}).scalar_one()>0
    with pytest.raises(DBAPIError):
        with n['appengine'].begin() as conn:
            bind(conn,n)
            conn.execute(text("UPDATE public.study_runs SET module='turbine' WHERE id=:id"),{'id':sid})


def test_v72_native_rejects_cross_tenant_study_insertion(n):
    with pytest.raises(DBAPIError):
        with n['appengine'].begin() as conn:
            bind(conn,n)
            conn.execute(text("""INSERT INTO public.study_runs
                (id,org_id,asset_id,module,source_ref,scenario_group,case_payload,
                 input_sha256,result,result_sha256,engine_sha256,created_by,created_at)
                VALUES (:id,:org,:asset,'gridloss','SYNTHETIC-X','study', '{}'::json,
                  repeat('a',64),'{}'::json,repeat('b',64),repeat('c',64),:actor,now())"""),
                {'id':uuid4().hex,'org':n['other'],'asset':n['asset'],'actor':n['ids']['engineer']})


def test_v73_dossier_native_rls_and_tenant_isolation(n):
    """Only meaningful when this file runs against genuine PostgreSQL 17."""
    with n['appengine'].connect() as conn:
        columns=conn.execute(text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='public.grid_economic_dossiers'::regclass")).one()
        assert tuple(columns)==(True,True)
        assert conn.execute(text('SELECT id FROM public.grid_economic_dossiers')).all()==[]
    c=n['client'];h=n['h'];org=n['org'];a=n['asset'];base=f'/v73/orgs/{org}'
    inp={'model_kind':'radial_ac_v73','reference_name':'SYNTHETIC_NOT_MAGADAN_FIELD',
      'source_voltage_kv_ll':20,'min_voltage_pu':0.90,
      'nodes':[{'node_id':'x','parent_id':'SOURCE','r_ohm_per_phase':.3,
                'x_ohm_per_phase':.4,'load_p_mw':5,'load_q_mvar':2,'ampacity_a':500}],
      'windows':[{'name':'reference','scale':1,'hours':100}]}
    alt=json.loads(json.dumps(inp));alt['nodes'][0]['r_ohm_per_phase']=.15
    ids=[]
    for case in (inp,alt):
        r=c.post(base+'/radial-runs',headers=h('engineer'),json={'asset_id':a,
            'source_ref':'SYNTHETIC-NATIVE-V73','scenario_group':'native_pg_lab','case':case})
        assert r.status_code==201,r.text
        ids.append(r.json()['run_id'])
    financial={'scope':'SYNTHETIC_NOT_A_TARIFF','capital_cost_rub':'1800000',
       'annual_opex_delta_rub':'150000','discount_rate':'0.12','years':8,
       'annual_repeat_count':'50','notes':'Independent synthetic native PG rehearsal only',
       'value_per_kwh_rub':{'low':'2','base':'3','high':'5'}}
    body={'asset_id':a,'baseline_run_id':ids[0],'proposed_run_id':ids[1],
      'benefit_key':'V73-native-'+uuid4().hex,'finance':financial}
    assert c.post(base+'/economic-dossiers',headers=h('engineer'),json=body).status_code==403
    approved=c.post(base+'/economic-dossiers',headers=h('economist'),json=body)
    assert approved.status_code==201,approved.text
    did=approved.json()['dossier_id']
    assert c.get('/v73/orgs/'+n['other']+'/economic-dossiers/'+did,headers=h('other')).status_code==404
    assert c.post(base+'/economic-dossiers/'+did+'/reproduce',headers=h('auditor')).status_code==200
    with n['appengine'].begin() as conn:
        bind(conn,n,'auditor')
        assert conn.scalar(text('SELECT count(*) FROM public.grid_economic_dossiers WHERE id=:i'),{'i':did})==1
        with pytest.raises(DBAPIError):
            conn.execute(text("UPDATE public.grid_economic_dossiers SET benefit_key='tampered' WHERE id=:i"),{'i':did})


def test_v73_pg_cross_tenant_insert_and_audit_role(n):
    with n['appengine'].begin() as conn:
        bind(conn,n,'engineer')
        with pytest.raises(DBAPIError):
            conn.execute(text("INSERT INTO public.grid_economic_dossiers(id,org_id,asset_id,baseline_run_id,proposed_run_id,benefit_key,finance_input,result,result_sha256,pinned_engine_sha256,created_by,created_at) VALUES (:id,:o,:a,'none','other','test-claim','{}','{}','a','b',:actor,now())"),
                {'id':uuid4().hex,'o':n['other'],'a':n['asset'],'actor':n['ids']['engineer']})


def test_v73_native_research_only_check_constraints(n):
    """Requires PostgreSQL 17: catalog check for actual enforced finance/status constraints."""
    with n['admin'].connect() as c:
        rows=c.execute(text('''SELECT conname, pg_get_constraintdef(oid)
            FROM pg_constraint WHERE conrelid='public.grid_economic_dossiers'::regclass
            AND conname IN ('grid_dossier_synthetic_finance_only','grid_dossier_research_status_only')''')).all()
        constraints={row[0]:row[1] for row in rows}
        assert set(constraints)=={'grid_dossier_synthetic_finance_only','grid_dossier_research_status_only'}
        assert 'SYNTHETIC_NOT_A_TARIFF' in constraints['grid_dossier_synthetic_finance_only']
        assert 'SYNTHETIC_RESEARCH_ONLY_NO_APPROVAL' in constraints['grid_dossier_research_status_only']
        assert 'industrial_investment_eligible' in constraints['grid_dossier_research_status_only']


# V7.4 NATIVE PostgreSQL test; test file is skipped/blocked unless a genuine
# dedicated PostgreSQL 17 test DSN and authorizer credentials are provided.
def test_v74_native_programme_rls_replay_and_cross_org_denial(n):
    for name in ('research_programmes','research_programme_studies',
                 'research_programme_links','research_programme_finance'):
        with n['appengine'].connect() as c:
            row=c.execute(text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=to_regclass(:tbl)"),
                          {'tbl':'public.'+name}).one()
            assert tuple(row)==(True,True),name
            assert c.scalar(text(f'SELECT count(*) FROM public.{name}'))==0
    c=n['client'];h=n['h'];org=n['org'];a=n['asset']
    heat={'mass_flow_kg_s':10,'supply_temp_c':90,'return_temp_c':60,
          'ambient_temp_c':-5,'cp_j_kg_k':4200,'length_m':1000,'overall_u_w_m_k':2}
    r=c.post(f'/v72/orgs/{org}/studies',headers=h('engineer'),json={
       'asset_id':a,'module':'heatnet','scenario_group':'native74',
       'source_ref':'SYNTHETIC-NATIVE-V74','case':heat,'scope':'SYNTHETIC_LAB_ONLY'})
    assert r.status_code==201,r.text
    sid=r.json()['id']
    p={'reference_code':'LAB-NATIVE74-'+uuid4().hex[:8],
      'title':'Synthetic native PostgreSQL V74 case',
      'purpose':'Native test of RLS, append-only programme and strict approval exclusion; not field data.',
      'study_ids':[sid], 'financial_dossier_ids':[],'links':[],
      'scope':'SYNTHETIC_MAGADAN_RESEARCH_ONLY'}
    row=c.post(f'/v74/orgs/{org}/programmes',headers=h('economist'),json=p)
    assert row.status_code==201,row.text
    pid=row.json()['id']
    assert c.post(f'/v74/orgs/{org}/programmes/{pid}/reproduce',headers=h('auditor')).json()['reproduced']
    assert c.get(f'/v74/orgs/{n["other"]}/programmes/{pid}',headers=h('other')).status_code==404
    with pytest.raises(DBAPIError):
        with n['appengine'].begin() as conn:
            bind(conn,n,'economist')
            conn.execute(text('UPDATE public.research_programmes SET title=:title WHERE id=:id'),
                         {'title':'FORGED','id':pid})
    with n['appengine'].begin() as conn:
        bind(conn,n,'auditor')
        assert conn.scalar(text('SELECT count(*) FROM public.research_programmes WHERE id=:id'),{'id':pid})==1
        assert conn.scalar(text('SELECT count(*) FROM public.research_programme_studies WHERE study_id=:id'),{'id':sid})==1
    with n['appengine'].connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM public.research_programmes'))==0


def test_v75_handoff_isolation_and_append_only(n):
    """PENDING NATIVE acceptance; requires migration 090 and real RLS."""
    import json
    from pathlib import Path
    sample=json.loads((Path(__file__).parents[1]/'ui'/'samples_v72.json').read_text())
    path='/v72/orgs/'+n['org']+'/studies'
    ids={}
    for module in ('hydroforecast','cascade'):
        r=n['client'].post(path,headers=n['h']('engineer'),json={
            'asset_id':n['asset'],'module':module,'case':sample[module],
            'source_ref':'SYNTHETIC-NATIVE-POSTGRES-V75',
            'scenario_group':'native_v75_lab'})
        assert r.status_code==201,r.text
        ids[module]=r.json()['id']
    data={'kind':'forecast_to_cascade','left_study_id':ids['hydroforecast'],
          'right_study_id':ids['cascade'],'forecast_bridge':{
          'step_hours':24,'scenario':'point','travel_lag_steps':0,
          'hydrological_mapping_ref':'SYNTHETIC-NATIVE-HYDRO-MAPPING-V75'}}
    base='/v75/orgs/'+n['org']+'/handoffs'
    result=n['client'].post(base,headers=n['h']('engineer'),json=data)
    assert result.status_code==201,result.text
    uid=result.json()['id']
    assert n['client'].get('/v75/orgs/'+n['other']+'/handoffs/'+uid,
        headers=n['h']('other')).status_code==404
    with n['appengine'].begin() as c:
        assert c.scalar(text('SELECT count(*) FROM research_handoffs'))==0
        bind(c,n)
        assert c.scalar(text('SELECT count(*) FROM research_handoffs WHERE id=:id'),{'id':uid})==1
        with pytest.raises(DBAPIError):
            c.execute(text('DELETE FROM research_handoffs WHERE id=:id'),{'id':uid})
    # The DELETE exception invalidates the transaction. Caller must not reuse it.


def test_v76_native_assurance_rls_and_parent_wbs(n):
    """PENDING NATIVE PostgreSQL 17 (never claimed PASS without real DB)."""
    with n['appengine'].connect() as conn:
        row=conn.execute(text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='public.assurance_packs_v76'::regclass")).one()
        assert tuple(row)==(True,True)
        assert conn.scalar(text('SELECT count(*) FROM public.assurance_packs_v76'))==0
    sample=json.loads((Path(__file__).parents[1]/'ui'/'samples_v72.json').read_text())
    c=n['client'];h=n['h'];org=n['org'];asset=n['asset'];sid={}
    for module in ('hydroforecast','cascade'):
        r=c.post(f'/v72/orgs/{org}/studies',headers=h('engineer'),json={
            'asset_id':asset,'module':module,'case':sample[module],
            'source_ref':'SYNTHETIC-NATIVE-POSTGRES-V76',
            'scenario_group':'native_v76_lab'})
        assert r.status_code==201,r.text
        sid[module]=r.json()['id']
    cap={'currency':'RUB','tax_basis':'EXCL_VAT_SYNTHETIC','title':'Synthetic PostgreSQL native financial rehearsal',
         'annual_caps_rub':{'2027':'500000'},'contingency_percent':'0',
         'lines':[{'code':'survey','title':'Synthetic engineering survey','category':'survey','year':2027,
                   'quantity':'1','unit':'package','unit_price_rub':'400000',
                   'price_source_ref':'SYNTHETIC-NATIVE-PG-V76'}]}
    prog={'reference_code':'LAB-PG76-'+uuid4().hex[:10],
          'title':'Synthetic PostgreSQL native regional research programme',
          'purpose':'Mandatory native RLS tenant isolation, WBS and append-only assurance tests with synthetic data only.',
          'study_ids':list(sid.values()),'capital':cap,'scope':'SYNTHETIC_MAGADAN_RESEARCH_ONLY'}
    r=c.post(f'/v74/orgs/{org}/programmes',headers=h('economist'),json=prog)
    assert r.status_code==201,r.text;pid=r.json()['id']
    bridge={'kind':'forecast_to_cascade','left_study_id':sid['hydroforecast'],
            'right_study_id':sid['cascade'],'programme_id':pid,
            'forecast_bridge':{'scenario':'point','step_hours':24,'travel_lag_steps':0,
                               'hydrological_mapping_ref':'SYNTHETIC-NATIVE-PG-76-HYDRO'}}
    r=c.post(f'/v75/orgs/{org}/handoffs',headers=h('engineer'),json=bridge)
    assert r.status_code==201,r.text;hid=r.json()['id']
    body={'reference_code':'LAB-PG76-PACK-'+uuid4().hex[:10],
          'programme_id':pid,'handoff_ids':[hid],
          'routing_handoff_id':hid,
          'routing':{'time_constant_hours':12,'initial_routed_outflow_cms':30,
                     'mapping_ref':'SYNTHETIC-NATIVE-PG-V76-ROUTE'},
          'finance':{'scope':'SYNTHETIC_INCREMENTAL_CASHFLOWS_ONLY',
                     'benefit_key':'PG76-SYN-'+uuid4().hex,
                     'source_assumption_ref':'SYNTHETIC-NATIVE-VALUE-V76',
                     'discounted_from_year':2027,'discount_rate':'0.12',
                     'benefit_scenarios':{'low':'0.5','base':'1','high':'1.5'},
                     'annual_gross_value_rub':{'2028':'100000'},
                     'annual_incremental_opex_rub':{'2028':'15000'},
                     'rationale':'Synthetic financial screening, not a real Magadan cost estimate, value or approved construction project.'},
          'scope':'SYNTHETIC_DECISION_EVIDENCE_NOT_APPROVAL'}
    url=f'/v76/orgs/{org}/assurance-packs'
    assert c.post(url,headers=h('engineer'),json=body).status_code==403
    r=c.post(url,headers=h('economist'),json=body)
    assert r.status_code==201,r.text;pack=r.json()['id']
    assert c.get(f'/v76/orgs/{n["other"]}/assurance-packs/{pack}',headers=h('other')).status_code==404
    assert c.post(f'{url}/{pack}/reproduce',headers=h('auditor')).status_code==200
    with n['appengine'].begin() as conn:
        bind(conn,n,'auditor')
        assert conn.scalar(text('SELECT count(*) FROM public.assurance_packs_v76 WHERE id=:id'),{'id':pack})==1
    with pytest.raises(DBAPIError):
        with n['appengine'].begin() as conn:
            bind(conn,n,'economist')
            conn.execute(text("DELETE FROM public.assurance_packs_v76 WHERE id=:id"),{'id':pack})
    with n['appengine'].connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM public.assurance_packs_v76'))==0


def test_v77_native_grid_reference(n):
    """PENDING NATIVE PG17: RLS and immutability with lab-only payloads."""
    c=n['client'];h=n['h'];org=n['org'];a=n['asset']
    with n['appengine'].connect() as conn:
        flags=conn.execute(text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='public.grid_reference_comparisons_v77'::regclass")).one()
        assert tuple(flags)==(True,True)
        assert conn.scalar(text('SELECT count(*) FROM public.grid_reference_comparisons_v77'))==0
    grid={'model_kind':'radial_ac_v73','reference_name':'SYNTHETIC-MAGADAN-PG17-V77',
      'source_voltage_kv_ll':20,'min_voltage_pu':0.9,
      'nodes':[{'node_id':'node1','parent_id':'SOURCE','r_ohm_per_phase':0.25,
         'x_ohm_per_phase':0.3,'load_p_mw':2,'load_q_mvar':0.6,'ampacity_a':1000}],
      'windows':[{'name':'normal','scale':1,'hours':24}]}
    r=c.post(f'/v73/orgs/{org}/radial-runs',headers=h('engineer'),json={
      'asset_id':a,'scenario_group':'synthetic_v77_pg','source_ref':'SYNTHETIC-NATIVE-REFERENCE-V77','case':grid})
    assert r.status_code==201,r.text
    sid=r.json()['run_id']
    req=c.get(f'/v77/orgs/{org}/grid-reference/request/{sid}',headers=h('viewer'))
    assert req.status_code==200,req.text
    window=r.json()['result']['result']['windows'][0]
    sub={'scope':'SYNTHETIC_UNATTESTED_REFERENCE_ONLY','claimed_tool':'other',
       'claimed_tool_version':'TEST-NOT-EXTERNAL','calculation_method':'Synthetic result from own solver; NOT independent',
       'source_reference':'SYNTHETIC-NATIVE-NOT-EXTERNAL-REFERENCE',
       'case_sha256':req.json()['case_sha256'],
       'windows':[{'window':'normal','line_loss_p_mw':window['line_loss_p_mw'],
          'nodes':[{'node_id':q['node_id'],'voltage_pu':q['voltage_pu'],
                    'current_a':q['current_a'],'line_loss_p_mw':q['line_loss_p_mw']} for q in window['nodes']]}]}
    url=f'/v77/orgs/{org}/grid-reference/comparisons'
    assert c.post(url,headers=h('viewer'),json={'study_id':sid,'submission':sub}).status_code==403
    r=c.post(url,headers=h('engineer'),json={'study_id':sid,'submission':sub})
    assert r.status_code==201,r.text
    rid=r.json()['comparison_id']
    assert r.json()['status']=='LAB_NUMERICAL_MATCH_UNATTESTED'
    assert c.post(f'{url}/{rid}/reproduce',headers=h('auditor')).status_code==200
    with n['appengine'].begin() as conn:
        bind(conn,n,'auditor')
        assert conn.scalar(text('SELECT count(*) FROM public.grid_reference_comparisons_v77 WHERE id=:id'),{'id':rid})==1
    with pytest.raises(DBAPIError):
        with n['appengine'].begin() as conn:
            bind(conn,n,'engineer')
            conn.execute(text('DELETE FROM public.grid_reference_comparisons_v77 WHERE id=:id'),{'id':rid})
    with n['appengine'].connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM public.grid_reference_comparisons_v77'))==0


def test_v79_native_new_table_default_deny_and_runtime_non_owner(n):
    # Executed ONLY under the mandatory PostgreSQL 17 acceptance configuration.
    with n['appengine'].connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM public.benefit_reservations_v79')).scalar_one()==0
        assert conn.execute(text('SELECT count(*) FROM public.measurement_screens_v79')).scalar_one()==0
        count=conn.execute(text("""SELECT count(*) FROM pg_class c JOIN pg_namespace z ON z.oid=c.relnamespace
                 WHERE z.nspname='public' AND c.relname IN
                 ('benefit_reservations_v79','measurement_screens_v79')
                 AND c.relrowsecurity AND c.relforcerowsecurity""")).scalar_one()
        assert count==2
    with pytest.raises(DBAPIError):
        with n['appengine'].begin() as conn:
            bind(conn,n)
            conn.execute(text("""INSERT INTO public.benefit_reservations_v79
              (id,org_id,asset_id,family,start_year,end_year,source_kind,source_id,
               source_sha256,source_fingerprint,measurement_plan_ref,
               measurement_boundary_description,comparison_normalization,
               reservation_sha256,created_by,created_at)
              VALUES (:id,:org,:asset,'MAINTENANCE_COST',2030,2034,
                 'MAINTENANCE_HANDOFF_V75','forged',:hash,:hash,
                 'SYNTHETIC-PLAN-NATIVE-TEST-2026',
                 'Synthetic single asset measurement boundary without field meters.',
                 'Baseline and post comparison must normalize exact same operating conditions and signed scope.',
                 :hash,:actor,now())"""),{
                    'id':uuid4().hex,'org':n['org'],'asset':n['asset'],
                    'hash':'0'*64,'actor':n['ids']['engineer']})


def test_v79_native_concurrent_overlap_and_replay(n):
    # Creating the two candidate documents must be performed via real HTTP API.
    from tests_v75.test_handoff_api import maintenance_payload
    from hydro_api.storage import StudyRun
    from hydro_api.main import sha
    sample_path=Path(__file__).resolve().parents[1]/'ui'/'samples_v72.json'
    synthetic=json.loads(sample_path.read_text())['turbine']
    c=n['client'];base='/v72/orgs/'+n['org']+'/studies'
    ids=[]
    for k in ('first','second'):
        result=c.post(base,headers=n['h']('engineer'),json={
           'asset_id':n['asset'],'module':'turbine','scenario_group':'v79-native-synthetic',
           'source_ref':'SYNTHETIC-V79-NATIVE-'+k,
           'case':synthetic})
        assert result.status_code==201,result.text
        ids.append(result.json()['id'])
    handoffs=[]
    for index,sid in enumerate(ids):
        params=maintenance_payload({'turbine':sid})
        params['maintenance_bridge']['planning_reference']+='-'+str(index)
        response=c.post('/v75/orgs/'+n['org']+'/handoffs',headers=n['h']('engineer'),json=params)
        assert response.status_code==201,response.text
        handoffs.append(response.json()['id'])
    claimurl='/v79/orgs/'+n['org']+'/benefit-reservations'
    def reservation(hid):
        return {'asset_id':n['asset'],'source_kind':'MAINTENANCE_HANDOFF_V75',
         'source_id':hid,'family':'MAINTENANCE_COST','start_year':2030,'end_year':2035,
         'measurement_plan_ref':'SYNTHETIC-V79-NATIVE-MV-PLAN-2026',
         'measurement_boundary_description':'Synthetic single asset boundary; no physical meter readings or operational actions.',
         'comparison_normalization':'Counterfactual comparison with the same baseline date, asset, workload and economic method; no field authority.'}
    first=c.post(claimurl,headers=n['h']('economist'),json=reservation(handoffs[0]))
    assert first.status_code==201,first.text
    other=c.post(claimurl,headers=n['h']('economist'),json=reservation(handoffs[1]))
    assert other.status_code==409,other.text
    audit=c.post(claimurl+'/'+first.json()['id']+'/reproduce',headers=n['h']('auditor'))
    assert audit.status_code==200,audit.text
    assert audit.json()['actual_savings_confirmed'] is False
