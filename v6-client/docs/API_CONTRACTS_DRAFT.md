# Proposed API contracts / V5 draft, not implemented

## Design guardrails

- **Analytical, read-only input ingestion**, without controls that can write commands into turbines, protection systems, SCADA or dispatcher networks.
- Corporate asset master keys `(organization_id, asset_id, valid_from, version)` with stable IDs and no implicit cross-company data merge.
- Every modeled value carries `source_id`, `time_range`, `unit`, `quality_flag`, `model_version`, `input_snapshot_id`, `computed_at`, and the digest of the calculation inputs.
- Historical forecasts must store when they were issued; ex-post evaluation cannot use measurements that were not known on that issue date.
- Server-side RBAC and entity scope checks on **every** read and write, plus database row-level security or equivalent.
- Immutable event storage (WORM/object lock or cryptographically anchored append-only event store) verified externally; no client-calculated audit proof alone.
- Data fields classified and retained according to client policy and applicable Russian law; no public exposure of plant-internal layouts or operational parameters.

## Proposed endpoints (NOT RUNNING)

| Path | Method | Essential rules | Returns |
|---|---|---|---|
| `/v1/orgs/{orgId}/assets` | GET | Server-auth scope | Paged assets and data-quality labels |
| `/v1/assets/{assetId}/measurements:ingest` | POST | Authorized ingest role; schema+unit validation; original preserved | Batch ID, accepted/rejected count and reasons |
| `/v1/models/{modelId}/evaluate` | POST | Approved dataset snapshot, time-based split, no future leakage | Versioned backtest and uncertainty metrics |
| `/v1/assets/{assetId}/scenarios` | POST | Verified versioned physical constraints | Scenario ID; `admissible=false` + traceable reasons as required |
| `/v1/initiatives` | POST | Data provenance; confirmed org/asset/module | Draft initiative ID and evidence links |
| `/v1/initiatives/{id}/transition` | POST | Server-side authorization + stage evidence + optimistic concurrency | Updated version; immutable audit event |
| `/v1/benefits/reconcile` | POST | Verified benefit IDs; no duplicates; no conflicts included in totals | Portfolio amount + uncertainty and excluded cases |
| `/v1/projects/{id}/actuals` | POST | Authoritative ERP identifiers; preserve original budget | Plan/fact and immutable revision |
| `/v1/projects/{id}/outcomes` | POST | Independent auditor; common baseline and weather/load normalization | Verified effect or explicitly unverified |
| `/v1/audit/export` | GET | Auditor scope, signed/anchored evidence set | Reproducible evidence dossier |

## Event contract

`event_id`, `organization_id`, `entity_type`, `entity_id`, `event_type`, `actor_id`, `role_id`, `event_at`, `previous_revision`, `new_revision`, `source_evidence_ids[]`, `hash_algorithm`, `content_digest`, `storage_receipt`.

## Decision state machine

`draft → engineering_review → financial_review → approval_pending → approved → in_execution → verification_pending → verified`, plus permitted rejection/correction transitions. No bypass, including system administrators. Every approval is linked to real authority and specific immutable document/version. Mandatory safety projects have separately governed decisions, not automatically rejected for negative NPV.

## Acceptance gates

Must pass unit/e2e + unauthorized API tests; input schema mutation; double-count benefit conflict; time leak on forecast; boundary and degenerate physical cases; negative balance; audit tamper; quality gates for actual field data; full historical backtesting and independent engineering validation. Contracts should be approved by security, engineer and finance representatives before implementation.
