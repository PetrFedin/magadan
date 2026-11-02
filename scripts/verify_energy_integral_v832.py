#!/usr/bin/env python3
"""Deterministic independent dense-time quadrature against V8.3.2 energy.

Only synthetic, constant-discharge and piecewise-linear rating curves.
This is NOT independent engineering validation or an external hydraulic solver.
"""
from __future__ import annotations
import csv
import json
from bisect import bisect_right
from math import fsum
from pathlib import Path
from random import Random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from hydro_api.cascade_v83 import ReservoirV83, reservoir_step
from tests_v83.fixture import cascade_case_v83


def independent_stage(volume, xs, stages):
    # Distinct reference implementation: interval lookup via binary search.
    if volume < xs[0] or volume > xs[-1]:
        raise ValueError('reference outside stage data')
    pos=min(max(bisect_right(xs, volume)-1,0),len(xs)-2)
    return stages[pos]+(stages[pos+1]-stages[pos])*(volume-xs[pos])/(xs[pos+1]-xs[pos])


def run(seed=8322026, scenarios=256, n_steps=4096):
    rng=Random(seed)
    readings=[]
    xs=[900_000_000.,940_000_000.,985_000_000.,1_030_000_000.,1_100_000_000.]
    for i in range(scenarios):
        stages=[375.]
        for _ in range(4):
            stages.append(stages[-1]+rng.uniform(5,28))
        first=rng.uniform(910_000_000,1_000_000_000)
        last=min(1_089_999_999.,first+rng.uniform(-5_000_000,91_000_000))
        spec=cascade_case_v83()['upper']
        spec['storage_curve']=[{'volume_m3':x,'upstream_elevation_m':y} for x,y in zip(xs,stages)]
        spec['start_volume_m3']=first
        spec['rated_capacity_mw']=1000
        res=ReservoirV83.model_validate(spec)
        incoming=150+(last-first)/86400
        out=reservoir_step(res,incoming,1000)
        if out['violations'] or out['energy_mwh'] is None:
            raise RuntimeError(f'SYNTHETIC_REFERENCE_FIXTURE_INVALID {i}: {out["violations"]}')
        # Reference samples at the midpoint of each 24h time bin. All
        # time-varying input is storage under a constant net daily flow.
        stages_along=(independent_stage(first+(last-first)*(j+.5)/n_steps,xs,stages)
                      for j in range(n_steps))
        avg_ref=fsum(stages_along)/n_steps
        # Tailwater = 303 at total 150 m3/s; loss = 1 m, eta = 0.90,
        # Q_turb = 125. These derive from the synthetic fixture, not field.
        coefficient=1000*9.80665*125*.9/1_000_000*24
        ref_energy=coefficient*(avg_ref-303-1)
        midpoint=coefficient*(independent_stage((first+last)/2,xs,stages)-304)
        err=abs(out['energy_mwh']-ref_energy)
        if err>0.002:
            raise AssertionError(f'INDEPENDENT_QUADRATURE_MISMATCH {i}: {err:.9f} MWh')
        readings.append({'sample_id':i,'start_storage_m3':first,'end_storage_m3':last,
                         'exact_integral_mwh':out['energy_mwh'],
                         'independent_4096_step_mwh':ref_energy,
                         'abs_reference_error_mwh':err,
                         'old_midpoint_mwh':midpoint,
                         'old_midpoint_signed_bias_mwh':midpoint-out['energy_mwh']})
    errs=[v['abs_reference_error_mwh'] for v in readings]
    b=[v['old_midpoint_signed_bias_mwh'] for v in readings]
    summary={'release':'V8.3.2', 'scope':'SYNTHETIC_CONSTANT_FLOW_EXACT_HEAD_INTEGRATION_ONLY',
             'seed':seed,'cases':scenarios,'steps_per_case':n_steps,
             'reference': 'INDEPENDENT_BISECT_AND_MIDPOINT_TIME_QUADRATURE',
             'max_abs_reference_error_mwh':max(errs),
             'mean_abs_reference_error_mwh':fsum(errs)/len(errs),
             'old_midpoint_mean_abs_bias_mwh':fsum(map(abs,b))/len(b),
             'old_midpoint_max_abs_bias_mwh':max(map(abs,b)),
             'all_256_reference_checks_pass':True,
             'real_hydrological_data_used':False,
             'external_hydraulic_solver_verified':False,
             'native_postgresql17_verified':False,
             'production_eligible':False}
    folder=ROOT/'artifacts_v832';folder.mkdir(exist_ok=True)
    (folder/'independent_energy_quadrature_v832.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    with (folder/'independent_energy_quadrature_v832.csv').open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(readings[0]));writer.writeheader();writer.writerows(readings)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary


if __name__=='__main__':run()
