#!/usr/bin/env python3
"""Reproducible synthetic hydrology scenarios; never real Magadan measurements."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
from hydro_api.forecast_v82 import DailyForecastResearchV82,evaluate_daily_forecast
from tests_v82.fixture import daily_flow_fixture,linear_flow_fixture

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'artifacts_v82'
DEST.mkdir(exist_ok=True)


def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

runs=[]
scenarios=[('ordinary',0),('increase_30_cms',30),('increase_65_cms',65),('decrease_30_cms',-30)]
for scenario,change in scenarios:
    for horizon in (1,2,3,5,7):
        raw=daily_flow_fixture(horizon=horizon,regime_shift=change)
        report=evaluate_daily_forecast(DailyForecastResearchV82.model_validate(raw))
        runs.append({'scenario':scenario,'horizon_days':horizon,
             'source_sha256':digest(raw),
             'selected_model':report['selected_model'],
             'mae_cms':report['holdout']['mae_cms'],
             'rmse_cms':report['holdout']['rmse_cms'],
             'bias_cms':report['holdout']['bias_cms'],
             'wape_percent':report['holdout']['wape_percent'],
             'actual_coverage':report['holdout']['interval_empirical_coverage_fraction'],
             'interval_misses':report['holdout']['interval_misses'],
             'calibration_radius_cms':report['calibration']['absolute_error_radius_cms'],
             'lag1':report['holdout']['held_out_lag1_residual_correlation'],
             'skill_vs_persistence_percent':report['holdout']['skill_vs_persistence_percent'],
             'future_point_cms':report['forecast']['point_cms'],
             'future_daily_volume_million_m3':report['forecast']['daily_volume_million_m3']['point'],
             'high_flow_holdout_count':report['holdout']['high_flow_holdout_count'],
             'risk_flags':report['risk_flags'],
             'real_magadan_data':False,'approval_eligible':False,
        })

case=daily_flow_fixture()
case_report=evaluate_daily_forecast(DailyForecastResearchV82.model_validate(case))
case_bundle={'case':case,'report':case_report,'input_sha256':digest(case),
             'report_sha256':digest(case_report),'engine_sha256':hashlib.sha256(
                (ROOT/'server/hydro_api/forecast_v82.py').read_bytes()).hexdigest(),
             'provenance':'SYNTHETIC_GENERATED_IN_CODE_NOT_HYDROLOGICAL_MEASUREMENTS',
             'industrial_approval_eligible':False}
(DEST/'synthetic_daily_flow_case_v82.json').write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n')
(DEST/'single_forecast_report_v82.json').write_text(json.dumps(case_bundle,ensure_ascii=False,indent=2)+'\n')
(DEST/'scenario_comparison_v82.json').write_text(json.dumps(runs,ensure_ascii=False,indent=2)+'\n')
with (DEST/'scenario_comparison_v82.csv').open('w',newline='') as f:
    keys=[k for k in runs[0] if k not in ('risk_flags',)]
    w=csv.DictWriter(f,fieldnames=keys)
    w.writeheader();w.writerows([{k:r[k] for k in keys} for r in runs])
with (DEST/'holdout_forecast_v82.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(case_report['holdout_rows'][0]))
    w.writeheader();w.writerows(case_report['holdout_rows'])
summary={
  'kind':'SYNTHETIC_STATISTICAL_EXPERIMENT',
  'model_name':'HydroForecast V8.2',
  'case_source_sha256':digest(case),
  'case_engine_sha256':case_bundle['engine_sha256'],
  'case_report_sha256':digest(case_report),
  'scenarios':len(scenarios),'horizons':[1,2,3,5,7],
  'tests_and_evaluation_windows':'initial 84, selection 28, calibration 28, holdout 28 (n=168)',
  'baseline':next(x for x in runs if x['scenario']=='ordinary' and x['horizon_days']==2),
  'shift':next(x for x in runs if x['scenario']=='increase_65_cms' and x['horizon_days']==2),
  'no_real_magadan_measurements':True,'real_tariff':False,'approved_hydro_dispatch':False,
}
(DEST/'executive_metrics_v82.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'scenarios':len(runs),'baseline':summary['baseline'],
                  'regime_shift':summary['shift']},ensure_ascii=False,indent=2))
