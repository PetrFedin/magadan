# HydroKontur 360 - Magadan | V7.2 Master System Design

**Date:** 2026-10-23. **Status:** Laboratory engineering demonstrator. Production HOLD.
**Account:** Potential RusHydro group partners; no approved partnership, access, procurement or field data established.

## 1. Decision purpose and project boundary

The system aims to improve reproducibility of the chain: observed condition -> technical study -> admissible options -> financial consequences -> approval -> execution -> verified outcome. It MUST NOT issue SCADA, relay protection, gate, generator or heat-network control commands. It MUST NOT claim that a synthetic study is field-validated.

Product and responsibility boundaries are separate:

- HydroForecast: historical forecast quality, provenance and future ensemble verification.
- CascadeEconomics: constraint-bound basin/cascade scenarios; not a dispatcher.
- TurbineReliability: condition anomalies and maintenance options; not certified machine protection.
- GridLoss Planner: model-based network analysis; not switching/protection dispatch.
- HeatNet Economics: thermohydraulic models; not a pressure or temperature setpoint controller.
- HydroCAPEX: engineering evidence tied to investment options; not a replacement for ERP/official capital approvals.

## 2. Target trust architecture

```
User browser / read-only visualization
        |
Authenticated API / OIDC session / CSRF and authorization
        |
Tenant boundary + role check + PostgreSQL RLS (not yet native-tested)
        |
+------------------------+-------------------------+
| Evidence and documents | Six synthetic studies   |
| source hash and review | immutable versions      |
+------------------------+-------------------------+
        |                           |
Verified grid run -> V7 investment process     No production-promotion edge
        |                           |
Traceable outcome dossier              exploratory comparison only
        |
Transactional audit outbox -> independent signed receipt (lab adapter only)
```

PostgreSQL RLS is designed to bind context to server sessions and database transactions, with FORCE RLS on per-tenant tables. Real DB acceptance and independent backup/restore are NOT complete. OIDC is tested against a synthetic provider, not a corporate IdP. External retention adapter does not establish WORM compliance absent deployed, verified retention policies.

## 3. Versions and authoritative truth

- V6 contains a standalone JavaScript laboratory model and 63 legacy tests.
- V7 adds a server-side grid benchmark and governed investment state machine.
- V7.1 adds OIDC integration protocol, SQL migrations, outbox/receipts and calculation reproduction.
- V7.2 adds immutable six-lane *synthetic* studies using an existing server identity boundary. Study runs cannot be promoted to investment evidence; the separate V7 regulated pipeline remains restricted to its reviewed grid calculation.

Every V7.2 study stores tenant, asset, source reference, scenario tag, input JSON, input SHA-256, result JSON, result SHA-256, engine source hash, author and timestamp. The scenario tag is NOT a proof of equivalent conditions. A study can be reproduced only with the pinned engine source; otherwise a new reviewed version is needed.

## 4. Tenant and data security

All V7.2 `/studies` reads first evaluate active membership against the organization in the path. Write access: engineer for the first five domains; economist for HydroCAPEX. Auditor/engineer can reproduce; viewer can only read synthetic studies. The API does not use a client-selected role as a source of authority.

The `study_runs` table is append-only in SQLite lab via triggers and is specified to be append-only under PostgreSQL via `060_studies_v72.sql`. This is not protection against the owner/host administrator. Native RLS, external WORM and restore testing are separate release gates.

## 5. Data contract

Mandatory study envelope: `asset_id`, `module`, `source_ref`, `scenario_group`, `case`, `scope`.
`source_ref` must start with `SYNTHETIC-`; scope is fixed to `SYNTHETIC_LAB_ONLY`. Requests with unsupported modules, invalid units, missing fields, inconsistent periods, non-finite numbers or oversized payloads are rejected.

Every domain model has a strict Pydantic schema available through `GET /v72/meta/modules/{module}/schema`. Units are explicit; no silent zero-filling, automatic unit conversion or undocumented imputation.

Future field data requirements: data provenance and ownership; observed and available timestamps; unit and calibration details; measurement chain; topology version; data quality; regulatory/data handling classification; approval to process; field engineer signoff.

## 6. Domain-specific model baselines

