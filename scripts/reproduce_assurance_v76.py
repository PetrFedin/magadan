#!/usr/bin/env python3
"""Offline showcase: all input values artificial. No field data or external systems."""
from __future__ import annotations
import json,secrets,tempfile,sys,argparse
from pathlib import Path
from fastapi.testclient import TestClient
from hydro_api.main import create_app
from hydro_api.storage import Organization,User,Membership,Asset
from hydro_api.main import HASHER

ROOT=Path(__file__).resolve().parents[1]
SOURCE=json.loads((ROOT/'server/ui/samples_v72.json').read_text())

def run():
    with tempfile.TemporaryDirectory(prefix='hydro-v76-synthetic-') as d:
        a=create_app(database_url='sqlite:///'+str(Path(d)/'lab.db'),
          jwt_secret=secrets.token_urlsafe(44),audit_secret=secrets.token_urlsafe(44))
        pwd=secrets.token_urlsafe(22);org='magadan-synthetic-v76';uids={}
        with a.state.SessionLocal() as db:
            db.add(Organization(id=org,name='Synthetic Magadan research, NOT existing electrical assets'));db.flush()
            db.add(Asset(id='lab-watershed-1',org_id=org,name='Lab example only',classification='LAB_REFERENCE'))
            for name,role in [('engineer','engineer'),('finance','economist'),('auditor','auditor')]:
                u=User(email=name+'@lab.invalid',password_hash=HASHER.hash(pwd));db.add(u);db.flush()
                db.add(Membership(org_id=org,user_id=u.id,role=role));uids[name]=u.id
            db.commit()
        with TestClient(a) as c:
            tokens={}
            for name in uids:
                response=c.post('/v7/auth/login',json={'email':name+'@lab.invalid','password':pwd})
                assert response.status_code==200,response.text
                tokens[name]=response.json()['access_token']
            def h(name):return {'Authorization':'Bearer '+tokens[name]}
            studies={}
            for module in ('hydroforecast','cascade','turbine'):
                response=c.post(f'/v72/orgs/{org}/studies',headers=h('engineer'),json={
                    'asset_id':'lab-watershed-1','module':module,'scenario_group':'lab-shared-v76',
                    'source_ref':'SYNTHETIC-V76-LAB-ONLY-SOURCE','case':SOURCE[module]})
                assert response.status_code==201,response.text
                studies[module]=response.json()['id']
            capital={'currency':'RUB','tax_basis':'EXCL_VAT_SYNTHETIC',
               'title':'Lab demonstration of staged capital allocation',
               'annual_caps_rub':{'2027':'500000','2028':'2000000','2029':'800000'},
               'contingency_percent':'0',
               'lines':[{'code':'survey','title':'Synthetic technical survey','category':'survey','year':2027,
                   'quantity':'1','unit':'package','unit_price_rub':'500000','price_source_ref':'SYNTHETIC-STAGED-SURVEY-V76'},
                  {'code':'equipment','title':'Synthetic equipment shipment','category':'equipment','year':2028,
                   'quantity':'1','unit':'package','unit_price_rub':'1800000','price_source_ref':'SYNTHETIC-STAGED-EQUIPMENT-V76','predecessors':['survey']},
                  {'code':'testing','title':'Synthetic commissioning program','category':'commissioning','year':2029,
                   'quantity':'1','unit':'package','unit_price_rub':'750000','price_source_ref':'SYNTHETIC-STAGED-TESTS-V76','predecessors':['equipment']}]}
            p=c.post(f'/v74/orgs/{org}/programmes',headers=h('finance'),json={
                'reference_code':'LAB-V76-SYNTHETIC-PROGRAMME',
                'title':'Synthetic Magadan engineering finance demonstration',
                'purpose':'Test programme version pins, staged capital, physical routing, maintenance and reproducibility with synthetic data only.',
                'study_ids':list(studies.values()),'capital':capital,'scope':'SYNTHETIC_MAGADAN_RESEARCH_ONLY'})
            assert p.status_code==201,p.text;pid=p.json()['id']
            settings=[{'kind':'forecast_to_cascade','left_study_id':studies['hydroforecast'],
              'right_study_id':studies['cascade'],'forecast_bridge':{'scenario':'point','step_hours':24,
                'travel_lag_steps':0,'hydrological_mapping_ref':'SYNTHETIC-V76-FORECAST-BRIDGE'}},
             {'kind':'turbine_to_maintenance','left_study_id':studies['turbine'],
              'maintenance_bridge':{'planning_reference':'SYNTHETIC-V76-MAINTENANCE-OPTIONS',
               'options':[{'option_id':'inspect','action':'inspection','materials_rub':'10000','labor_rub':'14000',
                 'north_logistics_rub':'9000','outage_hours':'2','downtime_value_rub_per_hour':'1000',
                 'lead_time_days':5,'basis_ref':'SYNTHETIC-V76-INSPECT'},
                 {'option_id':'repair','action':'repair','materials_rub':'90000','labor_rub':'12000',
                 'north_logistics_rub':'20000','outage_hours':'7','downtime_value_rub_per_hour':'1000',
                 'lead_time_days':40,'basis_ref':'SYNTHETIC-V76-REPAIR'}]}}]
            handoffs=[]
            for s in settings:
                s['programme_id']=pid
                resp=c.post(f'/v75/orgs/{org}/handoffs',headers=h('engineer'),json=s)
                assert resp.status_code==201,resp.text;handoffs.append(resp.json()['id'])
            body={'reference_code':'LAB-V76-INTEGRATED-SYNTHETIC-ASSURANCE','programme_id':pid,
                  'handoff_ids':handoffs,'routing_handoff_id':handoffs[0],
                  'routing':{'time_constant_hours':12,'initial_routed_outflow_cms':30,
                             'mapping_ref':'SYNTHETIC-V76-WATER-ROUTE'},
                  'finance':{'scope':'SYNTHETIC_INCREMENTAL_CASHFLOWS_ONLY',
                   'benefit_key':'synthetic_magadan_value_v76','source_assumption_ref':'SYNTHETIC-NO-REAL-ENERGY-VALUE',
                   'discounted_from_year':2027,'discount_rate':'0.12',
                   'benefit_scenarios':{'low':'0.5','base':'1','high':'1.5'},
                   'annual_gross_value_rub':{'2028':'200000','2029':'350000','2030':'500000','2031':'500000'},
                   'annual_incremental_opex_rub':{'2028':'20000','2029':'30000','2030':'30000','2031':'30000'},
                   'rationale':'Completely fictional avoided-cost profile for deterministic financial assurance.'},
                  'scope':'SYNTHETIC_DECISION_EVIDENCE_NOT_APPROVAL'}
            saved=c.post(f'/v76/orgs/{org}/assurance-packs',headers=h('finance'),json=body)
            assert saved.status_code==201,saved.text
            packid=saved.json()['id']
            detail=c.get(f'/v76/orgs/{org}/assurance-packs/{packid}',headers=h('auditor'))
            assert detail.status_code==200,detail.text
            replay=c.post(f'/v76/orgs/{org}/assurance-packs/{packid}/reproduce',headers=h('auditor'))
            assert replay.status_code==200,replay.text
            audit=c.get(f'/v7/orgs/{org}/audit/verify',headers=h('auditor'))
            assert audit.status_code==200,audit.text
            snap=detail.json()['snapshot']
            return {'release':'V7.6','all_source_data':'SYNTHETIC','six_product_sources':'THREE_STUDIES_AND_TWO_HANDOFFS_IN_THIS_DEMO',
             'programme_id':pid,'handoff_ids':handoffs,'assurance_pack_id':packid,
             'assurance_sha256':detail.json()['snapshot_sha256'],'reproduced':replay.json()['reproduced'],
             'source_handoffs_recomputed':replay.json()['source_handoffs_recomputed'],
             'audit_chain':audit.json(),'routed_scenario_status':snap['routed_ensemble']['status'],
             'routing_details':{'scenario_kind':snap['routed_ensemble']['scenario_envelope_kind'],
                'step_count':len(snap['routed_ensemble']['scenarios']['point']['rows']),
                'point_end_upper_storage_m3':snap['routed_ensemble']['scenarios']['point']['end_upper_storage_m3']},
             'finance':snap['financial']['scenario_results'],
             'wbs_cost_rub':snap['financial']['capital_screen']['total_synthetic_cost_rub'],
             'industrial_approval_eligible':False,'gates_not_closed':snap['gates_not_closed']}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True)
    args=ap.parse_args();result=run()
    file=Path(args.out);file.parent.mkdir(parents=True,exist_ok=True)
    file.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'reproduced':result['reproduced'],'wbs_cost_rub':result['wbs_cost_rub'],
                      'npvs':result['finance'],'audit_valid':result['audit_chain']['valid']},ensure_ascii=False,indent=2))
