#!/usr/bin/env python3
"""Reproduce V7.3 SYNTHETIC source-to-finance sample; does not prove Magadan site ROI."""
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
from hydro_api.radial_grid import RadialCase,solve_radial,physical_comparability
from hydro_api.finance_evidence import LabFinance,evaluate_feeder_alternative


def canonical(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def sha(obj):
    return hashlib.sha256(canonical(obj).encode('utf-8')).hexdigest()


def main():
    base={'model_kind':'radial_ac_v73','reference_name':'SYNTHETIC_MAGADAN_REFERENCE_ONLY',
          'source_voltage_kv_ll':20,'min_voltage_pu':.9,
          'nodes':[{'node_id':'n1','parent_id':'SOURCE','r_ohm_per_phase':.25,'x_ohm_per_phase':.3,'load_p_mw':2,'load_q_mvar':.6,'ampacity_a':1000},
                   {'node_id':'n2','parent_id':'n1','r_ohm_per_phase':.17,'x_ohm_per_phase':.22,'load_p_mw':1.5,'load_q_mvar':.55,'ampacity_a':1000},
                   {'node_id':'n3','parent_id':'n1','r_ohm_per_phase':.12,'x_ohm_per_phase':.15,'load_p_mw':1,'load_q_mvar':.3,'ampacity_a':1000}],
          'windows':[{'name':'normal','scale':1,'hours':120},{'name':'winter_peak','scale':1.2,'hours':24}]}
    proposed=copy.deepcopy(base)
    proposed['nodes'][0]['r_ohm_per_phase']=.13
    finance={'scope':'SYNTHETIC_NOT_A_TARIFF','capital_cost_rub':'1800000',
             'annual_opex_delta_rub':'150000','value_per_kwh_rub':{'low':'2','base':'3','high':'5'},
             'discount_rate':'0.12','years':8,'annual_repeat_count':'50',
             'notes':'Synthetic unit economics solely for deterministic testing.'}
    b=RadialCase.model_validate(base);p=RadialCase.model_validate(proposed);f=LabFinance.model_validate(finance)
    ok,reasons=physical_comparability(b,p)
    assert ok and not reasons
    br=solve_radial(b);pr=solve_radial(p)
    eco=evaluate_feeder_alternative(b,p,br,pr,f)
    assert br['status']=='LAB_ENGINEERING_LIMITS_MET' and pr['status']=='LAB_ENGINEERING_LIMITS_MET'
    report={'release':'V7.3','name':'GridLoss → HydroCAPEX synthetic evidence demonstration',
            'scope':'SYNTHETIC_ONLY_NOT_RUSHYDRO_NOT_MAGADAN_REAL_DATA',
            'input_sha256':{'baseline':sha(base),'alternative':sha(proposed),'finance':sha(finance)},
            'source_code_sha256':{name:hashlib.sha256((ROOT/'server'/'hydro_api'/name).read_bytes()).hexdigest()
                for name in ('radial_grid.py','finance_evidence.py')},
            'physical_comparability':{'accepted':ok,'reasons':reasons},
            'baseline':{'input':base,'output':br},
            'alternative':{'input':proposed,'output':pr},
            'finance':{'input':finance,'output':eco},
            'guards':{'automatic_real_site_approval':False,'native_pg17_accepted':False,
                      'licensed_magadan_data_used':False,'independent_field_signoff':False},
            'formula':'CF_year=(P_loss_base-P_loss_proposed)[MWh]×1000×annual_repeat×unit_value[RUB/kWh]-OPEX_year; NPV=-CAPEX+Σ CF/(1+r)^t'}
    dest=ROOT/'artifacts_v73'/'showcase_trace_v73.json'
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'filename':str(dest),'baseline_loss_mwh':br['total_line_energy_loss_mwh'],
                      'alternative_loss_mwh':pr['total_line_energy_loss_mwh'],
                      'annual_savings_kwh':eco['annual_energy_savings_kwh'],
                      'npv_base_rub':eco['price_scenarios']['base']['npv_rub'],
                      'physical_limits_met':True,'industrial_approval':False}))

if __name__=='__main__':main()
