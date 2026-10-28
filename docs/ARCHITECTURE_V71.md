# HydroKontur 360 - Magadan: V7.1 architecture and trust boundaries

Status: implementation candidate; not commissioned. Read TEST_REPORT for executed vs blocked tests. This document describes the implemented design and its remaining proof obligations. A diagram or migration file is not evidence that native RLS has run.

## 1. Scope and preserved baseline

The working copy is derived from the supplied V7 archive. V7 engineering/approval APIs retain `/v7` for compatibility; OIDC, delivery readiness and calculation reproduction add `/v71` routes. V6 six-module client and original deliverables are retained as legacy reference materials, not newly server-integrated modules. The server-side engineering path remains the synthetic balanced two-bus electrical case. No new SCADA controls, real asset parameters, construction commands or corporate integrations are introduced.

Five separately trusted components are required: browser, API, identity adapter, PostgreSQL security functions, independent audit receiver/storage. In this laboratory the API and identity adapter share a process but use separate database roles. Process compromise therefore crosses that boundary; production requires a separate identity service/process and reviewed secrets distribution. No claim is made to protect against a fully compromised application plus its authenticator credential.

## 2. Request and identity lifecycle

1. `/v71/auth/start` stores a hashed state and browser-binding value, nonce and S256 verifier with a five-minute lifetime.
2. The fixed discovery issuer and approved endpoint origins are checked. The authorization request includes PKCE, nonce, max_age and the configured assurance class.
3. Callback atomically consumes the transaction only for its bound browser. An authorization code is exchanged by the server, never by browser JavaScript.
4. RS256/JWKS, issuer, audience, authorized party where applicable, nonce, auth_time, expiry and configured ACR are validated. Only RSA keys of adequate size and pinned discovery origins are used. Tokens with remote jku/x5u headers are rejected.
5. The pre-provisioned `(issuer, subject)` mapping resolves the local user. Email, claimed admin roles or a browser org_id do not provision access.
6. The browser receives an opaque random session in an HttpOnly cookie. For HTTPS, __Host- naming, Secure and SameSite=Lax are used. A separate CSRF token plus exact Origin is required on cookie-authenticated writes.
7. AuthStore verifies expiry, revocation, user activation and token_version. Membership/role are re-read, not cached as authoritative token claims. Logout revokes this application session; it is not a global corporate logout.

No actual employee MFA ceremony was performed. The local synthetic IdP issues an explicitly simulated ACR. Corporate registration, real MFA policy mapping, certificate chain, logout events, deprovisioning feed, key rotation exercise, rate limiting and identity-service availability must be accepted separately. Only configured HTTPS providers are allowed outside explicit loopback laboratory mode.

## 3. PostgreSQL security model

The six SQL migrations target an EMPTY dedicated PostgreSQL 17 database. They have not been executed in this environment. The runtime never creates tables and refuses an owner, superuser or BYPASSRLS role.

| Role | Permission boundary |
|---|---|
| hk_owner | NOLOGIN owner of schemas/tables/security functions; bootstrap only, never API connection |
| hk_app | RLS-constrained business reads/writes and approved security functions; cannot alter policy, role or schema |
| hk_authenticator | OIDC transactions and sessions; reads only pre-provisioned identity mappings and the minimal user activation/version fields |
| hk_exporter | Reads audit/outbox records and inserts authenticated receipts; updates bounded delivery metadata only; cannot edit engineering data |

All public business/audit tables have ENABLE and FORCE RLS. Private auth/key tables are protected by schema privileges, not falsely advertised as tenant RLS tables. Each owner SECURITY DEFINER function has a fixed pg_catalog search_path, fully-qualified object names and revoked PUBLIC execution. Owner policies intentionally permit the internal definer functions to inspect their required rows. A superuser can bypass RLS and is outside the application boundary.

`bind_session(raw_token, org)` validates the hash of the opaque session, current user version, expiry/revocation and membership. It signs `(actor, org, session hash, transaction id, backend pid)` with a database-private HMAC key and sets transaction-local context. Policies verify the signature and session again. Setting only org_id or actor variables cannot create a valid context. A copied signature from a different transaction or pooled connection is invalid.

Reads and writes use explicit USING/WITH CHECK policies. Composite foreign keys join org_id and asset_id to evidence/model/run links, preventing cross-tenant or wrong-asset attachment. Single-review and transition-revision uniqueness constrain races. TRUNCATE, owner membership, CREATE and BYPASSRLS are not granted. Financial/engineering/manager roles remain separate from SQL connection roles.

Proof still required: execute all migrations, inspect catalog grants, run adversarial direct SQL and concurrent transactions, verify pool reuse, real revocation, backup/restore and a full seven-stage workflow. Static DDL string tests and SQLAlchemy compilation do not prove any of this.

## 4. Workflow invariants and versioning

The workflow remains draft -> engineering_review -> financial_review -> approval_pending -> approved -> in_execution -> verification_pending -> verified. Expected revision, actor role, independent reviewer, required accepted evidence, same org/asset/run and unchanged baseline are checked. SQL triggers repeat these constraints for native deployments rather than relying solely on HTTP code. Caller-supplied approver IDs are rejected.

The source of a calculation, model parameters, result hash, algorithm source digest and Python/SciPy/NumPy versions are pinned. A source or runtime change requires a NEW reviewed model/run rather than silently regenerating an old result. `/v71/orgs/{org_id}/runs/{run_id}/reproduce` allows an engineer or auditor to re-run, compare the result, perform a separately initialized mathematical reference check, and append an audit event.

