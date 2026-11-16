"""End-to-end HTTP lab handoff tests. No Magadan field measurements."""
import json,copy
from pathlib import Path
import pytest
from sqlalchemy import text,select
from hydro_api.storage import ResearchHandoff, StudyRun

S=json.loads((Path(__file__).parents[1]/'ui'/'samples_v72.json').read_text())

def register(env, modules=('hydroforecast','cascade','turbine')):
    c,h=env['client'],env['h'];ids={}
    for mod in modules:
        r=c.post('/v72/orgs/magadan-lab/studies',headers=h('lead'),json={
            'asset_id':'feeder-a','module':mod,'source_ref':'SYNTHETIC-V75-LAB-SOURCE',
            'scenario_group':'magadan_synthetic_v75','case':S[mod]})
        assert r.status_code==201,r.text
        ids[mod]=r.json()['id']
    return ids

def hydro_payload(ids):
    return {'kind':'forecast_to_cascade','left_study_id':ids['hydroforecast'],
            'right_study_id':ids['cascade'],'forecast_bridge':{
            'scenario':'point','step_hours':24,'travel_lag_steps':0,
            'hydrological_mapping_ref':'SYNTHETIC-CATCHMENT-BRIDGE-V75'}}

def maintenance_payload(ids):
    return {'kind':'turbine_to_maintenance','left_study_id':ids['turbine'],
            'maintenance_bridge':{
            'planning_reference':'SYNTHETIC-MAGADAN-REPAIR-PLANNING-V75',
            'options':[{'option_id':'inspection','action':'inspection','materials_rub':'15000',
                  'labor_rub':'25000','north_logistics_rub':'30000','outage_hours':'2',
                  'downtime_value_rub_per_hour':'3000','lead_time_days':7,
                  'basis_ref':'SYNTHETIC-INSPECTION-BASIS-V75'},
                {'option_id':'repair','action':'repair','materials_rub':'120000',
                  'labor_rub':'40000','north_logistics_rub':'60000','outage_hours':'15',
                  'downtime_value_rub_per_hour':'3000','lead_time_days':30,
                  'basis_ref':'SYNTHETIC-REPAIR-BASIS-V75'}]}}


def test_hydro_to_cascade_http_reproduction_and_tenant(env):
    ids=register(env,('hydroforecast','cascade'))
    c,h=env['client'],env['h'];base='/v75/orgs/magadan-lab/handoffs'
    payload=hydro_payload(ids)
    assert c.post(base,headers=h('viewer'),json=payload).status_code==403
    assert c.post(base,headers=h('finance'),json=payload).status_code==403
    res=c.post(base,headers=h('lead'),json=payload)
    assert res.status_code==201,res.text
    d=res.json();id=d['id']
    assert d['result']['n_steps']==3 and d['industrial_approval_eligible'] is False
    assert c.get(base+'/'+id,headers=h('viewer')).status_code==200
    assert c.get('/v75/orgs/separate-org/handoffs/'+id,headers=h('other')).status_code==404
    r=c.post(base+'/'+id+'/reproduce',headers=h('audit'))
    assert r.status_code==200,r.text
    assert r.json()['reproduced'] and r.json()['source_count']==2
    assert c.post(base+'/'+id+'/reproduce',headers=h('viewer')).status_code==403
    assert c.post(base,headers=h('lead'),json=payload).status_code==409
    assert c.get('/v7/orgs/magadan-lab/audit/verify',headers=h('audit')).json()['valid'] is True


def test_maintenance_http_options_and_dedupe(env):
    ids=register(env,('turbine',));c,h=env['client'],env['h'];base='/v75/orgs/magadan-lab/handoffs'
    resp=c.post(base,headers=h('lead'),json=maintenance_payload(ids))
    assert resp.status_code==201,resp.text
    r=resp.json()
    assert r['result']['auto_recommended_option_id'] is None
    assert r['result']['options'][0]['total_direct_plus_downtime_rub']=='76000.00'
    assert r['result']['expected_avoided_failure_cost_rub'] is None
    assert c.post(base+'/'+r['id']+'/reproduce',headers=h('audit')).status_code==200
    assert c.post(base,headers=h('lead'),json=maintenance_payload(ids)).status_code==409


def test_wrong_modules_and_unrelated_sources_are_rejected(env):
    ids=register(env);c,h=env['client'],env['h'];base='/v75/orgs/magadan-lab/handoffs'
    p=hydro_payload(ids);p['left_study_id']=ids['turbine']
    assert c.post(base,headers=h('lead'),json=p).status_code==422
    p=maintenance_payload(ids);p['right_study_id']=ids['cascade']
    assert c.post(base,headers=h('lead'),json=p).status_code==422
    p=hydro_payload(ids);p['left_study_id']='another-company-secret'
    assert c.post(base,headers=h('lead'),json=p).status_code==404


