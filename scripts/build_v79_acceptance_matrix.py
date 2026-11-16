#!/usr/bin/env python3
"""Generate deterministic testable V79 -> V8 acceptance tracker. All entries are plans unless specified."""
from pathlib import Path
import csv

ROOT=Path(__file__).resolve().parents[1]
items=[]

def add(area, code, priority, requirement, acceptance, evidence, status, owner):
    items.append((f'{area}-{code:02d}',area,priority,requirement,acceptance,evidence,status,owner))

base=[
('PLATFORM', 'P0', 'Full native PostgreSQL 17 migration in isolated fresh database', 'All 001..140 migrations apply once; independent rollback/pool tests', 'Native psql test transcript', 'BLOCKED_NO_DATABASE', 'DBA'),
('PLATFORM','P0','RLS denies cross-org read and write, even stale pooled context', 'Negative and concurrent PG tests as constrained role', 'Query and role audit traces','SQL_CANDIDATE','DBA+Security'),
('PLATFORM','P0','Reconcile all historical benefit dossiers with exclusive registry','Every legacy dossier mapped, conflict resolved, official sums only from canonical registry','Migration dry-run reconciliation','PLANNED','Economist+DBA'),
('PLATFORM','P0','Canonical physical measurement boundary graph across assets','Same source or shared boundary cannot be doubly recognized','Boundary ownership signoff and overlap tests','PLANNED','Engineering+Finance'),
('PLATFORM','P0','Corporate OIDC/MFA plus revocation', 'Real identity provider integration and revoke-with-active-session test','OIDC/MFA transcript','BLOCKED_NO_IDP','Identity+Security'),
('PLATFORM','P0','External retention-enforced audit', 'Signed version receipt verified after restore and retried delivery','External archive attestation','BLOCKED_NO_WORM','Security+Audit'),
('PLATFORM','P0','Backup and restore validation', 'Reproduce dossier and audit after isolated restore','RTO/RPO and hash trace','PLANNED','DBA+Audit'),
('PLATFORM','P0','Live authenticated browser end-to-end checks','375/768/1440 responsive view, focus, keyboard, decision flow','Browser E2E and screenshots','BLOCKED_BROWSER','QA'),
('PLATFORM','P0','All data inputs show original observation and availability timestamps','Zero accidental future leak and meter interval overlap','Time-boundary tests','LAB_IMPLEMENTED','Data Steward'),
('PLATFORM','P0','Benefit reservation SQLite atomic overlap constraints','Parallel same source/years -> one success one conflict','Concurrent HTTP trace','LAB_IMPLEMENTED','Engineering'),
('PLATFORM','P0','Material source hash replay before research claim','All supported source kinds replay or verify pinned origin','Deterministic replay trace','LAB_IMPLEMENTED','Engineering'),
('PLATFORM','P1','Independent third-party physical solver','Executed version/host evidence and nodal comparison','Signed reference calculation','BLOCKED_NO_SOLVER','External Engineer'),
('PLATFORM','P1','Corporate ERP financial read-only integration','Reconciled cost line to authoritative budget data','Signed integration log','PLANNED','Finance IT'),
]
for ix,(area,p,req,acc,evid,status,owner) in enumerate(base,1): add(area,ix,p,req,acc,evid,status,owner)

