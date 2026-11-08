#!/usr/bin/env bash
# Reproducible LOCAL laboratory CI. Not deployment or industrial acceptance.
set -Eeuo pipefail
if [[ "$#" -ne 1 ]]; then echo "Usage: $0 <40-char-head-sha>" >&2; exit 2; fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
SHA="$1"
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]] || [[ "$(git rev-parse HEAD)" != "$SHA" ]]; then
  echo "QA_HOLD: exact current Git HEAD SHA required" >&2; exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "QA_HOLD: dirty working tree" >&2
  git status --short >&2
  exit 2
fi
PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then echo "QA_HOLD: Python venv not installed" >&2; exit 2; fi
if ! printenv HYDRO_NATIVE_CONFIG >/dev/null || [[ ! -f "$HYDRO_NATIVE_CONFIG" ]]; then
  echo "QA_HOLD: provide dedicated PostgreSQL17 native config" >&2; exit 2
fi
OUT="$ROOT/runtime/qa-v86-$SHA"
umask 077
mkdir -p "$OUT/browser" "$OUT/scenarios"
export PYTHONPATH="$ROOT/server"
export HYDRO_NATIVE_TESTS_REQUIRED=1
export HYDRO_BROWSER_EVIDENCE_DIR="$OUT/browser"
printf '%s\n' "$SHA" > "$OUT/exact-sha.txt"
echo "EXACT_LOCAL_QA_SHA=$SHA"

"$PY" - <<'PY' > "$OUT/source-452.log"
import hashlib,json,subprocess
origin="eab0d0b1e418558914a448a21cf496982ac10a1d"
def git(*args):
 return subprocess.run(["git",*args],capture_output=True,check=True).stdout
raw=git("show",f"{origin}:MANIFEST_SHA256_V8.json")
assert hashlib.sha256(raw).hexdigest()=="c8d248cb351aa57de315edb370f3143da6b0fe1954df48fabf618d12e55146d3"
manifest=json.loads(raw)
assert manifest["file_count"]==452 and len(manifest["files"])==452
for path,h in manifest["files"].items():
 assert hashlib.sha256(git("show",f"{origin}:{path}")).hexdigest()==h,path
print("ORIGINAL_V8_MANIFEST_452_OF_452_SHA256_PASS; field provenance remains unverified")
PY
echo "ORIGINAL_SOURCE_BASELINE_PASS"

"$PY" -m unittest discover -s scripts/tests -p 'test_v84_junit_gate.py' -v > "$OUT/gate.log" 2>&1
grep -q 'Ran 23 tests' "$OUT/gate.log"
grep -q '^OK$' "$OUT/gate.log"
echo "EVIDENCE_VALIDATOR_23_PASS"

node --check server/ui/ui.js > "$OUT/js-syntax.log" 2>&1
npm test --prefix v6-client > "$OUT/javascript.log" 2>&1
grep -q '^# pass 63$' "$OUT/javascript.log"
grep -q '^# fail 0$' "$OUT/javascript.log"
echo "JAVASCRIPT_63_PASS"

"$PY" scripts/verify_route_independent_v83.py > "$OUT/route.log" 2>&1
"$PY" scripts/verify_energy_integral_v832.py > "$OUT/energy.log" 2>&1
"$PY" scripts/reproduce_v83.py --out "$OUT/scenarios" > "$OUT/scenario.log" 2>&1
echo "SYNTHETIC_PHYSICS_REPRODUCED"

"$PY" -m pytest -q -ra -o xfail_strict=true --maxfail=1 \
  server/tests_v71 server/tests_v72 server/tests_v73 server/tests_v74 \
  server/tests_v75 server/tests_v76 server/tests_v77 server/tests_v78 \
  server/tests_v79 server/tests_v8 server/tests_v81 server/tests_v82 \
  server/tests_v83 server/tests_v85 server/tests \
  --ignore=server/tests_v71/test_postgres_native.py \
  --ignore=server/tests_v78/test_postgres_native_v78.py \
  --ignore=server/tests_v8/test_postgres_native_boundary_v8.py \
  --ignore=server/tests_v81/test_pg_graph_freeze_native_v81.py \
  --ignore=server/tests/test_browser.py \
  --junitxml="$OUT/python.xml" > "$OUT/python.log" 2>&1
