import pytest
from sqlalchemy import text,select
from hydro_api.engineering import GridCase,balanced_two_bus,CalculationError
from hydro_api.main import create_app,sha,audit_report
from hydro_api.storage import Organization,AuditEvent


def test_secrets_required():
    with pytest.raises(RuntimeError):create_app('sqlite:///:memory:',jwt_secret='short',audit_secret='short')


def test_auth_login_logout_and_revoke(env):
    c=env['client'];h=env['h']
    assert c.get('/v7/orgs/magadan-lab/assets').status_code==401
    assert c.post('/v7/auth/login',json={'email':'lead@lab.invalid','password':'wrong'}).status_code==401
    assert c.post('/v7/auth/login',json={'email':'nosuch@lab.invalid','password':'wrong'}).status_code==401
    assert c.get('/v7/me',headers=h('lead')).status_code==200
    assert c.get('/v7/orgs/separate-org/assets',headers=h('lead')).status_code==404
    assert c.post('/v7/orgs/magadan-lab/assets',headers=h('viewer'),json={'name':'test new asset'}).status_code==403
    assert c.post('/v7/auth/logout',headers=h('lead')).status_code==200
    assert c.get('/v7/me',headers=h('lead')).status_code==401
    assert c.get('/health').json()['production_ready'] is False


def test_tenant_lists_scoped_and_role_from_database(env):
    c=env['client'];h=env['h']
    assert [x['id'] for x in c.get('/v7/orgs/magadan-lab/assets',headers=h('viewer')).json()]==['feeder-a']
    assert [x['id'] for x in c.get('/v7/orgs/separate-org/assets',headers=h('other')).json()]==['feeder-b']
    # JWT cannot choose an elevated role, role always reloaded from Membership.
    assert c.post('/v7/orgs/magadan-lab/models',headers=h('viewer'),json={'asset_id':'feeder-a','algorithm':'balanced_two_bus_AC_PQ_lab_v1','params':{}}).status_code==403


def test_grid_physical_equations_and_independent_root():
    c=GridCase(source_voltage_kv_ll=20,load_p_mw=5,load_q_mvar=2,
               line_r_ohm_per_phase=.3,line_x_ohm_per_phase=.4,
               period_hours=100,reference_name='synthetic reference')
    result=balanced_two_bus(c)
    assert abs(result['line_loss_p_mw']-0.022004055)<1e-8
    assert abs(result['sending_p_mw']-(5+result['line_loss_p_mw']))<1e-8
    assert result['active_power_balance_residual_mw']<1e-8
    assert result['independent_closed_form_voltage_difference_v']<.01
    assert 'SYNTHETIC' in result['data_classification']
    with pytest.raises(CalculationError):balanced_two_bus(GridCase(
        source_voltage_kv_ll=10,load_p_mw=180,load_q_mvar=100,
        line_r_ohm_per_phase=5,line_x_ohm_per_phase=5,
        period_hours=100,reference_name='Impossible high load'))


def test_model_evidence_need_independent_review(env):
    c=env['client'];h=env['h'];base='/v7/orgs/magadan-lab'
    e=c.post(base+'/evidence',headers=h('lead'),json={'asset_id':'feeder-a','kind':'grid_input',
        'source_ref':'synthetic-dataset-v1','payload':{
          'source_voltage_kv_ll':20,'load_p_mw':5,'load_q_mvar':2,
          'line_r_ohm_per_phase':.3,'line_x_ohm_per_phase':.4,
          'period_hours':100,'reference_name':'synthetic test'}})
    assert e.status_code==201,e.text; eid=e.json()['id']
    m=c.post(base+'/models',headers=h('lead'),json={'asset_id':'feeder-a','algorithm':'balanced_two_bus_AC_PQ_lab_v1','params':{}})
    assert m.status_code==201;mid=m.json()['id']
    assert c.post(base+'/runs',headers=h('lead'),json={'asset_id':'feeder-a','evidence_id':eid,'model_id':mid}).status_code==409
    assert c.post(base+'/evidence/'+eid+'/review',headers=h('lead'),json={'accepted':True,'note':'Try self approve'}).status_code==403
    assert c.post(base+'/models/'+mid+'/review',headers=h('lead'),json={'accepted':True,'note':'Try self approve'}).status_code==403
    assert c.post(base+'/evidence/'+eid+'/review',headers=h('audit'),json={'accepted':False,'note':'Reject synthetically'}).status_code==200
    assert c.post(base+'/evidence/'+eid+'/review',headers=h('audit'),json={'accepted':True,'note':'Reconsider same'}).status_code==409
    assert c.post(base+'/models/'+mid+'/review',headers=h('audit'),json={'accepted':True,'note':'Test model passed'}).status_code==200
    assert c.post(base+'/runs',headers=h('lead'),json={'asset_id':'feeder-a','evidence_id':eid,'model_id':mid}).status_code==409
    # Cross-company ID must not allow a run even if IDs are known
    assert c.post('/v7/orgs/separate-org/runs',headers=h('other'),json={'asset_id':'feeder-b','evidence_id':eid,'model_id':mid}).status_code==404


