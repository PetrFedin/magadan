#!/usr/bin/env python3
"""Reproducible source-stamped necessary normative review, NOT legal approval."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from hydro_api.normative_stage_v911 import (  # noqa: E402
    REFERENCE_PATH, build_v911_research_receipt, load_catalog,
)

V99 = ROOT / "artifacts_v9/magadan_dispatch_policy_v99.json"
V910 = ROOT / "artifacts_v9/magadan_terminal_reserve_stress_v910.json"
MODULE = ROOT / "server/hydro_api/normative_stage_v911.py"
OUTPUT = ROOT / "artifacts_v9/magadan_normative_screen_v911.json"


def report() -> dict:
    files = (REFERENCE_PATH, V99, V910, MODULE, Path(__file__))
    for source in files:
        if not source.is_file():
            raise FileNotFoundError("V911_SOURCE_MISSING:" + str(source))
    sha = {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest()
           for p in files}
    catalog = load_catalog()
    historic = json.loads(V99.read_text(encoding="utf-8"))
    stress = json.loads(V910.read_text(encoding="utf-8"))
    return build_v911_research_receipt(catalog, historic, stress, sha)


def main() -> int:
    value = report()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(value, sort_keys=True, indent=2,
                                 ensure_ascii=False), encoding="utf-8")
    v99 = value["v99_winter_screen"]["policy_winter_non_turbine_screening"]
    v910 = value["v910_reference_screen"]
    print("V911_V99_THERMAL_FIRST_WINTER_RELEASE_SCREEN=",
          json.dumps(v99["thermal_first"], sort_keys=True))
    print("V911_V99_HYDRO_FIRST_WINTER_RELEASE_SCREEN=",
          json.dumps(v99["hydro_first"], sort_keys=True))
    print("V911_V910_REFERENCE_SCREEN=", json.dumps(v910, sort_keys=True))
    print("V911_RECEIPT_SHA256=", value["payload_sha256"])
    print("V911_JSON_SHA256=", sha256(OUTPUT.read_bytes()).hexdigest())
    assert value["firm_capacity_mw"] is None
    assert value["production_ready"] is False
    assert value["investment_decision"] == "HOLD"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
