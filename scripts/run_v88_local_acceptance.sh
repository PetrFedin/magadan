#!/usr/bin/env bash
# V8.8 source-pinned local SYNTHETIC regional energy admission (not production).
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
SHA="${1:-}"
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]] || [[ "$(git rev-parse HEAD)" != "$SHA" ]]; then
  echo "V88_HOLD_EXACT_GIT_HEAD_REQUIRED" >&2; exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "V88_HOLD_DIRTY_TREE" >&2;git status --short >&2;exit 2
fi
: "${HYDRO_NATIVE_CONFIG:?V88_HOLD_NATIVE_PG17_REQUIRED}"
: "${HYDRO_BROWSER_EXECUTABLE:?V88_HOLD_REAL_CHROMIUM_REQUIRED}"
test -s "$HYDRO_NATIVE_CONFIG" && test -x "$HYDRO_BROWSER_EXECUTABLE"
PY="$ROOT/.venv/bin/python"
test -x "$PY"
OUT="$ROOT/runtime/qa-v88-$SHA"
umask 077
mkdir -p "$OUT"
export PYTHONPATH="$ROOT/server"
export HYDRO_NATIVE_TESTS_REQUIRED=1
export HYDRO_BROWSER_EVIDENCE_DIR="$OUT/browser"

# Same PostgreSQL17: real synthetic OIDC sessions, RLS native checks,
# real browser and authenticated restoration smoke.
bash scripts/run_v87_local_acceptance.sh "$SHA" > "$OUT/v87-unified.log" 2>&1
test -s "$ROOT/runtime/qa-v87-$SHA/acceptance-receipt.json"
echo "V88_REAL_PG17_OIDC_BROWSERS_RECOVERY_PASS"

"$PY" -m pytest -q -ra -o xfail_strict=true --maxfail=1 \
  server/tests_v71 server/tests_v72 server/tests_v73 server/tests_v74 \
  server/tests_v75 server/tests_v76 server/tests_v77 server/tests_v78 \
  server/tests_v79 server/tests_v8 server/tests_v81 server/tests_v82 \
  server/tests_v83 server/tests_v85 server/tests_v88 server/tests \
  --ignore=server/tests_v71/test_postgres_native.py \
  --ignore=server/tests_v78/test_postgres_native_v78.py \
  --ignore=server/tests_v8/test_postgres_native_boundary_v8.py \
  --ignore=server/tests_v81/test_pg_graph_freeze_native_v81.py \
  --ignore=server/tests/test_browser.py \
  --junitxml="$OUT/monolithic.xml" > "$OUT/monolithic.log" 2>&1
"$PY" scripts/v84_junit_gate.py \
  --junit "$OUT/monolithic.xml" --shard v88-all-python-single-process \
  --min-passed 404 --max-skipped 0 \
  --actual-sha "$SHA" --expected-sha "$SHA" \
  --require-case test_deficit_and_coincident_peak_are_separate_and_never_dispatch \
  --require-case test_http_roles_tenants_deterministic_proof_and_immutability \
  --require-case test_local_seed_runs_from_empty_database_and_refuses_second_seed \
  > "$OUT/monolithic-gate.json"
echo "V88_MONOLITHIC_404_PASS"

node --check server/ui/ui.js > "$OUT/ui-js-syntax.log" 2>&1
npm test --prefix v6-client > "$OUT/javascript.log" 2>&1
grep -q '^# pass 63$' "$OUT/javascript.log"
grep -q '^# fail 0$' "$OUT/javascript.log"
"$PY" -m unittest discover -s scripts/tests -p 'test_v84_junit_gate.py' -v > "$OUT/parser.log" 2>&1
grep -q 'Ran 23 tests' "$OUT/parser.log"
grep -q '^OK$' "$OUT/parser.log"
echo "V88_JS_63_PARSER_23_PASS"

"$PY" -m pytest -q -ra -o xfail_strict=true --maxfail=1 \
  server/tests/test_browser.py --junitxml="$OUT/browser.xml" > "$OUT/browser.log" 2>&1
"$PY" scripts/v84_junit_gate.py \
  --junit "$OUT/browser.xml" --shard v88-regional-energy-chromium \
  --min-passed 1 --max-skipped 0 \
  --actual-sha "$SHA" --expected-sha "$SHA" \
  --require-case test_real_browser_login_workflow_and_mobile \
  > "$OUT/browser-gate.json"
echo "V88_REAL_CHROMIUM_AND_SIX_ROLE_V88_SCREEN_PASS"

test -z "$(git status --porcelain)"
"$PY" - "$SHA" "$OUT" <<'PY'
from pathlib import Path
import hashlib,datetime,json,sys
sha,out=sys.argv[1],Path(sys.argv[2])
v87=Path("runtime")/("qa-v87-"+sha)/"acceptance-receipt.json"
g=json.loads((out/"monolithic-gate.json").read_text())
b=json.loads((out/"browser-gate.json").read_text())
prev=json.loads(v87.read_text())
assert g["passed"]>=404 and g["skipped"]==0
assert b["passed"]==1 and b["skipped"]==0
assert prev["same_database_native_test_count"]==40
assert prev["synthetic_oidc_test_count"]==2
receipt={
 "exact_git_sha":sha,"scope":"SYNTHETIC_REGIONAL_ENERGY_LOCAL_ONLY",
 "verified_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "single_process_python":g,"real_browser":b,
 "real_postgresql17_oidc_and_recovery_receipt_sha256":hashlib.sha256(v87.read_bytes()).hexdigest(),
 "js_unit_passed":63,"junit_gate_unit_passed":23,
 "real_source_data_verified":False,"corporate_mfa_verified":False,
 "nodal_network_n_minus_one_verified":False,"investment_approval":False,
 "production_ready":False,
 "evidence_sha256":{name:hashlib.sha256((out/name).read_bytes()).hexdigest()
  for name in ("monolithic.xml","browser.xml","javascript.log","parser.log")}
}
(out/"acceptance-receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
print("V88_RECEIPT_SHA256",hashlib.sha256((out/"acceptance-receipt.json").read_bytes()).hexdigest())
PY
echo "V88_SOURCE_PINNED_SYNTHETIC_ACCEPTANCE_PASS_PRODUCTION_HOLD"
