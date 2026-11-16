#!/usr/bin/env python3
"""Reproduce an HTTP end-to-end SYNTHETIC regional research programme.

No external network, no real assets, no secrets saved, and no industrial approval.
"""
import argparse,copy,hashlib,json,secrets,tempfile
from pathlib import Path
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from hydro_api.main import create_app
from hydro_api.storage import Organization,User,Membership,Asset

ROOT=Path(__file__).resolve().parents[1]


def run():
    cases=json.loads((ROOT/'server/ui/samples_v72.json').read_text())
    radial=json.loads((ROOT/'server/ui/radial_sample_v73.json').read_text())
    org='magadan-synthetic-programme'
    with tempfile.TemporaryDirectory(prefix='hydro-v74-') as directory:
        key=secrets.token_urlsafe(48)
        app=create_app('sqlite:///'+str(Path(directory)/'evidence.db'),
            jwt_secret=secrets.token_urlsafe(48),audit_secret=secrets.token_urlsafe(48))
        hasher=PasswordHasher(time_cost=1,memory_cost=8192,parallelism=1)
        with app.state.SessionLocal.begin() as db:
            db.add(Organization(id=org,name='Synthetic Magadan research, not an energy company'))
            db.flush()
            for name,role in [('engineer','engineer'),('economist','economist'),('auditor','auditor')]:
                u=User(email=f'{name}@synthetic.invalid',password_hash=hasher.hash(key))
                db.add(u);db.flush()
                db.add(Membership(org_id=org,user_id=u.id,role=role))
            db.add(Asset(id='synthetic-asset',org_id=org,name='NOT a real Magadan energy asset',classification='LAB_REFERENCE'))
        with TestClient(app) as http:
            tokens={}
            for name in ['engineer','economist','auditor']:
                res=http.post('/v7/auth/login',json={'email':f'{name}@synthetic.invalid','password':key})
                assert res.status_code==200,res.text
                tokens[name]=res.json()['access_token']
            def auth(name):return {'Authorization':'Bearer '+tokens[name]}
            def post(url,body,actor):
                r=http.post(url,headers=auth(actor),json=body)
                if r.status_code not in (200,201):raise RuntimeError(f'{url}: {r.status_code} {r.text[:800]}')
                return r.json()
            def study(module,data,group):
                return post(f'/v72/orgs/{org}/studies',{'asset_id':'synthetic-asset',
                    'module':module,'source_ref':'SYNTHETIC-V74-SHOWCASE','scenario_group':group,
                    'case':data}, 'economist' if module=='hydrocapex' else 'engineer')['id']
            studies={n:study(n,v,'programme-2027') for n,v in cases.items()}
            links=[]
            for left,right,relation in [
                ('hydroforecast','cascade','forecast_context_for_cascade'),
                ('cascade','hydrocapex','cascade_context_for_capex'),
                ('turbine','hydrocapex','diagnostics_context_for_capex'),
                ('gridloss','hydrocapex','grid_context_for_capex'),
                ('heatnet','hydrocapex','heat_context_for_capex')]:
                links.append({'from_study_id':studies[left],'to_study_id':studies[right],'relationship':relation})
            ref=radial['case'];proposed=copy.deepcopy(ref)
            proposed['nodes'][0]['r_ohm_per_phase']=0.13
            gridids=[]
            for c in (ref,proposed):
                x=post(f'/v73/orgs/{org}/radial-runs',{
                    'asset_id':'synthetic-asset','scenario_group':'radial-2027',
                    'source_ref':'SYNTHETIC-V74-SHOWCASE','case':c},'engineer')
                gridids.append(x['run_id'])
            econ=post(f'/v73/orgs/{org}/economic-dossiers',{
                'asset_id':'synthetic-asset','baseline_run_id':gridids[0],
                'proposed_run_id':gridids[1], 'benefit_key':'synthetic_grid_2027',
                'finance':radial['finance']},'economist')
            heat_base=cases['heatnet'];heat_prop=copy.deepcopy(heat_base)
            heat_prop['overall_u_w_m_k']=1
            hids=[study('heatnet',v,'heat-2027') for v in (heat_base,heat_prop)]
            plan={'title':'Synthetic multi-year WBS — NOT a construction estimate',
                'currency':'RUB','tax_basis':'EXCL_VAT_SYNTHETIC',
                'annual_caps_rub':{'2027':'500000','2028':'1500000','2029':'800000'},
                'contingency_percent':'0', 'lines':[
                  {'code':'01','title':'Synthetic baseline survey', 'category':'survey','year':2027,
                   'quantity':'1','unit':'lot','unit_price_rub':'200000','price_source_ref':'SYNTHETIC-WBS-SURVEY','predecessors':[]},
                  {'code':'02','title':'Synthetic design review','category':'design','year':2027,
                   'quantity':'1','unit':'lot','unit_price_rub':'300000','price_source_ref':'SYNTHETIC-WBS-DESIGN','predecessors':['01']},
                  {'code':'03','title':'Synthetic equipment and deliveries','category':'equipment','year':2028,
                   'quantity':'1','unit':'lot','unit_price_rub':'1500000','price_source_ref':'SYNTHETIC-WBS-EQUIPMENT','predecessors':['02']},
                  {'code':'04','title':'Synthetic commissioning work','category':'commissioning','year':2029,
                   'quantity':'1','unit':'lot','unit_price_rub':'800000','price_source_ref':'SYNTHETIC-WBS-COMMISSION','predecessors':['03']}]}
            heat_screen={'baseline_study_id':hids[0],'proposed_study_id':hids[1],
               'benefit_key':'synthetic_heat_2027','finance':{
                 'scope':'SYNTHETIC_HEAT_NOT_TARIFF','hours_per_year':'5000',
                 'value_rub_per_kwh':{'low':'2','base':'3','high':'5'},
                 'capital_cost_rub':'1000000','annual_opex_delta_rub':'100000',
                 'discount_rate':'0.12','years':8,
                 'notes':'Synthetic heat assumption; no actual tariff or asset valuation.'}}
            body={'reference_code':'LAB-MAGADAN-REGION-V74','title':'Magadan synthetic interdisciplinary energy research',
                  'purpose':'Reproducible research case linking six engineering domains, one electrical loss alternative, one thermal loss alternative and the synthetic multi-year capital budget.',
                  'study_ids':list(studies.values())+gridids+hids,
                  'financial_dossier_ids':[econ['dossier_id']], 'links':links,
                  'heat_screenings':[heat_screen],'capital':plan,
                  'scope':'SYNTHETIC_MAGADAN_RESEARCH_ONLY'}
            programme=post(f'/v74/orgs/{org}/programmes',body,'economist')
            audit=post(f'/v74/orgs/{org}/programmes/{programme["id"]}/reproduce',{},'auditor')
            assert audit['reproduced'] is True
            assert programme['summary']['programme_status']=='LAB_SCREENING_WITHOUT_COMPUTATIONAL_BLOCKERS',programme['summary']['computational_blockers']
            assert programme['summary']['field_ready'] is False
            assert programme['summary']['capital_budget_screen']['total_synthetic_cost_rub']=='2800000.00'
            view=http.get(f'/v74/orgs/{org}/programmes/{programme["id"]}',headers=auth('auditor'))
            assert view.status_code==200
            report={'release':'v7.4','scope':'SYNTHETIC_LAB_ONLY','real_magadan_asset_data':False,
                    'industrial_validation':False,
                    'programme_snapshot_sha256':programme['snapshot_sha256'],
                    'api_reproduction':audit,
                    'readiness':programme['summary'],
                    'links':links,'programme_snapshot':view.json()['snapshot'],
                    'source_digest_sha256':hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                    'demo_notes':'IDs generated at runtime; pinned hashes allow replay within this lab database; not bitwise reproducibility across fresh databases.'}
            app.state.engine.dispose()
            return report

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',default=str(ROOT/'artifacts_v74/showcase_trace_v74.json'));args=ap.parse_args()
    report=run();target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'file':str(target),'status':report['readiness']['programme_status'],
        'study_count':report['readiness']['calculation_count'],
        'links':len(report['links']),
        'capital_total_rub':report['readiness']['capital_budget_screen']['total_synthetic_cost_rub'],
        'field_ready':report['readiness']['field_ready']},ensure_ascii=False,indent=2))