This is not a reproducible container image or software supply-chain attestation yet. Final production provenance must include a locked dependency graph, signed image digest, build record, approved solver/version and machine precision rules. The source digest currently covers main.py and engineering.py, not every transitive dependency. Reproduction itself creates an event that requires later external sealing.

## 5. Transactional audit and independent receipts

A database trigger appends a business-change event and an outbox row in the SAME transaction. Per-organization head locking serializes the hash chain. Rollback must remove the business change, event and outbox row together. API-level semantic events complement the automatic row-change audit; two events describing one operation are not two financial effects.

The exporter claims one eligible event per organization with FOR UPDATE SKIP LOCKED, respects sequence ordering and uses bounded retry delays. A transaction currently holds the claimed queue row during a bounded HTTP request. This is deliberately simple for the pilot, not a high-throughput claim; production must load-test lease-based delivery and backlog behavior.

The independent receiver persists first, then signs a receipt. The Ed25519-signed body includes event/org/sequence, full sealed event, event hash, canonical envelope digest, exact object key and version ID, storage mode and retain-until time. The exporter pins the public key and checks every binding. Transport credentials do not authorize deletion.

A separate database receipt MAC key is shared ONLY by the receiver and a private PostgreSQL function. The exporter does not hold it. The BEFORE INSERT trigger validates the MAC over exact raw bytes, checks the parsed body and reconstructs the event binding from the database. Exporter SQL credentials alone therefore cannot set a successful receipt. Native enforcement of this design is still unexecuted.

Two storage implementations are deliberately distinct:
- LAB_FILE: a different process/directory, atomic application-level write-once behavior and retry idempotency. Host administrators can alter or remove files. This is NOT WORM.
- S3 COMPLIANCE adapter: requires an approved endpoint, versioning, Object Lock, conditional write, content checksum, pinned version ID and retention readback. Only an SDK contract fake was tested. No real S3 bucket or WORM service was used.

Production policy requires COMPLIANCE receipts by default. Before approval, execution or final verification, preceding events must be externally sealed and identity authentication must be recent. The NEW transition produces NEW pending audit records. Business state is not the same as archival state: dossier.assurance exposes that distinction. An approved/verified label must not be exported as externally archived until its receipt arrives.

The present gate is organization-wide, conservative and potentially blocking under heavy concurrent workloads. Per-dossier sealed checkpoints are a later optimization requiring separate invariants and tests. Expired retention, unavailable receiver or invalid receipts fail closed for protected transitions; this has no authority over the actual operation of an energy asset.

Threat limits: database superusers, receiver host operators or stolen receiver signing/MAC keys remain privileged trust boundaries. HMAC/Ed25519 receipts are technical evidence, not a qualified legal electronic signature. Old receipts need a key-retention/rotation policy. Storage retention must be approved by records management; 30 days in the example is not a legal requirement.

## 6. Failures, observability and operations

| Failure | Required behavior |
|---|---|
| Identity provider unavailable | No new verified login; no local-password bypass in OIDC profile |
| Expired/revoked session | Deny; reauthenticate through provider |
| Wrong org/asset or forged transaction context | Deny; no silent cross-tenant lookup |
| Stale revision | Conflict; caller reloads approved state |
| Changed input/model/runtime/result hash | Reject reproduction/transition; create a reviewed new version |
| Receiver offline | Persist outbox; retry; protected transition waits |
| Response lost after remote write | Retry identical event; stable receipt without duplicate effect |
| Bad receipt signature/version/retention/MAC | No acknowledgment, no external-seal claim |
| Native database absent | Native required suite FAILS rather than skipping to green |

Operational work not yet accepted: backup/PITR restore, real TLS reverse proxy and ingress body/rate limits, corporate CA/egress allowlisting, deployment secrets vault, signing-key rotation, SIEM delivery, service monitoring, alert routing, disaster recovery objectives, external penetration test, high load and dependency vulnerability review. Login success/failure security events currently need a dedicated identity audit stream; the tenant business audit is not a substitute.

## 7. Scientific boundary for Magadan Oblast

The engineering model is one ideal slack source, one balanced three-phase series R+jX line and one constant-PQ consumer. It omits shunts, multiphase unbalance, transformers/taps, topology switching, N-1, harmonics, relay protection and dynamics. The independently initialized backward/forward implementation is an internal mathematical cross-check, not external engineering validation.

No actual feeder, grid topology, coordinates, operating measurements or owner permission from Magadan Oblast is present. Every current dataset/model is laboratory-only. A future real-data import needs a separate reviewed adapter, owner authorization, a defined study boundary and an independent expert; current LAB_REFERENCE gates must not be bypassed.

## 8. Design references

- PostgreSQL 17 row security: https://www.postgresql.org/docs/17/ddl-rowsecurity.html (FORCE, owner bypass, superuser and whole-table privilege limitations).
- OpenID Connect Core: https://openid.net/specs/openid-connect-core-1_0.html (code flow, issuer/audience/nonce/auth_time validation).
- OAuth security BCP, RFC 9700: https://www.rfc-editor.org/rfc/rfc9700.html (PKCE and authorization security).
- Object Lock semantics: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html (version-scoped retention and COMPLIANCE). Protocol reference only; not a decision to use AWS for Russian energy data.
