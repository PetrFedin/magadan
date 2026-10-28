"""V7.6 HTTP vertical slice: protected, immutable, reproducible, no field eligibility."""
import json
from pathlib import Path
from sqlalchemy import text
from hydro_api.storage import AssurancePackV76
from .test_assurance_domain import budget,value
S=json.loads((Path(__file__).parents[1]/'ui'/'samples_v72.json').read_text())


def sources(env):
    c,h=env['client'],env['h'];out={}
    for mod in ('hydroforecast','cascade','turbine'):
        r=c.post('/v72/orgs/magadan-lab/studies',headers=h('lead'),json={
            'asset_id':'feeder-a','module':mod,'source_ref':'SYNTHETIC-V76-TEST-SOURCE',
            'scenario_group':'synthetic-magadan-v76','case':S[mod]})
        assert r.status_code==201,r.text
        out[mod]=r.json()['id']
    return out


def create_parent(env, ids, *, capital=True):
    data={'reference_code':'LAB-V76-FINANCIAL-RESEARCH','title':'Synthetic Magadan investment research dossier',
          'purpose':'Test engineering evidence and cash flow calculations using entirely fictitious sources and money.',
          'study_ids':list(ids.values()),'capital':budget().model_dump(mode='json') if capital else None,
          'scope':'SYNTHETIC_MAGADAN_RESEARCH_ONLY'}
    r=env['client'].post('/v74/orgs/magadan-lab/programmes',headers=env['h']('finance'),json=data)
    assert r.status_code==201,r.text
    return r.json()['id']


def handoffs(env,ids,pid):
    c,h=env['client'],env['h'];url='/v75/orgs/magadan-lab/handoffs'
    hydro={'kind':'forecast_to_cascade','left_study_id':ids['hydroforecast'],'right_study_id':ids['cascade'],
           'programme_id':pid,'forecast_bridge':{'scenario':'point','step_hours':24,'travel_lag_steps':0,
           'hydrological_mapping_ref':'SYNTHETIC-V76-FC-MAPPING'}}
    repair={'kind':'turbine_to_maintenance','left_study_id':ids['turbine'],'programme_id':pid,
            'maintenance_bridge':{'planning_reference':'SYNTHETIC-V76-MAINTENANCE-PLANNING',
            'options':[{'option_id':'check','action':'inspection','materials_rub':'10000',
                        'labor_rub':'14000','north_logistics_rub':'9000','outage_hours':'2',
                        'downtime_value_rub_per_hour':'1000','lead_time_days':5,'basis_ref':'SYNTHETIC-V76-INSPECTION-BASIS'},
                       {'option_id':'replace','action':'replacement','materials_rub':'90000',
                        'labor_rub':'12000','north_logistics_rub':'20000','outage_hours':'7',
                        'downtime_value_rub_per_hour':'1000','lead_time_days':40,'basis_ref':'SYNTHETIC-V76-REPLACE-BASIS'}]}}
    res=[]
    for x in (hydro,repair):
        r=c.post(url,headers=h('lead'),json=x)
        assert r.status_code==201,r.text
        res.append(r.json()['id'])
    return res


def payload(pid, hs):
    return {'reference_code':'LAB-V76-ASSURANCE-PACK-A','programme_id':pid,'handoff_ids':hs,
            'routing_handoff_id':hs[0],
            'routing':{'time_constant_hours':12,'initial_routed_outflow_cms':30,
                       'mapping_ref':'SYNTHETIC-V76-HYDRAULIC-MAPPING'},
            'finance':value().model_dump(mode='json'),
            'scope':'SYNTHETIC_DECISION_EVIDENCE_NOT_APPROVAL'}


