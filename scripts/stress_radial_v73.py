#!/usr/bin/env python3
"""Deterministic SYNTHETIC-only radial mathematical stress/reproducibility check.

No field data, no certified engineering benchmark, no production readiness assertion.
"""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from hydro_api.radial_grid import RadialCase, solve_radial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default=str(ROOT/'artifacts_v73'/'stress_radial_v73.json'))
    ap.add_argument('--seed', type=int, default=20261023)
    ap.add_argument('--cases', type=int, default=64)
    args = ap.parse_args()
    if not 1 <= args.cases <= 120:
        raise SystemExit('case count out of permitted lab range')
    rng = random.Random(args.seed)
    max_p_balance = 0.0
    max_q_balance = 0.0
    max_kcl_v = 0.0
    max_sweep = 0
    failed = []
    cases_hash = hashlib.sha256()
    for i in range(args.cases):
        count = rng.randint(1,7)
        nodes = []
        for j in range(count):
            parent = 'SOURCE' if j == 0 else ('SOURCE' if rng.random()<.2 else 'n'+str(rng.randrange(j)))
            nodes.append({'node_id':'n'+str(j), 'parent_id':parent,
                         'r_ohm_per_phase':round(rng.uniform(.02,.20),6),
                         'x_ohm_per_phase':round(rng.uniform(.01,.23),6),
                         'load_p_mw':round(rng.uniform(.03,.45),6),
                         'load_q_mvar':round(rng.uniform(.01,.20),6),
                         'ampacity_a':2500})
        windows = [{'name':f'w{n}', 'hours':rng.randint(1,36), 'scale':round(rng.uniform(.6,1.6),6)}
                   for n in range(rng.randint(1,4))]
        raw = {'model_kind':'radial_ac_v73','reference_name':'SYNTHETIC-DETERMINISTIC-MONTE-CARLO',
               'source_voltage_kv_ll':rng.choice([10,20,35,60]),'min_voltage_pu':.7,
               'nodes':nodes,'windows':windows}
        cases_hash.update(json.dumps(raw, sort_keys=True, separators=(',',':')).encode())
        try:
            report = solve_radial(RadialCase.model_validate(raw))
            if report['status'] != 'LAB_ENGINEERING_LIMITS_MET':
                failed.append({'case':i,'reason':'constraint_violations','detail':report['constraint_violations']})
            for w in report['windows']:
                max_p_balance=max(max_p_balance,w['power_balance_residual_mw'])
                max_q_balance=max(max_q_balance,w['power_balance_residual_mvar'])
                max_kcl_v=max(max_kcl_v,w['max_kcl_discrepancy_v'])
                max_sweep=max(max_sweep,w['sweep_iterations'])
        except Exception as ex:
            failed.append({'case':i,'reason':type(ex).__name__,'detail':str(ex)})
    output={'release':'V7.3','scope':'SYNTHETIC_ONLY_NOT_MAGADAN_NETWORK',
            'not_an_external_independent_solver':True,'seed':args.seed,'case_count':args.cases,
            'input_cases_sha256':cases_hash.hexdigest(),'failures':failed,
            'max_active_balance_residual_mw':max_p_balance,
            'max_reactive_balance_residual_mvar':max_q_balance,
            'max_nodal_solver_voltage_difference_v':max_kcl_v,
            'max_backward_forward_iterations':max_sweep,'accepted':len(failed)==0}
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k not in ('failures',)}))
    if failed:
        print('FAILED CASES:',json.dumps(failed[:8]));raise SystemExit(1)

if __name__ == '__main__':main()
