#!/usr/bin/env python3
"""Auditable synthetic-only V7.5 HTTP storyline; creates no real assets.

Outputs no secrets, tokens, passwords or personal data. Only lab outcomes.
"""
import argparse,json,secrets,tempfile
from pathlib import Path
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from hydro_api.main import create_app
from hydro_api.storage import Organization,User,Membership,Asset
ROOT=Path(__file__).resolve().parents[1]
S=json.loads((ROOT/'server/ui/samples_v72.json').read_text())


def run():
    org='magadan-synthetic-v75';asset_id='synthetic-lab-asset'
    with tempfile.TemporaryDirectory(prefix='hydrokontur-v75-') as directory:
        password=secrets.token_urlsafe(32)
        app=create_app('sqlite:///'+str(Path(directory)/'lab.db'),
            jwt_secret=secrets.token_urlsafe(48),audit_secret=secrets.token_urlsafe(48))
        ph=PasswordHasher(time_cost=1,memory_cost=8192,parallelism=1)
        with app.state.SessionLocal.begin() as db:
            db.add(Organization(id=org,name='NOT an operating company; synthetic only'))
            for role in ('engineer','economist','auditor'):
                u=User(email=role+'@lab.invalid',password_hash=ph.hash(password))
                db.add(u);db.flush();db.add(Membership(org_id=org,user_id=u.id,role=role))
            db.add(Asset(id=asset_id,org_id=org,name='NON-GEOGRAPHIC, SYNTHETIC ENERGY ASSET',
                         classification='LAB_REFERENCE'))
        with TestClient(app) as client:
            token={}
            for role in ('engineer','economist','auditor'):
                r=client.post('/v7/auth/login',json={'email':role+'@lab.invalid','password':password})
                assert r.status_code==200,r.text
                token[role]=r.json()['access_token']
            def h(r):return {'Authorization':'Bearer '+token[r]}
            def post(path,body,role):
                response=client.post(path,headers=h(role),json=body)
                if response.status_code not in (200,201):
                    raise RuntimeError(path+' returned '+str(response.status_code)+' '+response.text[:300])
                return response.json()
            ids={}
            for module,case in S.items():
                ids[module]=post('/v72/orgs/'+org+'/studies',{
                    'asset_id':asset_id,'module':module,'source_ref':'SYNTHETIC-V75-SCENARIO',
                    'scenario_group':'synthetic_cascade_and_maintenance',
                    'case':case},'economist' if module=='hydrocapex' else 'engineer')['id']
            edges=[{'from_study_id':ids[l], 'to_study_id':ids[r],'relationship':kind}
                   for l,r,kind in (
                    ('hydroforecast','cascade','forecast_context_for_cascade'),
                    ('cascade','hydrocapex','cascade_context_for_capex'),
                    ('turbine','hydrocapex','diagnostics_context_for_capex'),
                    ('gridloss','hydrocapex','grid_context_for_capex'),
                    ('heatnet','hydrocapex','heat_context_for_capex'))]
            wbs={'title':'Synthetic research WBS for Magadan demonstration','currency':'RUB',
                 'tax_basis':'EXCL_VAT_SYNTHETIC','annual_caps_rub':{'2027':'900000','2028':'1100000'},
                 'contingency_percent':'0',
                 'lines':[
                    {'code':'01.01','title':'Synthetic technical survey','category':'survey',
                     'year':2027,'quantity':'1','unit':'lot','unit_price_rub':'500000',
                     'price_source_ref':'SYNTHETIC-PRICE-ESTIMATE-V75','predecessors':[]},
                    {'code':'02.01','title':'Synthetic project engineering','category':'design',
                     'year':2027,'quantity':'1','unit':'lot','unit_price_rub':'250000',
                     'price_source_ref':'SYNTHETIC-PRICE-ESTIMATE-V75','predecessors':['01.01']},
                    {'code':'03.01','title':'Synthetic equipment purchase','category':'equipment',
                     'year':2028,'quantity':'1','unit':'lot','unit_price_rub':'700000',
                     'price_source_ref':'SYNTHETIC-PRICE-ESTIMATE-V75','predecessors':['02.01']},
                    {'code':'04.01','title':'Synthetic commissioning work','category':'commissioning',
                     'year':2028,'quantity':'1','unit':'lot','unit_price_rub':'150000',
                     'price_source_ref':'SYNTHETIC-PRICE-ESTIMATE-V75','predecessors':['03.01']} ]}
            programme=post('/v74/orgs/'+org+'/programmes',{
                'reference_code':'LAB-MAGADAN-V75-CASE',
                'title':'Synthetic Magadan engineering research dossier',
                'purpose':'Reproducible source-pinned cross-domain research with no operational or investment authority.',
                'study_ids':list(ids.values()),'links':edges,'capital':wbs},'economist')
            pid=programme['id'];base='/v75/orgs/'+org+'/handoffs'
            hydro=post(base,{'kind':'forecast_to_cascade','programme_id':pid,
                'left_study_id':ids['hydroforecast'],'right_study_id':ids['cascade'],
                'forecast_bridge':{'scenario':'point','step_hours':24,'travel_lag_steps':1,
                  'arrival_history_cms':[60],
                  'hydrological_mapping_ref':'SYNTHETIC-HYDRO-CATCHMENT-V75'}},'engineer')
            maint=post(base,{'kind':'turbine_to_maintenance','programme_id':pid,
                'left_study_id':ids['turbine'],'maintenance_bridge':{
                    'planning_reference':'SYNTHETIC-MAINTENANCE-MAGADAN-V75',
                    'options':[
                     {'option_id':'inspection','action':'inspection','materials_rub':'10000',
                      'labor_rub':'25000','north_logistics_rub':'15000','outage_hours':'2',
                      'downtime_value_rub_per_hour':'3000','lead_time_days':7,
                      'basis_ref':'SYNTHETIC-INSPECTION-PRICE-V75'},
                     {'option_id':'repair','action':'repair','materials_rub':'130000',
                      'labor_rub':'40000','north_logistics_rub':'60000','outage_hours':'14',
                      'downtime_value_rub_per_hour':'3000','lead_time_days':45,
                      'basis_ref':'SYNTHETIC-REPAIR-PRICE-V75'}]}},'engineer')
            e1=post(base+'/'+hydro['id']+'/reproduce',{},'auditor')
            e2=post(base+'/'+maint['id']+'/reproduce',{},'auditor')
            parent=post('/v74/orgs/'+org+'/programmes/'+pid+'/reproduce',{},'auditor')
            linked=post('/v75/orgs/'+org+'/programmes/'+pid+'/reproduce-handoffs',{},'auditor')
            response=client.get('/v7/orgs/'+org+'/audit/verify',headers=h('auditor'))
            assert response.status_code==200,response.text
            audit=response.json();assert audit['valid'] is True
            return {'release':'V7.5-LAB','data_classification':'100_PERCENT_SYNTHETIC',
                    'region':'MAGADAN_CANDIDATE_ONLY','field_data_used':False,
                    'six_modules_saved':len(ids),'programme_id':pid,
                    'programme_sha256':parent['programme_sha256'],
                    'parent_models_reproduced':parent.get('engineering_models_reexecuted',False),
                    'handoff_count':linked['attached_handoffs_recomputed'],
                    'hydrological_handoff':{'id':hydro['id'],'reproduced':e1['reproduced'],
                      'n_steps':hydro['result']['n_steps'],
                      'constraint_violations':hydro['result']['constraint_violations'],
                      'energy_mwh':hydro['result']['synthetic_total_energy_mwh']},
                    'maintenance_handoff':{'id':maint['id'],'reproduced':e2['reproduced'],
                      'auto_recommendation':maint['result']['auto_recommended_option_id'],
                      'failure_probability':maint['result']['calibrated_failure_probability'],
                      'options':maint['result']['options']},
                    'wbs_synthetic_total_rub':programme['summary']['capital_budget_screen']['total_synthetic_cost_rub'],
                    'audit_chain_verified':audit['valid'],
                    'postgresql_rls_native_test':'NOT_EXECUTED',
                    'independent_engineer':'NOT_AVAILABLE',
                    'real_idp_and_worm':'NOT_CONNECTED',
                    'industrial_approval_eligible':False}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);args=ap.parse_args()
    result=run();p=Path(args.output);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))
    print('V75_SYNTHETIC_HANDOFF_TRACE_PASS',p)
