#!/usr/bin/env python3
"""End-to-end reproducible synthetic lab showcase, no field / external systems."""
import json,os,hashlib,secrets,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from hydro_api.main import create_app,HASHER,sha
from hydro_api.storage import Organization,User,Membership,Asset
from tests_v75.test_handoff_api import maintenance_payload
from tests_v79.test_measurement import sample

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'artifacts_v79'/'showcase_trace_v79.json'
with tempfile.TemporaryDirectory(prefix='hk-v79-synthetic-') as temp:
    app=create_app(database_url='sqlite:///'+temp+'/lab.db',
       jwt_secret=secrets.token_urlsafe(45), audit_secret=secrets.token_urlsafe(45))
    users={};pwd='LAB-Synthetic-Password-Not-Production-2026!'
    with app.state.SessionLocal() as db:
        db.add(Organization(id='magadan-synthetic',name='No actual utility organization'))
        db.flush()
        db.add(Asset(id='feeder-synthetic',org_id='magadan-synthetic',name='Synthetic feeder boundary'))
        db.flush()
        for name,role in [('engineer','engineer'),('economist','economist'),('auditor','auditor')]:
            u=User(email=name+'@invalid.local',password_hash=HASHER.hash(pwd),active=True)
            db.add(u);db.flush();users[name]=u.id
            db.add(Membership(org_id='magadan-synthetic',user_id=u.id,role=role,active=True))
        db.commit()
    client=TestClient(app)
    headers={}
    for name in users:
        auth=client.post('/v7/auth/login',json={'email':name+'@invalid.local','password':pwd})
        assert auth.status_code==200,auth.text
        headers[name]={'Authorization':'Bearer '+auth.json()['access_token']}
    studies=json.loads((ROOT/'server'/'ui'/'samples_v72.json').read_text())
    t=client.post('/v72/orgs/magadan-synthetic/studies',headers=headers['engineer'],json={
        'asset_id':'feeder-synthetic','module':'turbine','scenario_group':'synthetic-mv-v79',
        'source_ref':'SYNTHETIC-ONLY-V79-TURBINE','case':studies['turbine']})
    assert t.status_code==201,t.text
    hand=client.post('/v75/orgs/magadan-synthetic/handoffs',headers=headers['engineer'],
                     json=maintenance_payload({'turbine':t.json()['id']}))
    assert hand.status_code==201,hand.text
    hand_id=hand.json()['id']
    claim={'asset_id':'feeder-synthetic','family':'MAINTENANCE_COST',
           'source_kind':'MAINTENANCE_HANDOFF_V75','source_id':hand_id,
           'start_year':2030,'end_year':2035,
           'measurement_plan_ref':'SYNTHETIC-V79-LAB-PLAN-2030',
           'measurement_boundary_description':'Synthetic single feeder asset with no physical meter rights or field inspection.',
           'comparison_normalization':'The same load, operating environment, physical asset and normalized baseline must be independently verified before any savings.'}
    reserved=client.post('/v79/orgs/magadan-synthetic/benefit-reservations',
                         headers=headers['economist'],json=claim)
    assert reserved.status_code==201,reserved.text
    repeat=client.post('/v79/orgs/magadan-synthetic/benefit-reservations',
                       headers=headers['economist'],json=claim)
    assert repeat.status_code==409,repeat.text
    screen=sample();screen['asset_id']='feeder-synthetic'
    measure=client.post('/v79/orgs/magadan-synthetic/measurement-screens',
                        headers=headers['engineer'],json=screen)
    assert measure.status_code==201,measure.text
    rid=measure.json()['id']
    auditor=client.post('/v79/orgs/magadan-synthetic/measurement-screens/'+rid+'/reproduce',
                        headers=headers['auditor'])
    assert auditor.status_code==200,auditor.text
    audit=client.get('/v7/orgs/magadan-synthetic/audit/verify',headers=headers['auditor'])
    assert audit.status_code==200 and audit.json()['valid'] is True
    output={
        'release':'V7.9-LAB', 'region':'MAGADAN_CONCEPT_NOT_REAL_NETWORK',
        'synthetic_source_sha256':sha(screen),
        'maintenance_handoff_id':hand_id,
        'benefit_reservation_id':reserved.json()['id'],
        'duplicate_claim_blocked_http_status':repeat.status_code,
        'benefit_lab_estimated_gross_rub':reserved.json()['lab_estimated_gross_rub'],
        'mv_report_id':rid,
        'mv_input_sha256':measure.json()['input_sha256'],
        'mv_report_sha256':measure.json()['report_sha256'],
        'mv_report':measure.json()['report'],
        'auditor_recomputed_from_source':auditor.json()['audit_reproduced'],
        'local_hmac_audit_valid':audit.json()['valid'],
        'external_worm_attestation':False,
        'postgresql_native_rls_passed':False,
        'actual_savings_confirmed':False,
        'industrial_approval_eligible':False,
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(output,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in output.items() if k not in ('mv_report',)},indent=2))
    print('signed_difference_kwh',output['mv_report']['signed_normalized_difference_kwh'])
    client.close()
    app.state.engine.dispose()
