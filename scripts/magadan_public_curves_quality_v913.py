#!/usr/bin/env python3
"""Source-pinned public Order 174 candidate curve quality audit, NOT field curves."""
from __future__ import annotations

from pathlib import Path
from hashlib import sha256
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"server"))

from hydro_api.public_curves_quality_v913 import ( # noqa: E402
    DIR, SOURCE_EXPECTED, load_candidate, validate_volume_candidate,
    review_quarantined_public_tables, validate_second_publisher_partial_crosscheck,
)

OUTPUT=ROOT/"artifacts_v9/magadan_public_curves_quality_v913.json"
FILES=tuple(
    DIR/f"order174_v913_{name}_volume_grid_candidate.json"
    for name in ("kolyma","ust_srednekan")
)+tuple(
    DIR/f"order174_v913_{name}_candidate.json"
    for name in ("kolyma_tailwater","ust_tailwater","kolyma_dispatch","ust_dispatch")
)+(
    DIR/"order174_v913_two_publisher_partial_crosscheck.json",
    ROOT/"server/hydro_api/public_curves_quality_v913.py",
    ROOT/"scripts/magadan_public_curves_quality_v913.py",
)

def report():
    if not all(f.is_file() for f in FILES):
        raise ValueError("V913_SOURCE_MISSING")
    curves={
        key:validate_volume_candidate(load_candidate(key),key)
        for key in SOURCE_EXPECTED
    }
    quarantined=review_quarantined_public_tables()
    independently_compared=validate_second_publisher_partial_crosscheck()
    for key,value in curves.items():
        if value["physical_operation_admitted"] is not False:
            raise AssertionError("V913_REAL_CURVE_FALSE_ADMISSION")
    for key,value in quarantined.items():
        if (value["active_tailwater_function"] is not False
                or value.get("active_zone_dispatch",False) is not False):
            raise AssertionError("V913_QUARANTINED_SOURCE_FALSE_ADMISSION")
    total=sum(x["numeric_coordinates"] for x in curves.values())
    if total!=1802:
        raise AssertionError("V913_SOURCE_POINTS_UNEXPECTED")
    result={
        "artifact":"MAGADAN-V913-ORDER174-PUBLIC-CANDIDATE-QUALITY-1",
        "document":"Order Rosvodresursy 174 (2025-07-07), registered 83126",
        "source_primary_authenticity_verified":False,
        "complete_independent_second_publisher_cell_comparison":False,
        "source_publication_secondary_transcription":True,
        "licensing_and_redistribution_review_completed":False,
        "original_source_document_sha256_verified":False,
        "candidate_curves":curves,
        "additional_tables_in_quarantine":quarantined,
        "independent_secondary_publisher_comparison":independently_compared,
        "source_sha256":{
            str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest()
            for p in FILES
        },
        "summary":{
            "reservoirs":2,
            "total_volume_coordinates":total,
            "candidate_kolyma_coordinates":curves["kolyma"]["numeric_coordinates"],
            "candidate_ust_coordinates":curves["ust_srednekan"]["numeric_coordinates"],
            "lower_equal_adjacent_rounded_volumes":curves["ust_srednekan"]["adjacent_equal_rounded_volumes"],
            "statutory_anchor_points_agree":6,
            "second_publisher_matching_coordinates":independently_compared["matching_secondary_publisher_cells"],
            "second_publisher_unchecked_coordinates":independently_compared["uncompared_kolyma_tail_cells"],
            "quarantined_secondary_tables":len(quarantined),
            "registered_tailwater_declines":1,
            "physical_curves_admitted_for_real_simulation":0,
            "dispatch_zone_curves_admitted_for_real_simulation":0,
        },
        "operator_hydraulic_admissibility_signed":False,
        "full_turbine_efficiency_curves_verified":False,
        "hydraulic_transit_calibrated":False,
        "industrial_power_firm_MW":None,
        "firm_available_capacity_mw":None,
        "network_n_minus_one_verified":False,
        "production_ready":False,
        "investment_decision":"HOLD",
    }
    source_bytes=json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False).encode("utf-8")
    result["payload_sha256"]=sha256(source_bytes).hexdigest()
    return result

def main():
    data=report()
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(data,sort_keys=True,indent=2,
                                 ensure_ascii=False),encoding="utf-8")
    print("V913_SUMMARY="+json.dumps(data["summary"],sort_keys=True))
    print("V913_SOURCE_LEDGER_COUNT="+str(len(data["source_sha256"])))
    print("V913_PAYLOAD_SHA256="+data["payload_sha256"])
    print("V913_FILE_SHA256="+sha256(OUTPUT.read_bytes()).hexdigest())
    return 0

if __name__=="__main__":
    raise SystemExit(main())
