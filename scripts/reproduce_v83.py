#!/usr/bin/env python3
"""Create reproducible V8.3 synthetic hydrological/physical sensitivity matrix.

No real curves or inflow observations, no financial effect, no operating advice.
"""
from __future__ import annotations
import argparse, hashlib, json, sys, csv
from copy import deepcopy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
from hydro_api.cascade_v83 import CoupledCascadeV83, evaluate_coupled_cascade_v83
from tests_v83.fixture import cascade_case_v83
from hydro_api.forecast_v82 import ENGINE_TAG as FORECAST_ENGINE_V82
from hydro_api.cascade_v83 import ENGINE_TAG as CASCADE_ENGINE_V83


def json_digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,
           separators=(',',':'),allow_nan=False).encode()).hexdigest()


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=ROOT/'artifacts_v83')
    args=ap.parse_args(argv)
    args.out.mkdir(parents=True,exist_ok=True)
    rows=[]; cases=[];reports={}
    for regime in (-30,0,30,65,100):
        for lag in (0,12,24,36):
            d=cascade_case_v83(delay_hours=lag)
            # Prior-day releases are varied only in the sensitivity matrix,
            # allowing the travel lag to change downstream arrivals explicitly.
            if lag:
                d['route']['previous_daily_releases_cms']=[145,132][:len(d['route']['previous_daily_releases_cms'])]
                d['upper']['previous_release_cms']=145
            for x in d['forecast']['observations'][-28:]:
                x['mean_flow_cms']=max(0,round(x['mean_flow_cms']+regime,7))
            model=CoupledCascadeV83.model_validate(d)
            r=evaluate_coupled_cascade_v83(model)
            key=f'regime_{regime:+d}_lag_{lag:02d}'
            cases.append({'key':key,'sha256':json_digest(model.model_dump(mode='json'))})
            reports[key]=r
            for s in r['scenarios']:
                rows.append({'test_case':key,'regime_offset_cms':regime,'lag_hours':lag,
                 'branch':s['name'],'upstream_forecast_cms':s['upper_forecast_inflow_cms'],
                 'upper_end_storage_m3':round(s['upper']['end_storage_m3'],3),
                 'lower_end_storage_m3':round(s['lower']['end_storage_m3'],3),
                 'arrived_upper_cms':round(s['transit']['arrival_mean_flow_cms'],6),
                 'transit_closing_m3':round(s['transit']['closing_in_transit_m3'],3),
                 'total_energy_mwh':None if s['total_energy_mwh'] is None else round(s['total_energy_mwh'],6),
                 'conservation_residual_m3':s['global_mass_balance_residual_m3'],
                 'violations':';'.join(s['violations']),
                 'empirical_coverage_fraction':r['hydrology_report']['holdout_empirical_coverage_fraction'],
                 'hydrology_mae_cms':r['hydrology_report']['holdout_mae_cms'],
                 'production_ready':r['production_ready']})
    # Boundary failures are a separate stress block, not probabilistic paths.
    for label,callback in [
      ('capacity_limit',lambda d:d['upper'].update(rated_capacity_mw=45)),
      ('minimum_release',lambda d:d['upper'].update(minimum_release_cms=190)),
      ('storage_overflow',lambda d:d['upper'].update(start_volume_m3=1_099_000_000,
                                                     max_volume_m3=1_099_100_000)),
      ('ramp_limit',lambda d:d['lower'].update(previous_release_cms=0,max_daily_ramp_cms=10))]:
        d=cascade_case_v83()
        callback(d)
        model=CoupledCascadeV83.model_validate(d)
        report=evaluate_coupled_cascade_v83(model)
        reports['constraint_'+label]=report
    summary={
      'release':'8.3','scope':'SYNTHETIC_ONLY','forecast_engine':FORECAST_ENGINE_V82,
      'cascade_engine':CASCADE_ENGINE_V83,
      'synthetic_cases':len(cases),'forecast_regimes_cms':[-30,0,30,65,100],
      'travel_lags_hours':[0,12,24,36],
      'daily_branch_evaluations':len(rows),
      'constraint_stress_cases':4,
      'all_normal_scenarios_mass_balance':all(abs(x['conservation_residual_m3'])<0.001 for x in rows),
      'any_normal_scenario_infeasible':any(bool(x['violations']) for x in rows),
      'constraint_scenarios_flagged':{x: any(not y['feasible_under_synthetic_constraints']
          for y in reports['constraint_'+x]['scenarios']) for x in ('capacity_limit','minimum_release','storage_overflow','ramp_limit')},
      'min_coverage_fraction':min(x['empirical_coverage_fraction'] for x in rows),
      'max_hydrology_mae_cms':max(x['hydrology_mae_cms'] for x in rows),
      'all_energy_values_nonfinance':all(not r['eligible_for_financial_ledger'] and
                                            r['monetary_benefit_rub'] is None and
                                            not r['production_ready'] for r in reports.values()),
      'source_data_attested':False,'external_engineering_verified':False,
      'magadan_field_pilot_passed':False,'native_pg17_rls_passed':False,
    }
    assert summary['all_normal_scenarios_mass_balance']
    assert summary['all_energy_values_nonfinance']
    assert all(summary['constraint_scenarios_flagged'].values())
    path=args.out/'cascade_scenario_matrix_v83.csv'
    with path.open('w',newline='',encoding='utf-8') as fd:
        out=csv.DictWriter(fd,fieldnames=list(rows[0]))
        out.writeheader();out.writerows(rows)
    (args.out/'cascade_scenario_index_v83.json').write_text(json.dumps({
      'summary':summary,'scenario_inputs':cases,
      'report_digest_sha256':{k:json_digest(v) for k,v in reports.items()},
      'source_hash_sha256':{
        'cascade_v83.py':hashlib.sha256((ROOT/'server/hydro_api/cascade_v83.py').read_bytes()).hexdigest(),
        'forecast_v82.py':hashlib.sha256((ROOT/'server/hydro_api/forecast_v82.py').read_bytes()).hexdigest()},
    },indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (args.out/'synthetic_cascade_v83.json').write_text(json.dumps(
         cascade_case_v83(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2,ensure_ascii=False))
    return summary


if __name__=='__main__':
    main()
