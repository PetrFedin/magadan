# HydroKontur 360 Magadan - release sequence, evidence and go/no-go criteria

## What V7.2 really ships

1. New `hydro_api.studies`: deterministic, bounded six-lane laboratory calculations with strict domain inputs and explicit caveats.
2. New `hydro_api.studies_api`: authenticated tenant-scoped create/list/detail/reproduce/compare, engine fingerprint, immutable study persistence, OpenAPI schema exposure.
3. SQLite synthetic lab table with append-only guards. PostgreSQL migration 060 with forced RLS, per-tenant policies, composite asset FK, audit trigger and immutable rows.
4. A new studies workspace integrated into the existing server-served UI. Synthetic examples are static and public; authenticated actions remain on server.
5. Model and security tests + constrained portfolio optimization test cases.
6. Design dossiers for site selection, finance, construction, legal traceability and enterprise integration.

## Do not infer from V7.2

- No existing RusHydro application has been modified or deployed.
- No industrial feeder has been modelled or measured.
- No external grid/heat/hydrology solver is integrated in production.
- No independent engineer has certified the model.
- No actual PostgreSQL native RLS test has run in this environment.
- No real corporate IdP or external WORM proof has been supplied.
- No approved financial business case or construction estimate exists for Magadan sites.

## V7.3 P0 - infrastructure safety and native proof

- Run the 001-060 migrations in a new, dedicated PostgreSQL 17 instance. Verify all RLS functions, transaction pooling, context revocation, cross-tenant role exceptions, read/write isolation and audit triggers with full native tests. Record database version and SQL migration checksums.
- Deploy a separate receiver with approved versioned Object Lock and evidence of actual retention enforcement. Restore a backup and verify receipt chain independently.
- Integrate a real corporate OIDC issuer subject to sponsor-approved policies and MFA; test role revocation, cross-organization access, CSRF and session expiry.
- Run actual browser E2E in permitted network/container where localhost is allowed. Test login, six studies, model review, full V7 initiative lifecycle and mobile layout.
- Generate source-level SBOM and dependency vulnerability review, adjust threat model and incident runbook; no external exposure until signed.

## V7.4 P0 - engineering pilot rights and baseline

- Secure written participation from at least one legitimate Magadan grid data owner and establish an approved data processing perimeter.
- Independently reconcile measurements, topology and original operating regime against an accepted reference model. Pre-register tolerances.
- Add bounded multi-bus AC (including transformers, topology versions and approved equipment characteristics) without any operational control endpoints.
- Require independent third-party report; if comparison fails, model remains in exploratory state.

## V7.5 P1 - investment evidence and outcome

- Crosswalk engineering study -> versioned evidence -> independent approval -> investment alternatives -> lifecycle cost -> post-project verification. Never permit a synthetic laboratory run to become a certified engineering report without explicit review and an approved field-data workflow.
- Budget/WBS/CBS binding, sensitivity analysis, northern logistics data and regulatory completeness gates.
- Export self-contained decisions with original data hashes, validated calculation, assumptions, signatories, statutory constraints and audit receipts.

## V8 P1/P2 - broaden scientifically validated domain coverage

- HydroForecast: actual basin model + ensembles, independent calibration and drought/flood stress tests.
- Cascade: physical water routing and operator rules with unit-level characteristics.
- Turbine: OEM-grade signal pipeline, defect ontology, credible model validation and EAM connection.
- HeatNet: true hydraulic and heat-exchange network solver, expert review and comparable weather baseline.
- HydroCAPEX: incumbent enterprise finance integration, cost/contract authoritativeness, BIM and signed post-action economics.

## Decision requested for earliest external meeting

A technical-discovery session and controlled data readiness survey, not immediate grant or full-build funding. Define the operator and source-of-truth for a bounded asset, obtain an independent technical reviewer and compare the incumbent workflows on identical evidence.

## Quality evidence to preserve

`artifacts_v72/` reports, `docs/openapi_v72.json`, migration and schema checks, module fixtures, source SHA-256, and every explicit HOLD status. Do not turn a static HTML screenshot into a browser E2E claim. Do not count PostgreSQL static SQL lint as native RLS pass.