by_area={
 'HYDROFORECAST':[
 ('P0','Select Kolym catchment and confirm data access','Signed scope, forecast issues, gauges, availability timestamps','PLANNED'),
 ('P1','Historical forecast replay without hindsight','Rolling-origin forecasts and independent hydrologist verification','PLANNED'),
 ('P1','Physics-based water balance and missing terms','Conservation residual and seasonal stress diagnostics','PLANNED'),
 ('P1','Ensemble interval calibration','Coverage and probabilistic score by hydrologic regime','PLANNED'),
 ('P1','Mapped forecast to cascade with exact basin and step','No arbitrary renaming of water boundary or unit','LAB_PARTIAL'),
 ('P2','Continuous skill monitoring and recalibration governance','New model version accepted only after holdout validation','PLANNED'),
 ],
 'CASCADE':[
 ('P0','Signed reservoir stage-storage and hydraulic curves','Calibrated upstream/downstream characteristics and hard constraints','PLANNED'),
 ('P1','Time-continuous reservoir routing','Mass balance and delay verified on independent historical data','LAB_PARTIAL'),
 ('P1','Turbine maps and head loss under changing water levels','Independent power output and unit availability reference','PLANNED'),
 ('P1','Reject violating dispatch and environmental constraints','Every rejected scenario explicitly cites binding rule','LAB_PARTIAL'),
 ('P1','Scenario economic comparison in appropriate market segment','Finance owner signs tariff and dispatch accounting assumptions','PLANNED'),
 ('P2','Multi-reservoir uncertainty robustness','Research stress scenarios and uncertainty bands reviewed','PLANNED'),
 ],
 'TURBINE':[
 ('P0','Verified machine and sensor configuration','Calibration, regime, repairs and event labels reconciled','PLANNED'),
 ('P1','Time-series anomalies stratified by operating regime','Control false alerts per unit hour and defects found','LAB_PARTIAL'),
 ('P1','Probabilistic defect model requires enough confirmed failures','Calibration check or explicit unknown probability','PLANNED'),
 ('P1','Maintenance alternative comparison with North logistics','Deliveries, downtime, spares, engineer signoff','LAB_PARTIAL'),
 ('P1','CMMS work orders and closed loop confirmation','Correct reference to source event and completed work','PLANNED'),
 ('P2','Fleet transfer evaluation','Hold out whole machine or station before generalized claims','PLANNED'),
 ],
 'GRID':[
 ('P0','Owner-signed feeder scheme and legal data release','Revision, phases, line and transformer parameters, meters','BLOCKED_NO_DATA'),
 ('P0','Independent multi-bus AC reference comparison','All nodal voltages, line currents and losses within pre-agreed tolerances','BLOCKED_NO_SOLVER'),
 ('P1','Seasonal actual interval model and calibration','Meter intervals complete; topology change and quality flagged','LAB_PARTIAL'),
 ('P1','Capex WBS and annual avoided cost valuations','Signed price basis, commissioning, tax and annual NPV','LAB_PARTIAL'),
 ('P1','Before after measurement and verification','Chronological holdout, uncertainty and authorized metrology','LAB_SYNTHETIC'),
 ('P2','Thermal and contingency screening','Technical safety validated separately from loss economics','PLANNED'),
 ],
 'HEAT':[
 ('P0','Signed heat supply and thermal network boundary','Source and network operator ownership, data sharing authorization','BLOCKED_NO_DATA'),
 ('P1','Thermohydraulic network solver integration','Pressure/flow/temperature agreed vs independent professional reference','PLANNED'),
 ('P1','Weather normalized thermal balance','Routine vs nonroutine adjustments and seasonal coverage','LAB_PARTIAL'),
 ('P1','Separate heat, pump power and fuel value attribution','No duplication in benefit registry and tariff economics','LAB_PARTIAL'),
 ('P1','Heating season intervention construction calendar','Restrictions, permits, commissioning and quality plan','PLANNED'),
 ('P2','Reliability of social services and alternatives','Obligatory reliability ranked before purely financial NPV','PLANNED'),
 ],
 'HYDROCAPEX':[
 ('P0','Project baseline and alternative version graph','No alternative without engineering source and owner','LAB_PARTIAL'),
 ('P0','Canonical all-module benefit ownership','Global exclusion + legacy migration and consolidation policy','LAB_PARTIAL'),
 ('P1','Verified WBS CBS and contract pricing','Quantities, unit costs, contingency, delivery origin','LAB_PARTIAL'),
 ('P1','Yearly cashflows and constraints','Correct nominal vs real, tax, tariffs and horizon','LAB_PARTIAL'),
 ('P1','North logistics evidence','Routes, seasonal windows and quotes linked to milestone','PLANNED'),
 ('P1','Construction drawings and permit evidence','Responsible professional and applicable document version','PLANNED'),
 ('P1','Approved commissioning -> post-MV evidence','Independent physically measured verification with uncertainty','LAB_SYNTHETIC'),
 ('P2','Capital portfolio optimization across projects','Mandatory/optional, dependency, exclusivity, budget verified','LAB_PARTIAL'),
 ],
}
for area,lines in by_area.items():
    for i,(p,req,acc,status) in enumerate(lines,1):
        add(area,i,p,req,acc,'Expert-reviewed artifact + automated tests',status,'Specialist+QA')

out=ROOT/'docs'/'V79_V8_ACCEPTANCE_BACKLOG.csv'
with out.open('w',newline='') as f:
    w=csv.writer(f);w.writerow(['id','area','priority','requirement','objective_acceptance','required_evidence','current_status','owner_candidate']);w.writerows(items)
print(out, 'data_rows=',len(items))