def test_model_run_reproducible_and_tenant_isolated(prepared):
    env=prepared['env'];c=env['client'];h=env['h'];base=prepared['base']
    r=c.get(base+'/runs/'+prepared['run'],headers=h('viewer'))
    assert r.status_code==200
    assert sha(r.json()['result'])==r.json()['result_sha256']
    assert c.get('/v7/orgs/separate-org/runs/'+prepared['run'],headers=h('other')).status_code==404
    assert c.get('/v7/orgs/magadan-lab/audit/verify',headers=h('viewer')).status_code==403
    assert c.get(base+'/audit/verify',headers=h('audit')).json()['valid'] is True


def test_workflow_evidence_review_sod_dossier_and_stale(prepared):
    env=prepared['env'];c=env['client'];h=env['h'];base=prepared['base']
    iid=c.post(base+'/initiatives',headers=h('lead'),json={'asset_id':'feeder-a','run_id':prepared['run'],
              'title':'Study modernization of synthetic feeder','effect_key':'test-feeder-losses-2026'}).json()['id']
    def change(actor,to,rev):
        return c.post(base+f'/initiatives/{iid}/transition',headers=h(actor),json={'to_state':to,'expected_revision':rev})
    assert change('lead','approved',0).status_code==409
    assert change('viewer','engineering_review',0).status_code==403
    assert change('lead','engineering_review',0).status_code==200
    assert change('lead','financial_review',1).status_code==403 # separation of duties
    assert change('reviewer','financial_review',1).status_code==409 # lacking report
    def proof(kind,actor,reviewer='audit'):
        cases={
          'engineering_report':{'run_id':prepared['run'],'finding':'Engineering notes: synthetic load-flow is coherent','methodology_ref':'LAB-REF-2BUS-2026','signed_document_ref':'SYNTHETIC-ENG-REPORT-001'},
          'financial_report':{'run_id':prepared['run'],'currency':'RUB','initial_capex_rub':'28000000','annual_net_benefit_rub':'9200000','discount_rate':'0.12','horizon_years':8,'methodology_ref':'LAB-NPV-2026','assumption_status':'SYNTHETIC'},
          'approval_memo':{'decision_ref':'SYNTHETIC-BOARD-MINUTES-001','authorized_body':'Synthetic authority only','decision':'approved','approval_date':'2026-10-20'},
          'execution_proof':{'work_package_ref':'SYNTHETIC-WORK-PACKAGE-01','completion_date':'2026-10-20','acceptance_document_ref':'SYNTHETIC-ACCEPTANCE-001'},
          'outcome_report':{'run_id':prepared['run'],'verification_method':'Synthetic two-bus post-calculation check, not physical measurement','observed_loss_mw':'0.02','observation_ref':'SYNTHETIC-OBSERVATIONS-001','period_start':'2026-01-01','period_end':'2026-10-20'}
        }
        payload=cases[kind]
        r=c.post(base+'/evidence',headers=h(actor),json={'asset_id':'feeder-a','kind':kind,
            'source_ref':'SYNTHETIC/'+kind+'/doc-v1','payload':payload});assert r.status_code==201,r.text
        eid=r.json()['id']
        assert c.post(base+f'/evidence/{eid}/review',headers=h(reviewer),json={'accepted':True,'note':'Reviewed as synthetic example'}).status_code==200
        ar=c.post(base+f'/initiatives/{iid}/evidence',headers=h(actor),json={'evidence_id':eid});assert ar.status_code==200,ar.text
        return eid
    proof('engineering_report','reviewer');assert change('reviewer','financial_review',1).status_code==200
    assert change('finance','approval_pending',2).status_code==409
    proof('financial_report','finance');assert change('finance','approval_pending',2).status_code==200
    assert change('manager','approved',3).status_code==409
    proof('approval_memo','manager');assert change('manager','approved',3).status_code==200
    assert change('manager','approved',3).status_code==409
    assert change('manager','in_execution',4).status_code==200
    assert change('reviewer','verification_pending',5).status_code==409
    proof('execution_proof','reviewer');assert change('reviewer','verification_pending',5).status_code==200
    proof('outcome_report','audit2','audit');assert change('audit2','verified',6).status_code==403
    assert change('audit','verified',6).status_code==200
    dossier=c.get(base+f'/initiatives/{iid}/dossier',headers=h('viewer'))
    assert dossier.status_code==200
    assert dossier.json()['initiative']['state']=='verified'
    assert len(dossier.json()['transitions'])==7
    assert len(dossier.json()['evidence'])==5
    assert c.get('/v7/orgs/separate-org/initiatives/'+iid+'/dossier',headers=h('other')).status_code==404
    assert c.get(base+'/audit/verify',headers=h('audit')).json()['valid'] is True
    assert c.get(base+'/audit/export',headers=h('audit')).json()['events']


