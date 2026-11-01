"""PNG exhibits of synthetic forecast evaluation. No real hydrology."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'artifacts_v82'
lines=json.loads((folder/'scenario_comparison_v82.json').read_text())
report=json.loads((folder/'single_forecast_report_v82.json').read_text())['report']

fig,ax=plt.subplots(figsize=(12,4.2))
rows=report['holdout_rows'];idx=list(range(1,len(rows)+1))
ax.plot(idx,[x['actual_cms'] for x in rows],label='Actual (synthetic)')
ax.plot(idx,[x['point_cms'] for x in rows],label='Two-day horizon forecast')
ax.fill_between(idx,[x['lower_cms'] for x in rows],[x['upper_cms'] for x in rows],alpha=0.2,label='Empirical residual band')
ax.set(xlabel='Held-out target index (days)',ylabel='Daily mean streamflow, m³/s',title='HydroForecast V8.2 / synthetic historical holdout (not a Magadan forecast)')
ax.legend(loc='best');ax.grid(alpha=.25);fig.tight_layout();fig.savefig(folder/'forecast_holdout_v82.png',dpi=155)
plt.close(fig)

fig,ax=plt.subplots(figsize=(11,4.5))
for scenario in ['ordinary','increase_30_cms','increase_65_cms','decrease_30_cms']:
    a=sorted((x for x in lines if x['scenario']==scenario),key=lambda x:x['horizon_days'])
    ax.plot([x['horizon_days'] for x in a],[x['mae_cms'] for x in a],marker='o',label=scenario)
ax.set(xlabel='Forecast horizon (days)',ylabel='Holdout MAE (m³/s)',title='Synthetic sensitivity to regime shifts / no real field data')
ax.legend(loc='upper left');ax.grid(alpha=.25);fig.tight_layout();fig.savefig(folder/'forecast_stress_v82.png',dpi=155)
plt.close(fig)
print('PNG created',[(p.name,p.stat().st_size) for p in folder.glob('forecast_*v82.png')])
