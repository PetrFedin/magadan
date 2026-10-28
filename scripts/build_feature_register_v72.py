"""Create traceable V7.2 backlog without presenting proposals as implemented code."""
from pathlib import Path
import csv, json
ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'docs/V72_FEATURE_REGISTER.csv'
rows=[]
def put(module,items,status,priority,proof):
 for description in items.split(';'):
  d=description.strip()
  if d:rows.append({'id':f'HK72-{len(rows)+1:03}', 'module':module,'requirement':d,
                    'priority':priority,'implementation_status':status,
                    'proof_or_gap':proof,'production_accepted':'NO'})
put('Core','Server-side membership check;Role-specific study writing;Cross-tenant study read rejection;Append-only synthetic study rows;Versioned input/result hashes;Pinned-engine recalculation;Explicit source SYNTHETIC gate;Engine JSON schemas;Scenario pair comparison caveat',
    'LAB_IMPLEMENTED','P0','server/tests_v72/test_studies.py')
put('Core','Native PostgreSQL 17 RLS acceptance;Independent WORM retention test;Corporate SSO/MFA connection;Full browser HTTP E2E;Backup and restore rehearsal;Threat modeling and penetration testing',
    'NOT_ACCEPTED','P0','Native DB, corporate IdP and authorized environments required')
put('HydroForecast','Retrospective MAE/RMSE/bias;Out-of-time forecast training gate;Interval coverage and WAPE undefined safeguard',
    'LAB_IMPLEMENTED','P0','tests_v72/test_studies.py')
put('HydroForecast','Validated basin GIS;Physical snowmelt/runoff model;Historical hindcast against incumbent baseline;Forecast uncertainty calibration;Expert-approved hydrological dataset',
    'PLANNED','P1','Magadan hydrology expert and data rights required')
put('CascadeEconomics','Single-step two-reservoir mass balance;Hydropower approximation and storage bounds;Minimum release and rated-capacity checks',
    'LAB_IMPLEMENTED','P0','tests_v72/test_studies.py')
put('CascadeEconomics','Approved basin operating rules;Time-lagged water routing;Turbine curves and reservoir level curves;Multi-period mixed-integer optimization;Operator-authenticated stress scenarios',
    'PLANNED','P1','Independently validated operator model required')
put('TurbineReliability','Robust MAD deviation scoring;Operating-load comparability check;Explicit undefined failure probability',
    'LAB_IMPLEMENTED','P0','tests_v72/test_studies.py')
put('TurbineReliability','OEM-grade sensor calibration;Failure event taxonomy and EAM integration;Independent detection-performance study;Confirmed spare-part lead times and North logistics',
    'PLANNED','P1','Maintenance history and expert verification required')
put('GridLoss','Balanced two-bus numerical AC calculation;Independent high-voltage solution comparison;Power balance residual verification',
    'LAB_IMPLEMENTED','P0','server/hydro_api/engineering.py and legacy tests')
put('GridLoss','Verified Magadan feeder topology;Multi-bus unbalanced power flow;N-1 independent engineering verification;Technical-vs-nontechnical losses allocation;Post-construction savings counterfactual',
    'PLANNED','P1','Authorized operational data and industry tool benchmark required')
put('HeatNet','Steady-state heat delivery and UA loss;Thermal units and temperature assumptions',
    'LAB_IMPLEMENTED','P0','tests_v72/test_studies.py')
put('HeatNet','Pressure and hydraulic network solver;Pipe friction and distributed heat exchange;Calibration against actual measurements;Regional heat-service reliability and tariff accounting',
    'PLANNED','P1','Approved ZuluThermo-like engineering baseline required')
put('HydroCAPEX','Decimal-based discounted cashflows;Mandatory investment preservation;Dependencies and cycle rejection;Mutual exclusion and yearly budget enforcement;Duplicate benefit key rejection',
    'LAB_IMPLEMENTED','P0','tests_v72/test_studies.py')
put('HydroCAPEX','Corporate ERP/EPM budget binding;Legal engineering approval;WBS/CBS and bills of quantity;BIM/4D review;Magadan climate/geocryology and logistics;Actual post-investment effectiveness',
    'PLANNED','P1','Economic sponsor, cost evidence and legal construction docs required')
put('Regional','Owner-authorized asset data acquisition;Independent field engineer signoff;Procurement and grants eligibility dossier;Regulatory applicability by project;Economic and social benefit separation',
    'NOT_ACCEPTED','P0','RusHydro and individual asset owners have not authorized pilot data')
with output.open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
summary={'total':len(rows),'by_status':{k:sum(r['implementation_status']==k for r in rows) for k in sorted(set(r['implementation_status'] for r in rows))},
         'production_accepted':0,'verification_basis':'Laboratory tests only; planned items unimplemented'}
(ROOT/'artifacts_v72/feature_register_summary.json').write_text(json.dumps(summary,indent=2))
print(summary)