def test_effect_key_is_per_tenant(prepared):
    env=prepared['env'];c=env['client'];h=env['h'];base=prepared['base']
    j={'asset_id':'feeder-a','run_id':prepared['run'],'title':'First feeder option proof', 'effect_key':'benefit-2026-A'}
    a=c.post(base+'/initiatives',headers=h('lead'),json=j)
    assert a.status_code==201
    assert c.post(base+'/initiatives',headers=h('lead'),json=j).status_code==409
    assert c.post('/v7/orgs/separate-org/initiatives',headers=h('other'),json={**j,'asset_id':'feeder-b'}).status_code==404


def test_append_only_triggers_and_detect_changed_head(prepared):
    env=prepared['env'];c=env['client'];h=env['h'];base=prepared['base']
    with env['db']() as db:
        e=db.execute(select(AuditEvent).where(AuditEvent.org_id=='magadan-lab')).scalars().first()
        assert e is not None
        with pytest.raises(Exception):
            with db.begin_nested():db.execute(text('DELETE FROM audit_events WHERE id=:id'),{'id':e.id})
        db.rollback()
        org=db.get(Organization,'magadan-lab')
        org.audit_tip='0'*64
        db.commit()
    r=c.get(base+'/audit/verify',headers=h('audit'))
    assert r.status_code==200 and r.json()['valid'] is False
    assert r.json()['reason']=='CHAIN_TIP_MISMATCH'


def test_correct_model_immutable(prepared):
    env=prepared['env']
    with env['db']() as db:
        with pytest.raises(Exception):
            with db.begin_nested():db.execute(text("UPDATE model_versions SET algorithm='HACK' WHERE id=:id"),{'id':prepared['model']})
        db.rollback()


def test_openapi_endpoint_and_no_field_control(env):
    c=env['client'];d=c.get('/openapi.json').json()
    paths=d['paths']
    assert '/v7/orgs/{org_id}/runs' in paths
    assert not any(any(s in p.lower() for s in ('scada','dispatch','switchgear','breaker','turbine/control')) for p in paths)
    assert c.get('/v7/meta/limitations').json()['field_data']=='not connected'

def test_api_lists_and_strict_provenance(prepared):
    env=prepared['env'];c=env['client'];h=env['h'];base=prepared['base']
    assert len(c.get(base+'/models',headers=h('viewer')).json())==1
    assert len(c.get(base+'/evidence',headers=h('viewer')).json())==1
    assert len(c.get(base+'/runs',headers=h('viewer')).json())==1
    for typ in ['engineering_report','financial_report','approval_memo','execution_proof','outcome_report']:
        r=c.post(base+'/evidence',headers=h({'engineering_report':'reviewer','financial_report':'finance','approval_memo':'manager','execution_proof':'reviewer','outcome_report':'audit'}[typ]),
                 json={'asset_id':'feeder-a','kind':typ,'source_ref':'DOCUMENT-NOT-VALID','payload':{}})
        assert r.status_code==422, (typ,r.text)
    # Asset within same org cannot be accidentally associated with another organization's run.
    assert c.post('/v7/orgs/separate-org/evidence',headers=h('other'),json={'asset_id':'feeder-a','kind':'grid_input','source_ref':'lab-source','payload':prepared['case']}).status_code==404


