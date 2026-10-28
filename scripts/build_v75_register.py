#!/usr/bin/env python3
"""Extends V7.4 traceability without rewriting historical rows/statuses."""
from pathlib import Path
import csv
root=Path(__file__).resolve().parents[1]
base=root/'docs/V74_FEATURE_REGISTER.csv'
target=root/'docs/V75_FEATURE_REGISTER.csv'
rows=list(csv.DictReader(base.open()))
entries=[
 ('Core','Server-validated source asset and organization for handoff','P0','LAB_IMPLEMENTED','server/tests_v75/test_handoff_api.py'),
 ('Core','Role engineer required for synthetic handoff creation','P0','LAB_IMPLEMENTED','server/tests_v75/test_handoff_api.py'),
 ('Core','Append-only research handoff row in SQLite','P0','LAB_IMPLEMENTED','server/tests_v75/test_handoff_api.py'),
 ('Core','Input, result, engine and parent programme source pins','P0','LAB_IMPLEMENTED','server/tests_v75/test_handoff_api.py'),
 ('Core','Research handoff idempotency and duplicate rejection','P0','LAB_IMPLEMENTED','server/tests_v75/test_handoff_api.py'),
 ('Core','Parent programme membership enforced on linked study ids','P0','LAB_IMPLEMENTED','server/tests_v75/test_handoff_api.py'),
 ('Core','PostgreSQL 17 RLS migration 090 native acceptance','P0','DESIGNED_UNACCEPTED','server/migrations/090_calculation_handoffs_v75.sql'),
 ('Core','Genuine corporate OIDC/MFA identity integration','P0','BLOCKED_NOT_CONNECTED','docs/V75_NATIVE_SECURITY_RUNBOOK_RU.md'),
 ('Core','External compliant retention and audit anchoring','P0','BLOCKED_NOT_CONNECTED','docs/V75_NATIVE_SECURITY_RUNBOOK_RU.md'),
 ('HydroForecast','Hindcast prediction-only transfer independent of observed actual','P0','LAB_IMPLEMENTED','server/tests_v75/test_domain_coupling.py'),
 ('HydroForecast','Explicit timezone aware contiguous target timeline','P0','LAB_IMPLEMENTED','server/tests_v75/test_domain_coupling.py'),
 ('HydroForecast','Quantile lower, point and upper sensitivity variants','P1','LAB_IMPLEMENTED','server/tests_v75/test_domain_coupling.py'),
 ('HydroForecast','Source catchment mapping identifier and physical units m3/s','P0','LAB_IMPLEMENTED','server/hydro_api/coupling_v75.py'),
 ('CascadeEconomics','Hourly step agreement and delayed-arrival history gate','P0','LAB_IMPLEMENTED','server/tests_v75/test_domain_coupling.py'),
 ('CascadeEconomics','Mass balance, reservoir constraints and energy per timestep','P0','LAB_IMPLEMENTED','server/tests_v75/test_domain_coupling.py'),
 ('CascadeEconomics','Verified real cascade characteristic curves and transit routing','P0','BLOCKED_FIELD_DATA','docs/V75_MAGADAN_FIELD_READINESS_RU.md'),
 ('TurbineReliability','Diagnostic anomaly not translated into failure probability','P0','LAB_IMPLEMENTED','server/tests_v75/test_domain_coupling.py'),
 ('TurbineReliability','Alternative inspection/repair direct cost and logistics','P1','LAB_IMPLEMENTED','server/tests_v75/test_domain_coupling.py'),
 ('TurbineReliability','Explicit unknown downtime-risk and no automatic recommendation','P0','LAB_IMPLEMENTED','server/tests_v75/test_domain_coupling.py'),
 ('TurbineReliability','Calibrated probability from authenticated defect history','P1','BLOCKED_FIELD_DATA','docs/V75_MAGADAN_FIELD_READINESS_RU.md'),
 ('HydroCAPEX','Research programme linkage with parent SHA and reproducibility','P0','LAB_IMPLEMENTED','server/tests_v75/test_handoff_api.py'),
 ('HydroCAPEX','Independent finance approval of maintenance cost vs actual project','P0','PLANNED','docs/V75_DEEP_ARCHITECTURE_RU.md'),
 ('HydroCAPEX','Automatic multi-project WBS reconciliation for maintenance bridge','P1','PLANNED','docs/V75_DEEP_ARCHITECTURE_RU.md'),
 ('UX','New server-backed synthetic handoff workspace','P1','LAB_IMPLEMENTED','server/ui/index.html'),
 ('UX','Full authenticated Chromium network E2E acceptance','P0','BLOCKED_NOT_ACCEPTED','docs/V75_NATIVE_SECURITY_RUNBOOK_RU.md'),
 ('Magadan','Authorized engineering dataset and expert acceptance','P0','BLOCKED_FIELD_DATA','docs/V75_MAGADAN_FIELD_READINESS_RU.md'),
]
for i,(mod,req,pri,status,proof) in enumerate(entries,1):
    rows.append({'id':f'HK75-{i:03d}','module':mod,'requirement':req,'priority':pri,
                 'implementation_status':status,'proof_or_gap':proof,'production_accepted':'NO'})
with target.open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['id','module','requirement','priority','implementation_status','proof_or_gap','production_accepted'])
    w.writeheader();w.writerows(rows)
from collections import Counter
print('base',len(rows)-len(entries),'added',len(entries),'total',len(rows),'status',dict(Counter(r['implementation_status'] for r in rows)))
assert not any(r['production_accepted']!='NO' for r in rows)
