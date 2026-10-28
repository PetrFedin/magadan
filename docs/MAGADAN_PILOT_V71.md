# Magadan Oblast electrical pilot: required evidence and acceptance gates

Status: NOT OPENED. No specific feeder has been selected or authorized. No real operator has supplied data or appointed an independent engineer. The software cannot authorize a physical test, construction activity or operating change.

## 1. Data/permission package

Each item needs owner, document ID/version/hash, authorized scope, period, confidentiality, allowed users, retention and reviewer: (a) asset ownership and consent; (b) actual topology/version and measurement boundary; (c) line/transformer verified parameters and units; (d) metering IDs, intervals, calibration/accuracy and acquisition timestamps; (e) operating/topology event log; (f) load profiles and power factor/reactive data; (g) known data gaps/corrections; (h) applicable technical constraints; (i) independent benchmark model/solver/license; (j) agreed financial cost methodology and base period.

No data from maps, marketing material or another territory may be substituted for an owner's operating diagram. Raw technical topology and confidential measurements must remain in the approved contour and must not be added to a public repository.

## 2. Method boundary

The present two-bus solver can validate a simple mathematical equivalent only after the engineer explicitly accepts that reduction. It cannot represent an arbitrary Magadan feeder. For a real multi-node case, use an approved solver adapter with independently checked topology, transformers, voltage levels, load/time-series and numerical convergence controls. No relay settings, operating commands or switch actions are generated.

## 3. Independent benchmark protocol

Freeze the dataset, topology, model and solver versions BEFORE comparison. Define admissible mismatch by measured uncertainty and engineering purpose; do not select thresholds after seeing the result. Compare nodal voltage, active/reactive branch flow, technical losses, nodal and total balance, convergence and constraint violations. Identify missing sensitivity cases; compare at least the agreed normal and adverse cases, not just one easy point. Include invalid units, stale topology and missing measurements as refusal tests.

An expert must examine the model assumptions and sign the report with actual name, qualification/authority, date, scope and reservations. A user clicking an auditor role, a synthetic signed_document_ref or an Ed25519 storage receipt is not such a professional conclusion.

## 4. Engineering to investment evidence chain

Authorized dataset -> accepted model -> reproducible calculation -> independent engineering report -> valid alternative -> separate financial review -> competent authority decision -> actual execution evidence -> like-for-like outcome evaluation -> externally sealed dossier.

Financial analysis must distinguish physical kWh, economic resource cost, tariff/accounting effect and actual cash savings. Keep CAPEX, software cost, integration, annual operation, taxes, funding and discounting assumptions explicit. Avoid duplicate benefit attribution across software modules or intercompany flows. The current laboratory NPV is synthetic, not a RusHydro budget.

## 5. Opening gates

G1: native PostgreSQL isolation, transaction and restore acceptance.
G2: actual corporate identity/MFA and authority mapping.
G3: real independent archival retention and signed receipt acceptance.
G4: owner-authorized dataset and approved limited purpose.
G5: separately signed independent technical benchmark.
G6: economic methodology and practical pilot acceptance by the competent owner.

All six are external gates; none is marked complete merely because this document or source code exists. The other five analytical products remain in their prior laboratory/requirements status; this release does not silently port their models into the PostgreSQL server.
