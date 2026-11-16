#!/usr/bin/env python3
"""Independent hourly discretization of pure travel-time shift (synthetic).

Checks conservation of a piecewise constant flow history; not field hydraulic
validation, a calibrated routing solver or a production clearance.
"""
from __future__ import annotations
import json, random, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
from hydro_api.cascade_v83 import UniformTravelLagV83, route_uniform_day


def hourly_flow(t:int, flows:list[float])->float:
    idx=-(t//24)
    if not 0 <= idx < len(flows):
        raise ValueError('SOURCE_HOUR_OUTSIDE_RECOVERED_FLOW_HISTORY')
    return flows[idx]


def hour_reference(delay:int, flows:list[float]):
    arrived=sum(hourly_flow(hour-delay,flows) for hour in range(24))/24
    opening=3600*sum(hourly_flow(hour,flows) for hour in range(-delay,0))
    closing=3600*sum(hourly_flow(hour,flows) for hour in range(24-delay,24))
    mass_error=opening+flows[0]*86400-arrived*86400-closing
    return arrived,opening,closing,mass_error


def main():
    rng=random.Random(8302026)
    records=[]
    for lag in range(73):
        for sample in range(6):
            history_days=(lag+23)//24
            flows=[round(rng.uniform(0,400),6) for _ in range(1+history_days)]
            inp=UniformTravelLagV83(delay_hours=lag,
                previous_daily_releases_cms=flows[1:],
                source_ref='SYNTHETIC-INDEPENDENT-HOURLY-REFERENCE-2026')
            computed=route_uniform_day(flows[0],inp)
            arrived,opening,closing,residual=hour_reference(lag,flows)
            abs_error=max(abs(computed['arrival_mean_flow_cms']-arrived),
                abs(computed['opening_in_transit_m3']-opening)/86400,
                abs(computed['closing_in_transit_m3']-closing)/86400,
                abs(residual)/86400)
            if abs_error>1e-7:
                raise AssertionError(f'ROUTING_REFERENCE_MISMATCH: lag={lag}, sample={sample}, error={abs_error}')
            records.append(abs_error)
    result={'release':'8.3.1','scope':'SYNTHETIC_HOURLY_REFERENCE_ONLY',
       'independent_integer_hour_lags_inclusive':[0,72],
       'samples_per_lag':6,'scenarios':len(records),'seed':8302026,
       'max_flow_equivalent_error_cms':max(records),
       'conservation_check_passed':True,
       'external_hydraulic_solver_executed':False,
       'actual_magadan_hydrological_data_used':False,
       'production_ready':False}
    path=ROOT/'artifacts_v83/independent_hourly_route_v83.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':main()