"$PY" scripts/v84_junit_gate.py --junit "$OUT/python.xml" \
  --shard monolithic-python --min-passed 380 --max-skipped 0 \
  --actual-sha "$SHA" --expected-sha "$SHA" \
  --require-case test_local_seed_runs_from_empty_database_and_refuses_second_seed \
  --require-case test_independent_role_sessions_forecast_to_cascade_without_financial_post \
  --require-case test_peak_violation_cannot_enter_money_or_dispatch_in_any_role \
  > "$OUT/python-receipt.json"
echo "MONOLITHIC_PYTHON_380_PASS"

"$PY" -m pytest -q -ra -o xfail_strict=true --maxfail=1 \
  server/tests_v71/test_postgres_native.py \
  server/tests_v78/test_postgres_native_v78.py \
  server/tests_v8/test_postgres_native_boundary_v8.py \
  server/tests_v81/test_pg_graph_freeze_native_v81.py \
  --junitxml="$OUT/native.xml" > "$OUT/native.log" 2>&1
"$PY" scripts/v84_junit_gate.py --junit "$OUT/native.xml" \
  --shard native-postgresql17 --min-passed 40 --max-skipped 0 \
  --actual-sha "$SHA" --expected-sha "$SHA" \
  --require-case test_native_installed_version_and_exact_lock_contract \
  > "$OUT/native-receipt.json"
echo "POSTGRESQL17_NATIVE_40_PASS"

"$PY" -m pytest -q -ra -o xfail_strict=true --maxfail=1 \
  server/tests/test_browser.py --junitxml="$OUT/browser.xml" > "$OUT/browser.log" 2>&1
"$PY" scripts/v84_junit_gate.py --junit "$OUT/browser.xml" \
  --shard chromium-role-and-responsive --min-passed 1 --max-skipped 0 \
  --actual-sha "$SHA" --expected-sha "$SHA" \
  --require-case test_real_browser_login_workflow_and_mobile \
  > "$OUT/browser-receipt.json"
echo "CHROMIUM_BROWSER_ROLE_MATRIX_PASS"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "QA_HOLD: tracked or untracked source changed during tests" >&2
  git status --short >&2
  exit 2
fi

"$PY" - "$OUT" "$SHA" <<'PY'
from pathlib import Path
import datetime,hashlib,json,sys
out=Path(sys.argv[1]); sha=sys.argv[2]
def read(name):return json.loads((out/name).read_text())
science=read("scenarios/cascade_scenario_index_v83.json")["summary"]
energy=read("energy.log")
route=read("route.log")
assert science["daily_branch_evaluations"]==60
assert science["all_normal_scenarios_mass_balance"] is True
assert science["source_data_attested"] is False
assert energy["cases"]==256 and energy["all_256_reference_checks_pass"] is True
assert route["scenarios"]==438 and route["conservation_check_passed"] is True
receipt={
 "git_sha":sha,"generated_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "scope":"SOURCE_PINNED_LOCAL_SYNTHETIC_LAB_ONLY",
 "original_v8_manifest_files_verified":452,
 "junit_validator_unit_tests_passed":23,
 "javascript_unit_tests_passed":63,
 "python":read("python-receipt.json"),
 "native_postgres17":read("native-receipt.json"),
 "chromium_browser":read("browser-receipt.json"),
 "synthetic_energy_trials":256,
 "synthetic_route_cases":438,
 "hydrology_branch_evaluations":60,
 "corporate_sso_verified":False,"external_worm_verified":False,
 "real_magadan_data_verified":False,"public_staging_deployed":False,
 "github_hosted_ci_verified":False,"production_ready":False,
 "evidence_sha256":{n:hashlib.sha256((out/n).read_bytes()).hexdigest()
   for n in ("python.xml","native.xml","browser.xml","javascript.log",
             "gate.log","route.log","energy.log")},
}
(out/"acceptance-receipt.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n")
print(json.dumps({k:receipt[k] for k in ("git_sha","scope","production_ready")}))
PY
echo "SOURCE_PINNED_LOCAL_ACCEPTANCE_COMPLETE_PRODUCTION_HOLD"
