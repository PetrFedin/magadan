"""Synthetic only; generator is not a Magadan hydrological observation dataset."""
from datetime import datetime, timezone, timedelta
from math import sin, cos, pi


def daily_flow_fixture(n=168,horizon=2,alpha=0.1,trend=0.16,regime_shift=0):
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    observations=[]
    for i in range(n):
        at=start+timedelta(days=i)
        flow=160 + trend*i + 15*sin(2*pi*i/32) + 5*sin(2*pi*i/8) + 4*cos(2.1*i)
        if i>=n-28:
            flow+=regime_shift
        observations.append({
           'observed_at':at.isoformat(),
           'available_at':(at+timedelta(hours=6)).isoformat(),
           'mean_flow_cms':round(max(0,flow),7),
           'source_ref':f'SYNTHETIC-MAGADAN-LAB-DAILY-Q-{i:04d}',
        })
    return {
      'asset_id':'feeder-a','as_of':(start+timedelta(days=n-1,hours=10)).isoformat(),
      'horizon_days':horizon,'miscoverage_alpha':alpha,
      'monitor_threshold_cms':200,
      'observations':observations,
    }


def linear_flow_fixture(n=140,horizon=2,starting=20,step=0.5):
    d=daily_flow_fixture(n=n,horizon=horizon)
    for i,item in enumerate(d['observations']):
        item['mean_flow_cms']=starting+i*step
    d['monitor_threshold_cms']=None
    return d
