"""Single-figure, source-backed laboratory plots; not real hydropower charts."""
from pathlib import Path
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts_v83'
with (OUT/'cascade_scenario_matrix_v83.csv').open(encoding='utf-8') as f:
    rows=list(csv.DictReader(f))
fig,ax=plt.subplots(figsize=(9,5))
for name in ('dry','central','wet'):
    data=sorted((r for r in rows if r['regime_offset_cms']=='0' and r['branch']==name),
                key=lambda x:float(x['lag_hours']))
    ax.plot([float(x['lag_hours']) for x in data],
            [float(x['total_energy_mwh']) for x in data],marker='o',label=name)
ax.set(title='Synthetic cascade / fixed releases / no real data',xlabel='Pure transport lag (hours)',ylabel='Illustrative total energy (MWh / day)')
ax.legend();fig.tight_layout();fig.savefig(OUT/'cascade_energy_vs_lag_v83.png',dpi=160);plt.close(fig)

fig,ax=plt.subplots(figsize=(9,5))
regimes=sorted(set(int(r['regime_offset_cms']) for r in rows))
cover=[100*float(next(r['empirical_coverage_fraction'] for r in rows if int(r['regime_offset_cms'])==regime)) for regime in regimes]
ax.bar([str(x) for x in regimes],cover)
ax.axhline(90,linestyle='--',label='Nominal 90% (not achieved)')
ax.set(title='Synthetic holdout coverage under artificial regime shifts',xlabel='Artificial streamflow step (m³/s)',ylabel='Empirical interval coverage (%)',ylim=(0,100))
ax.legend();fig.tight_layout();fig.savefig(OUT/'cascade_coverage_v83.png',dpi=160);plt.close(fig)
print('CHARTS',len(list(OUT.glob('cascade_*v83.png'))),'SYNTHETIC_ONLY')
