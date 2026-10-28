import csv
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=root/'docs/V72_FEATURE_REGISTER.csv';target=root/'docs/V73_FEATURE_REGISTER.csv'
with source.open(newline='') as f:rows=list(csv.DictReader(f))
fieldnames=list(rows[0].keys())
addition=[
 ('GridLoss','Radial network topology with cycle and orphan rejection','P0','LAB_IMPLEMENTED','server/tests_v73/test_radial_and_finance.py'),
 ('GridLoss','Balanced 3phase multi-node sweep plus independent nodal KCL crosscheck','P0','LAB_IMPLEMENTED','server/tests_v73/test_radial_and_finance.py'),
 ('GridLoss','Multi-period weighted feeder energy losses','P0','LAB_IMPLEMENTED','server/tests_v73/test_radial_and_finance.py'),
 ('GridLoss','Ampacity and voltage-limits diagnostic flags','P0','LAB_IMPLEMENTED','server/tests_v73/test_radial_and_finance.py'),
 ('GridLoss','Like-for-like topology and load invariant comparison','P0','LAB_IMPLEMENTED','server/tests_v73/test_radial_and_finance.py'),
 ('GridLoss','Synthetic radial HTTP calculation tenant-scoped','P0','LAB_IMPLEMENTED','server/tests_v73/test_radial_and_finance.py'),
 ('HydroCAPEX','Physical-result to NPV scenarios with correct MWh/kWh units','P0','LAB_IMPLEMENTED','server/tests_v73/test_radial_and_finance.py'),
 ('HydroCAPEX','Annual hour expansion bounded by 8784','P0','LAB_IMPLEMENTED','server/tests_v73/test_radial_and_finance.py'),
 ('HydroCAPEX','Immutable synthetic economic dossier and independent reproduction','P0','LAB_IMPLEMENTED','server/tests_v73/test_radial_and_finance.py'),
 ('HydroCAPEX','Prevent repeat benefit-key and baseline/alternative pair','P0','LAB_IMPLEMENTED','server/tests_v73/test_radial_and_finance.py'),
 ('Core','Reject NaN Inf booleans and near-zero line resistance','P0','LAB_IMPLEMENTED','server/tests_v73/test_radial_and_finance.py'),
 ('Core','Bounded per-request radial model complexity','P0','LAB_IMPLEMENTED','server/tests_v73/test_radial_and_finance.py'),
 ('Core','PostgreSQL dossier tenant RLS and composite FK migration draft','P0','DESIGNED_UNACCEPTED','server/migrations/070_grid_economic_dossiers_v73.sql'),
 ('Regional','Full native PG17 run of dossier migration and direct SQL bypass tests','P0','NOT_ACCEPTED','Dedicated PostgreSQL17 + psycopg + signed test report required'),
 ('Regional','Field feeder independently validated against pandapower or OpenDSS','P0','NOT_ACCEPTED','Written data consent and professional engineering signoff required'),
 ('Regional','Actual baseline loss monitoring with approved measurement and verification','P1','PLANNED','Field measurements and M&V protocol required'),
 ('GridLoss','Unbalanced phase and transformer load flow','P1','PLANNED','External validated industrial solver required'),
 ('GridLoss','N-1 outage and protection checks','P1','PLANNED','System operator signed model and N-1 benchmark required'),
 ('HydroForecast','Value-of-information attribution shared with cascade scenarios','P1','PLANNED','Approved hydrology hindcast and economic value model required'),
 ('CascadeEconomics','Multi-step travel delay and release constraints','P1','PLANNED','Approved Kolyma cascade physical model required'),
 ('TurbineReliability','EAM events and correctly calibrated defect-detection performance','P1','PLANNED','Confirmed repair logs and independent expert labels required'),
 ('HeatNet','Verified hydraulic/thermal model against heat industry standard','P1','PLANNED','Authorized Magadan heat-network data and engineer signoff required'),
 ('HydroCAPEX','Reconciliation against enterprise approved project valuation','P1','PLANNED','Corporate finance methodology, ERP approvals and contract costs required'),
]
for i,(domain,requirement,priority,state,proof) in enumerate(addition,69):
 rows.append({'id':f'HK73-{i:03d}','module':domain,'requirement':requirement,'priority':priority,
              'implementation_status':state,'proof_or_gap':proof,'production_accepted':'NO'})
# Preserve original 68 rows and adapt their column headings; archive stays included.
# Prior row key is module; for older spreadsheet exports preserve same fields.
with target.open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=fieldnames);w.writeheader();w.writerows(rows)
assert len({r['id'] for r in rows})==len(rows)
print('requirements:',len(rows),'laboratory:',sum(r['implementation_status']=='LAB_IMPLEMENTED' for r in rows))