def test_full_http_pack_review_and_role_isolation(env):
    ids=sources(env);pid=create_parent(env,ids);hs=handoffs(env,ids,pid)
    c,h=env['client'],env['h'];url='/v76/orgs/magadan-lab/assurance-packs'
    p=payload(pid,hs)
    assert c.post(url,headers=h('lead'),json=p).status_code==403
    assert c.post(url,headers=h('viewer'),json=p).status_code==403
    r=c.post(url,headers=h('finance'),json=p)
    assert r.status_code==201,r.text
    rid=r.json()['id'];result=r.json()
    assert result['industrial_approval_eligible'] is False
    assert result['routing_status']=='SYNTHETIC_MASS_BALANCE_OK'
    assert result['financial']['capital_screen']['total_synthetic_cost_rub']=='3050000.00'
    assert c.get(url+'/'+rid,headers=h('viewer')).status_code==200
    assert c.get('/v76/orgs/separate-org/assurance-packs/'+rid,headers=h('other')).status_code==404
    assert c.post(url+'/'+rid+'/reproduce',headers=h('viewer')).status_code==403
    replay=c.post(url+'/'+rid+'/reproduce',headers=h('audit'))
    assert replay.status_code==200,replay.text
    assert replay.json()['source_handoffs_recomputed']==2
    assert c.post(url,headers=h('finance'),json=p).status_code==409
    duplicate_claim=payload(pid,hs)
    duplicate_claim['reference_code']='LAB-V76-OTHER-REFERENCE'
    duplicate_claim['finance']['benefit_key']='DIFFERENT_BUT_SAME_SOURCE'
    assert c.post(url,headers=h('finance'),json=duplicate_claim).status_code==409
    assert c.get('/v7/orgs/magadan-lab/audit/verify',headers=h('audit')).json()['valid'] is True
    assert c.get('/v76/meta/readiness').json()['production_ready'] is False


def test_unknown_handoff_wrong_reference_and_wrong_routing_kind(env):
    ids=sources(env);pid=create_parent(env,ids);hs=handoffs(env,ids,pid)
    c,h=env['client'],env['h'];url='/v76/orgs/magadan-lab/assurance-packs'
    data=payload(pid,hs)
    data['handoff_ids']=['random-not-visible']
    data['routing_handoff_id']=None;data['routing']=None
    assert c.post(url,headers=h('finance'),json=data).status_code==404
    data=payload(pid,hs);data['routing_handoff_id']=hs[1]
    assert c.post(url,headers=h('finance'),json=data).status_code==422
    data=payload(pid,hs);data['handoff_ids']=[hs[0],hs[0]]
    assert c.post(url,headers=h('finance'),json=data).status_code==422


def test_parent_missing_capex_refused(env):
    ids=sources(env);pid=create_parent(env,ids,capital=False);hs=handoffs(env,ids,pid)
    result=env['client'].post('/v76/orgs/magadan-lab/assurance-packs',headers=env['h']('finance'),json=payload(pid,hs))
    assert result.status_code==409


def test_sqlite_append_only_and_snapshot_tamper_detection(env):
    ids=sources(env);pid=create_parent(env,ids);hs=handoffs(env,ids,pid)
    c,h=env['client'],env['h'];url='/v76/orgs/magadan-lab/assurance-packs'
    r=c.post(url,headers=h('finance'),json=payload(pid,hs));assert r.status_code==201,r.text
    rid=r.json()['id']
    with env['db']() as db:
        import pytest
        with pytest.raises(Exception,match='APPEND_ONLY'):
            db.execute(text('UPDATE assurance_packs_v76 SET benefit_key=:v WHERE id=:id'),{'v':'rewritten','id':rid});db.commit()
        db.rollback()
        with pytest.raises(Exception,match='APPEND_ONLY'):
            db.execute(text('DELETE FROM assurance_packs_v76 WHERE id=:id'),{'id':rid});db.commit()
        db.rollback()
        db.execute(text('DROP TRIGGER lock_assurance_packs_v76_update'))
        db.execute(text("UPDATE assurance_packs_v76 SET snapshot_sha256='"+'0'*64+"' WHERE id=:id"),{'id':rid});db.commit()
    assert c.post(url+'/'+rid+'/reproduce',headers=h('audit')).status_code==409


def test_source_mutation_detected_in_child_replay(env):
    ids=sources(env);pid=create_parent(env,ids);hs=handoffs(env,ids,pid)
    c,h=env['client'],env['h'];url='/v76/orgs/magadan-lab/assurance-packs'
    r=c.post(url,headers=h('finance'),json=payload(pid,hs));assert r.status_code==201,r.text
    with env['db']() as db:
        db.execute(text('DROP TRIGGER lock_study_runs_update'))
        db.execute(text("UPDATE study_runs SET input_sha256='"+'0'*64+"' WHERE id=:id"),{'id':ids['hydroforecast']});db.commit()
    assert c.post(url+'/'+r.json()['id']+'/reproduce',headers=h('audit')).status_code==409


def test_openapi_v76_contract_and_no_field_endpoints(env):
    paths=env['client'].get('/openapi.json').json()['paths']
    assert '/v76/orgs/{org_id}/assurance-packs' in paths
    assert '/v76/orgs/{org_id}/assurance-packs/{pack_id}/reproduce' in paths
    assert not any('/scada/' in p or '/dispatch/' in p for p in paths)