def test_token_tamper_and_role_revocation(env):
    import jwt as pyjwt
    from sqlalchemy import select
    from hydro_api.storage import Membership
    c=env['client'];h=env['h']
    malformed={'Authorization':'Bearer '+env['tokens']['lead']+'ZZ'}
    assert c.get('/v7/me',headers=malformed).status_code==401
    with env['db']() as db:
        role=db.scalar(select(Membership).where(Membership.user_id==env['users']['lead'],Membership.org_id=='magadan-lab'))
        role.active=False;db.commit()
    # A valid, not-yet-expired JWT cannot override a revoked organization membership.
    assert c.get('/v7/orgs/magadan-lab/assets',headers=h('lead')).status_code==404


def test_foreign_run_document_cannot_attach(prepared):
    env=prepared['env'];c=env['client'];h=env['h'];base=prepared['base']
    iid=c.post(base+'/initiatives',headers=h('lead'),json={'asset_id':'feeder-a','run_id':prepared['run'],
        'title':'Synthetic protected initiative','effect_key':'SYNTHETIC-PROOF-MISMATCH'}).json()['id']
    other='different-calculation-uuid-2026'
    document={'run_id':other,'finding':'This synthetic finding is linked to another calculation',
              'methodology_ref':'SYNTHETIC-METHODOLOGY-2026','signed_document_ref':'SYNTHETIC-DOC-MISMATCH'}
    e=c.post(base+'/evidence',headers=h('reviewer'),json={'asset_id':'feeder-a','kind':'engineering_report',
        'source_ref':'SYNTHETIC-MISMATCH-DOC','payload':document});assert e.status_code==201,e.text
    eid=e.json()['id']
    assert c.post(base+f'/evidence/{eid}/review',headers=h('audit'),json={'accepted':True,'note':'Synthetic schema valid, but wrong initiative'}).status_code==200
    r=c.post(base+f'/initiatives/{iid}/evidence',headers=h('reviewer'),json={'evidence_id':eid})
    assert r.status_code==409 and 'different calculation' in r.json()['detail']


def test_financial_npv_is_server_calculated(prepared):
    env=prepared['env'];c=env['client'];h=env['h'];base=prepared['base']
    iid=c.post(base+'/initiatives',headers=h('lead'),json={'asset_id':'feeder-a','run_id':prepared['run'],
        'title':'Test financial normalization','effect_key':'FIN-SYNTHETIC-2026'}).json()['id']
    payload={'run_id':prepared['run'],'currency':'RUB','initial_capex_rub':'28000000',
             'annual_net_benefit_rub':'9200000','discount_rate':'0.12',
             'horizon_years':8,'methodology_ref':'SYNTHETIC-NPV-V1','assumption_status':'SYNTHETIC'}
    e=c.post(base+'/evidence',headers=h('finance'),json={'asset_id':'feeder-a','kind':'financial_report',
           'source_ref':'SYNTHETIC-FIN-CALC-2026','payload':payload});assert e.status_code==201,e.text
    evid=e.json()['id']
    assert c.post(base+f'/evidence/{evid}/review',headers=h('audit'),json={'accepted':True,'note':'Approved schema, no real cost backing'}).status_code==200
    assert c.post(base+f'/initiatives/{iid}/evidence',headers=h('finance'),json={'evidence_id':evid}).status_code==200
    dossier=c.get(base+f'/initiatives/{iid}/dossier',headers=h('viewer')).json()
    value=float(dossier['evidence'][0]['financial_npv_rub'])
    assert 17_000_000 < value < 18_000_000


def test_security_headers_on_lab_html(env):
    r=env['client'].get('/lab')
    assert r.status_code==200
    assert 'script-src' in r.headers['content-security-policy']
    assert 'SYNTHETIC LAB' in r.text
    assert r.headers['x-frame-options']=='DENY'

