import os
import pytest
from fastapi.testclient import TestClient
from hydro_api.main import create_app,HASHER
from argon2 import PasswordHasher
from hydro_api import main as _api_main
# Only the synthetic-test fixture: production Argon2 parameters are unchanged.
_api_main.HASHER = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
_api_main.DUMMY_HASH = _api_main.HASHER.hash("This-is-not-a-login-account-random-dummy-value-2026")
HASHER = _api_main.HASHER
TEST_HASH = HASHER.hash("Testing-password-Long-2026!")
from hydro_api.storage import User,Membership,Organization,Asset

@pytest.fixture(scope='function')
def env(tmp_path):
    app=create_app(database_url='sqlite:///'+str(tmp_path/'v7.db'),
                   jwt_secret='v7-jwt-secret-for-unit-tests-never-production-123456',
                   audit_secret='v7-audit-secret-for-unit-tests-never-production-123456')
    dbmaker=app.state.SessionLocal
    with dbmaker() as db:
        db.add_all([Organization(id='magadan-lab',name='Magadan synthetic lab'), Organization(id='separate-org',name='Other test org')]); db.flush()
        users={}
        for name,org,role in [
            ('lead','magadan-lab','engineer'),('reviewer','magadan-lab','engineer'),
            ('finance','magadan-lab','economist'),('manager','magadan-lab','manager'),
            ('audit','magadan-lab','auditor'),('audit2','magadan-lab','auditor'),
            ('viewer','magadan-lab','viewer'),('other','separate-org','engineer'),
            ('otheraudit','separate-org','auditor')]:
            u=User(email=name+'@lab.invalid',password_hash=TEST_HASH)
            db.add(u);db.flush();users[name]=u.id
            db.add(Membership(org_id=org,user_id=u.id,role=role))
        db.add(Asset(id='feeder-a',org_id='magadan-lab',name='Synthetic feeder A',classification='LAB_REFERENCE'))
        db.add(Asset(id='feeder-b',org_id='separate-org',name='Synthetic feeder B',classification='LAB_REFERENCE'))
        db.commit()
    client=TestClient(app,raise_server_exceptions=True)
    tokens={}
    for name in users:
        r=client.post('/v7/auth/login',json={'email':name+'@lab.invalid','password':'Testing-password-Long-2026!'})
        assert r.status_code==200,r.text
        tokens[name]=r.json()['access_token']
    def h(name):return {'Authorization':'Bearer '+tokens[name]}
    yield {'client':client,'h':h,'app':app,'tokens':tokens,'users':users,'db':dbmaker}
    client.close()
    app.state.engine.dispose()

@pytest.fixture
def prepared(env):
    c=env['client'];h=env['h'];base='/v7/orgs/magadan-lab'
    p={'reference_name':'Synthetic test two-bus feeder - NOT actual Magadan network',
       'source_voltage_kv_ll':20,'load_p_mw':5,'load_q_mvar':2,
       'line_r_ohm_per_phase':0.3,'line_x_ohm_per_phase':0.4,'period_hours':100}
    e=c.post(base+'/evidence',headers=h('lead'),json={'asset_id':'feeder-a','kind':'grid_input',
        'source_ref':'SYNTHETIC-LAB-FEEDER-A-v1','payload':p});assert e.status_code==201,e.text
    evid=e.json()['id']
    v=c.post(base+'/evidence/'+evid+'/review',headers=h('audit'),json={'accepted':True,'note':'Approved test dataset, synthetic only'});assert v.status_code==200,v.text
    m=c.post(base+'/models',headers=h('lead'),json={'asset_id':'feeder-a','algorithm':'balanced_two_bus_AC_PQ_lab_v1','params':{}});assert m.status_code==201,m.text
    mid=m.json()['id']
    v=c.post(base+'/models/'+mid+'/review',headers=h('audit'),json={'accepted':True,'note':'Approved laboratory model version'});assert v.status_code==200,v.text
    run=c.post(base+'/runs',headers=h('lead'),json={'asset_id':'feeder-a','model_id':mid,'evidence_id':evid});assert run.status_code==201,run.text
    return {'env':env,'base':base,'model':mid,'evidence':evid,'run':run.json()['id'],'case':p,'result':run.json()['result']}
