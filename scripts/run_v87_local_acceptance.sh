#!/usr/bin/env bash
# One-SHA V8.7 integrated synthetic staging proof. No real enterprise MFA.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
SHA="${1:-}"
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]] || [[ "$(git rev-parse HEAD)" != "$SHA" ]]; then
  echo "V87_HOLD_EXACT_SOURCE_SHA_REQUIRED" >&2; exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "V87_HOLD_DIRTY_SOURCE_TREE" >&2; git status --short >&2; exit 2
fi
: "${HYDRO_NATIVE_CONFIG:?V87_HOLD_PG17_NATIVE_CONFIG_REQUIRED}"
: "${HYDRO_BROWSER_EXECUTABLE:?V87_HOLD_REAL_CHROMIUM_REQUIRED}"
test -s "$HYDRO_NATIVE_CONFIG" && test -x "$HYDRO_BROWSER_EXECUTABLE"
PY="$ROOT/.venv/bin/python"
test -x "$PY"
OUT="$ROOT/runtime/qa-v87-$SHA"
umask 077
mkdir -p "$OUT/screenshots"
export HYDRO_NATIVE_TESTS_REQUIRED=1 PYTHONPATH="$ROOT/server"
export HYDRO_BROWSER_EVIDENCE_DIR="$OUT/screenshots"

"$PY" -m pytest -q -ra -o xfail_strict=true --maxfail=1 \
  server/tests_v87/test_pg_oidc_browser_unified_v87.py \
  --junitxml="$OUT/unified.xml" > "$OUT/unified.log" 2>&1
"$PY" scripts/v84_junit_gate.py \
  --junit "$OUT/unified.xml" --shard v87-unified \
  --min-passed 2 --max-skipped 0 --actual-sha "$SHA" --expected-sha "$SHA" \
  --require-case test_v87_real_pg17_oidc_http_chromium_roles_and_audit \
  --require-case test_v87_mfa_claim_policy_enforced_and_no_auto_provision \
  > "$OUT/unified-gate.json"
echo "V87_UNIFIED_OIDC_BROWSER_PG17_2_PASS"

"$PY" -m pytest -q -ra -o xfail_strict=true --maxfail=1 \
  server/tests_v71/test_postgres_native.py \
  server/tests_v78/test_postgres_native_v78.py \
  server/tests_v8/test_postgres_native_boundary_v8.py \
  server/tests_v81/test_pg_graph_freeze_native_v81.py \
  --junitxml="$OUT/native.xml" > "$OUT/native.log" 2>&1
"$PY" scripts/v84_junit_gate.py \
  --junit "$OUT/native.xml" --shard v87-native-postgres17 \
  --min-passed 40 --max-skipped 0 --actual-sha "$SHA" --expected-sha "$SHA" \
  --require-case test_native_installed_version_and_exact_lock_contract \
  > "$OUT/native-gate.json"
echo "V87_SAME_DATABASE_NATIVE_PG17_40_PASS"

"$PY" scripts/v87_backup_restore.py \
  --native-config "$HYDRO_NATIVE_CONFIG" \
  --output "$OUT/recovery.json" > "$OUT/recovery.log" 2>&1
"$PY" - "$OUT" "$SHA" <<'PY'
import hashlib,json,sys,datetime
from pathlib import Path
out=Path(sys.argv[1]);sha=sys.argv[2]
data=json.loads((out/"recovery.json").read_text())
assert data["table_rows_equal"] and data["rls_policies_equal"]
assert data["triggers_equal"] and data["restored_rls_without_session_default_deny"]
assert not data["production_ready"]
receipt={
 "exact_git_sha":sha,
 "scope":"LOCAL_REAL_PG17_SYNTHETIC_IDP_ACR_ONLY",
 "synthetic_oidc_test_count":2,
 "same_database_native_test_count":40,
 "recovery_tables":data["table_count"],
 "recovery_rows":data["total_rows"],
 "recovery_rls_policies":data["rls_policy_count"],
 "recovery_triggers":data["trigger_count"],
 "corporate_idp_connected":False,
 "real_mfa_ceremony_verified":False,
 "production_ready":False,
 "created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "sha256":{n:hashlib.sha256((out/n).read_bytes()).hexdigest()
           for n in ("unified.xml","native.xml","recovery.json")},
}
(out/"acceptance-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
print("V87_INTEGRATED_RECOVERY_PASS",data["table_count"],data["total_rows"],
      data["rls_policy_count"],data["trigger_count"])
PY
test -z "$(git status --porcelain)"
echo "V87_SOURCE_PINNED_SYNTHETIC_STAGE_PASS_PRODUCTION_HOLD"