def test_handoff_require_programme_membership(env):
    ids=register(env);c,h=env['client'],env['h']
    programme={'reference_code':'LAB-V75-PROGRAMME-01','title':'Synthetic Magadan research package',
     'purpose':'Research only, independent engineering validation for Magadan region still missing.',
     'study_ids':[ids['hydroforecast'],ids['turbine']], 'scope':'SYNTHETIC_MAGADAN_RESEARCH_ONLY'}
    r=c.post('/v74/orgs/magadan-lab/programmes',headers=h('finance'),json=programme)
    assert r.status_code==201,r.text;pid=r.json()['id']
    p=hydro_payload(ids);p['programme_id']=pid
    assert c.post('/v75/orgs/magadan-lab/handoffs',headers=h('lead'),json=p).status_code==409
    p=maintenance_payload(ids);p['programme_id']=pid
    r=c.post('/v75/orgs/magadan-lab/handoffs',headers=h('lead'),json=p)
    assert r.status_code==201,r.text
    assert c.post('/v75/orgs/magadan-lab/handoffs/'+r.json()['id']+'/reproduce',headers=h('audit')).status_code==200


def test_append_only_sqlite_and_immutable_hash_guard(env):
    ids=register(env,('turbine',));c,h=env['client'],env['h'];base='/v75/orgs/magadan-lab/handoffs'
    r=c.post(base,headers=h('lead'),json=maintenance_payload(ids));assert r.status_code==201,r.text
    id=r.json()['id']
    with env['db']() as db:
        with pytest.raises(Exception,match='APPEND_ONLY'):
            db.execute(text('UPDATE research_handoffs SET kind=:k WHERE id=:id'),{'k':'forged','id':id});db.commit()
        db.rollback()
        with pytest.raises(Exception,match='APPEND_ONLY'):
            db.execute(text('DELETE FROM research_handoffs WHERE id=:id'),{'id':id});db.commit()
        db.rollback()
        # Compromised local SQLite admin can remove a trigger; the application must still detect tampering.
        db.execute(text('DROP TRIGGER lock_research_handoffs_update'))
        db.execute(text("UPDATE research_handoffs SET snapshot_sha256='"+'0'*64+"' WHERE id=:id"),{'id':id})
        db.commit()
    assert c.get(base+'/'+id,headers=h('viewer')).status_code==409


def test_mutated_source_rejected_even_if_child_record_is_intact(env):
    ids=register(env,('turbine',));c,h=env['client'],env['h'];base='/v75/orgs/magadan-lab/handoffs'
    r=c.post(base,headers=h('lead'),json=maintenance_payload(ids));assert r.status_code==201
    id=r.json()['id']
    with env['db']() as db:
        db.execute(text('DROP TRIGGER lock_study_runs_update'))
        db.execute(text("UPDATE study_runs SET result_sha256='"+'0'*64+"' WHERE id=:id"),{'id':ids['turbine']})
        db.commit()
    assert c.post(base+'/'+id+'/reproduce',headers=h('audit')).status_code==409


def test_unauthorized_non_lab_asset_blocked(env):
    ids=register(env,('turbine',));c,h=env['client'],env['h']
    with env['db']() as db:
        db.execute(text("UPDATE assets SET classification='NON_LAB' WHERE id='feeder-a'"))
        db.commit()
    assert c.post('/v75/orgs/magadan-lab/handoffs',headers=h('lead'),json=maintenance_payload(ids)).status_code==409


def test_openapi_v75_contract_and_strict_scope(env):
    d=env['client'].get('/openapi.json').json()['paths']
    assert '/v75/orgs/{org_id}/handoffs' in d
    assert '/v75/orgs/{org_id}/handoffs/{handoff_id}/reproduce' in d
    assert all('scada' not in p and 'operate' not in p for p in d)
    assert env['client'].get('/v75/meta/readiness').json()['production_ready'] is False


def test_research_programme_handoff_listing_and_reproduction(env):
    ids=register(env)
    c,h=env['client'],env['h']
    programme={'reference_code':'LAB-V75-INTEGRATED-MAGADAN','title':'Synthetic studies and handoff review',
        'purpose':'Maintain explicit internal links between technical models with no field authority.',
        'study_ids':list(ids.values()),'scope':'SYNTHETIC_MAGADAN_RESEARCH_ONLY'}
    rp=c.post('/v74/orgs/magadan-lab/programmes',headers=h('finance'),json=programme)
    assert rp.status_code==201,rp.text
    pid=rp.json()['id']
    base='/v75/orgs/magadan-lab/handoffs'
    h1=hydro_payload(ids);h1['programme_id']=pid
    h2=maintenance_payload(ids);h2['programme_id']=pid
    assert c.post(base,headers=h('lead'),json=h1).status_code==201
    assert c.post(base,headers=h('lead'),json=h2).status_code==201
    l=c.get(f'/v75/orgs/magadan-lab/programmes/{pid}/handoffs',headers=h('viewer'))
    assert l.status_code==200,l.text
    assert sorted(l.json()['handoff_kinds'])==['forecast_to_cascade','turbine_to_maintenance']
    assert 'NATIVE_POSTGRESQL_RLS_NOT_ACCEPTED' in l.json()['unclosed_gates']
    repro=c.post(f'/v75/orgs/magadan-lab/programmes/{pid}/reproduce-handoffs',headers=h('audit'))
    assert repro.status_code==200,repro.text
    assert repro.json()['attached_handoffs_recomputed']==2
    assert repro.json()['parent_programme_models_reproduced_here'] is False
    assert c.post(f'/v74/orgs/magadan-lab/programmes/{pid}/reproduce',headers=h('audit')).status_code==200
    assert c.get(f'/v75/orgs/separate-org/programmes/{pid}/handoffs',headers=h('other')).status_code==404