| Domain | What V7.2 actually computes | Not yet computed |
| --- | --- | --- |
| HydroForecast | Retrospective MAE, RMSE, bias, WAPE, interval coverage; timeline leakage gate | Live weather and hydrology forecasting, probabilistic calibration, out-of-sample basin forecasts |
| CascadeEconomics | Two idealized reservoirs, one time step, mass balance and power approximation | Routing, operating regulations, travel time, turbine curves, multi-season optimization |
| TurbineReliability | Median/MAD anomaly at comparable operating load; uncertainty reported | Failure probabilities, OEM defect diagnoses, validated RUL, work orders |
| GridLoss | Two-bus balanced PQ AC loss | Multi-bus calibration, unbalance, equipment limits, N-1, switching proposals |
| HeatNet | Lumped heat transfer and pipe-loss estimate | Full network hydraulic solver, pressure boundaries, transient temperatures, ZuluThermo parity |
| HydroCAPEX | Decimal NPV, mandatory/dependent/exclusive portfolio and annual budget gates | Full ERP/EPM integration, tariff normalization, inflation, taxes, risk simulation, WBS/BIM4D |

## 7. Magadan-first empirical scope

Proposed—not approved—reference candidates: Kolyma cascade assets (hydrological, hydroelectric, diagnostics); authorized grid fragment of an applicable regional network operator; approved heat-network section near Magadan; bounded investment dossier set. Real equipment availability, water management rules, line parameters, maintenance histories, network ownership and project data must come from lawful agreements and verified source documents.

For grid field pilot, require single-line diagram and effective date, node and feeder identifiers, instrument registry/calibration, synchronized P/Q/V measurements, loading timeline, loss balance, independent reference solver, engineering specialist review, financial baseline, written permissions and data access classification. A map of Magadan alone is never engineering evidence.

## 8. Workflow and signoffs

Engineering author and reviewer must be different when evidence requires independent review. A manager must not sign as engineering reviewer by role switching in the browser. Investment approval needs a reviewed engineering report, independent reviewed financial document and approval memorandum in the prescribed sequence; the V7 pipeline also records execution and outcome evidence. These remain distinct from corporate legal authorization to spend funds.

New V7.2 studies are explicitly blocked from the V7 initiative creation because they are not `calculation_runs` and lack the independent engineering signoff pipeline.

## 9. Cybersecurity and operations

Production requires corporate IdP integration with MFA policy, approved domestic/regional hosting, backup/restore rehearsals, independent audit retention, monitoring, explicit network boundary, vulnerability management, data classification, secrets lifecycle, incident response, business continuity and an owner-approved threat model. All processing must remain read-only with respect to operational technology.

## 10. Stage-gate definition of done

G0 Scope: written sponsorship, asset and data owners, purpose, authorized studies.
G1 Data: completeness, calibrated records, rights to use, field engineer review.
G2 Mathematics: external specialist independently reproduces benchmark cases and defines tolerances before seeing results.
G3 Cyber: RLS native runs, tenant attack tests, SSO, audit WORM and restore drills.
G4 Economics: finance signs true counterfactual and methodology; no double-counted benefits.
G5 Trial: offline parallel-run against existing production practices, without operational commands.
G6 Investment: actual approvers, budget source and procurement/legal approvals.
G7 Outcome: independently measured fact, documented variance and model revision.

Release to industrial pilot is BLOCKED until G0-G4 are signed; deployment as decision support additionally requires G5 and customer authorization. Unsuccessful tests must remain visible and prevent status promotion.

## 11. Competitor parity check targets

GridLoss must be benchmarked against an authorized reference solver (RastrWin3, PowerFactory or similarly accepted solution). HeatNet must be benchmarked with a validated thermohydraulic tool such as ZuluThermo where authorized. Maintenance process integration requires the actual EAM/CMMS contract; HydroCAPEX must interface with incumbent EPM/ERP rather than recreate a competing source of truth. Compare functions on identical engineering inputs and documented settings; no unsupported assertion of superiority.

Reference sources to revisit: [PostgreSQL RLS](https://www.postgresql.org/docs/17/ddl-rowsecurity.html); [OIDC Core](https://openid.net/specs/openid-connect-core-1_0.html); [OWASP Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html); [HEC-ResSim](https://www.hec.usace.army.mil/software/hec-ressim/features.aspx); [ZuluThermo](https://www.politerm.com/products/thermo/zuluthermo/).
