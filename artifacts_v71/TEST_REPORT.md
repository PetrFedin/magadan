# V7.1 RC1: actual test report

Evidence date: 22 October 2026. This report separates executed code checks from unexecuted native/corporate acceptance.

## Final completed runs

| Group | Passed | Failures | Exit | Evidence |
|---|---:|---:|---:|---|
| V7 API regression A | 10 | 0 | 0 | local_server_a.txt / .xml |
| V7 API regression B (includes parametrized cases) | 22 | 0 | 0 | local_server_b.txt / .xml |
| V7.1 identity, audit, replay, schema and mathematical reference | 58 | 0 | 0 | local_components.txt / .xml |
| Inherited V6 JavaScript laboratory | 63 | 0 | 0 | legacy_v6_node_tests.txt |

Thus 90 Python + 63 JavaScript test cases passed. These are NOT 153 production controls, NOT an engineering certification, and NOT PostgreSQL acceptance. Eight of the Python cases are static DDL/schema checks, not actual database enforcement tests. The final reports have complete process exit statuses. Earlier partial/broad runs and first-failure logs are retained only as development history and are not counted.

## Actual networking tests

The component suite includes a complete authorization-code/S256-PKCE redirect, token exchange, JWKS verification, local session and logout over actual loopback HTTP against a synthetic IdP. It also includes real loopback HTTP delivery to an independent local-file audit receiver. These exercise HTTP transports, but NOT a corporate identity provider, actual employee MFA or protected external storage.

## Native PostgreSQL -- BLOCKED

20 native test functions are authored. They cover real roles, default deny, forged GUC context, tenant changes, transaction pool leakage, current membership/session revocation, cross-tenant inserts, TRUNCATE, role escalation, atomic audit/outbox rollback, append-only controls, exporter privileges, receipt authenticity, composite links, concurrent revisions and the seven-stage workflow. No native PostgreSQL test function was executed.

The mandatory-native invocation exits 2 during collection with NATIVE_ACCEPTANCE_BLOCKED when no dedicated PostgreSQL configuration exists. See native_required.txt. It must never be reported as a passing skip. The environment has no postgres server/driver or Docker; package downloads were unavailable, and the connected remote computer was offline. No other project database was used.

## Browser -- BLOCKED

The real Chromium attempt was skipped due ERR_BLOCKED_BY_ADMINISTRATOR. See browser_attempt.txt/.xml. No browser security restriction was bypassed. UI JavaScript syntax was checked with node --check; this is not live browser functional acceptance. Existing artifacts/ screenshots belong to V7 and must not be relabeled V7.1.

## Engineering reference

Ten synthetic balanced two-bus cases were compared against a separately initialized backward/forward implementation. Maximum absolute active-loss difference is 4.718293915295657e-10 MW, below the programmed 1e-8 MW cross-check tolerance. See engineering_comparison.json for each input, output and runtime/source fingerprint. This is a mathematical consistency check, not an accuracy statement for a real network in Magadan Oblast. No independent engineer signed any result.

## Storage

Local-file persistence, sequence conflicts, retries, signatures, content binding, body size and refusal to treat LAB_FILE as WORM were exercised. S3 COMPLIANCE behavior was checked only with an SDK contract fake. Actual versioning, retention shortening, overwrite/delete attempts, administrator behavior and external object storage have not been tested. PostgreSQL MAC-trigger rejection is written, not executed.

## Packaging/remaining acceptance

Python syntax/bytecode compilation, UI JS syntax, workflow YAML parse and OpenAPI generation were performed. Workflow YAML parsing does not mean the workflow ran. Dependency vulnerability scanning, reproducible image signing, backup/PITR restore, load testing, corporate SSO/MFA, real retention, certificate policy and field validation remain open.

The acceptance_summary.json is the machine-readable status. Documentation, a green component test or a workflow file must not be used to change production_ready=false.