@pytest.mark.parametrize('p,q,r,x',[ (1,0,0.1,0.1),(3,1,0.2,0.5),(7,3,0.5,0.7),
                                      (9,2,0.3,1.0),(3,0.2,1,0.1),(5,4,0.1,0.6),
                                      (12,4,0.15,0.25),(0.5,0,0.01,0),
                                      (6,6,0.35,0.2),(2,0.5,1,1),
                                      (4,2,0.5,0.5),(7,0.1,0.7,0.3)])
def test_physical_solver_parameter_grid(p,q,r,x):
    data=GridCase(reference_name='synthetic parameter sweep',source_voltage_kv_ll=35,
                  load_p_mw=p,load_q_mvar=q,line_r_ohm_per_phase=r,
                  line_x_ohm_per_phase=x,period_hours=8760)
    result=balanced_two_bus(data)
    assert result['line_loss_p_mw']>0
    assert result['receiving_voltage_pu']>0
    assert result['solver_residual_pu']<1e-8
    assert abs(result['sending_p_mw']-p-result['line_loss_p_mw'])<1e-7
    assert result['active_power_balance_residual_mw']<=1e-7


def test_detection_after_privileged_db_tampering(prepared):
    """DB administrator can disable SQLite triggers, but without HMAC secret changes are detectable."""
    env=prepared['env'];engine=env['app'].state.engine
    with engine.begin() as conn:
        conn.exec_driver_sql('DROP TRIGGER lock_audit_events_update')
        conn.exec_driver_sql("UPDATE audit_events SET payload='{}' WHERE org_id='magadan-lab' AND seq=1")
    r=env['client'].get(prepared['base']+'/audit/verify',headers=env['h']('audit'))
    assert r.status_code==200 and r.json()['valid'] is False
    assert r.json()['reason']=='CHAIN_INTEGRITY_FAILURE'


def test_invalid_jwt_expiration_and_audience(env):
    from datetime import datetime,timezone,timedelta
    import jwt
    c=env['client'];u=env['users']['lead']
    secret='v7-jwt-secret-for-unit-tests-never-production-123456'
    def token(aud,ttl):
        dt=datetime.now(timezone.utc)
        return jwt.encode({'sub':u,'ver':0,'jti':'synthetic-jti','iss':'hydrokontur-lab','aud':aud,
                           'iat':dt-timedelta(minutes=5),'exp':dt+timedelta(seconds=ttl)},secret,algorithm='HS256')
    for t in [token('invalid-audience',300), token('hydrokontur-api',-1)]:
        assert c.get('/v7/me',headers={'Authorization':'Bearer '+t}).status_code==401


def test_real_field_data_unsupported_and_postgres_gated(env):
    from fastapi.testclient import TestClient
    body=env['client'].get('/v7/meta/limitations').json()
    assert body['field_data']=='not connected'
    with pytest.raises(RuntimeError,match='PostgreSQL requires the OIDC session boundary'):
        create_app(database_url='postgresql+psycopg://postgres@127.0.0.1/hydro',
                   jwt_secret='valid-jwt-secret-at-least-32-characters-123',
                   audit_secret='valid-audit-secret-at-least-32-characters-456')

def test_local_seed_runs_from_empty_database_and_refuses_second_seed(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    from sqlalchemy import func
    from hydro_api.storage import setup_engine,User,Organization,Asset,Membership
    root=Path(__file__).resolve().parents[1]
    db_path=tmp_path/'new-lab-seed.db'
    environment={**os.environ,'HYDRO_ALLOW_DEMO_SEED':'YES','HYDRO_DATABASE_URL':'sqlite:///'+str(db_path),
                 'PYTHONPATH':str(root)}
    p=subprocess.run([sys.executable,'-m','hydro_api.seed_lab'],cwd=root,env=environment,capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    eng,Factory=setup_engine('sqlite:///'+str(db_path))
    with Factory() as db:
        assert db.scalar(select(func.count()).select_from(Organization))==1
        assert db.scalar(select(func.count()).select_from(Asset))==1
        assert db.scalar(select(func.count()).select_from(User))==7
        assert db.scalar(select(func.count()).select_from(Membership))==7
    eng.dispose()
    rerun=subprocess.run([sys.executable,'-m','hydro_api.seed_lab'],cwd=root,env=environment,capture_output=True,text=True)
    assert rerun.returncode==2 and 'not empty' in rerun.stderr
