"""V9.13 public *candidate* curve import: reproducibility and data-quality guard.

The published table is from a secondary legal-article transcription, not a
signed operator/official-original calibration. No part of this module can
return approved real hydraulic power, operation, law compliance or firm MW.
Flat rounded lower-reservoir volumes prevent unique global inversion.
Tailwater curves and dispatch-zone graphics are quarantined (missing or
ambiguous mapping and explicit Appendix 11 non-monotonicity).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
import re

ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/"data/reference"
STEP=Decimal("0.10")
TEN=Decimal("10")
SOURCE_EXPECTED={
    "kolyma":{
        "appendix":8,"rows":111,"points":1101,
        "first_bs":"369.06","last_bs":"479.06","first_volume":"0.168",
        "last_volume":"32.400","start_os":"370.00","datum":"BS_AND_OS",
        "ties":0,"anchors":("7.838","15.077","17.961"),
        "anchor_levels":("431.06","450.56","456.66")
    },
    "ust_srednekan":{
        "appendix":9,"rows":71,"points":701,
        "first_bs":"230.00","last_bs":"300.00","first_volume":"0.000",
        "last_volume":"8.746","datum":"BS","ties":73,
        "anchors":("2.863","5.436","6.085"),
        "anchor_levels":("278.00","290.00","292.30")
    },
}
OTHER={
  "kolyma_tailwater":(10,3),
  "ust_tailwater":(11,13),
  "kolyma_dispatch":(12,50),
  "ust_dispatch":(13,25),
}
MISSING="DATA_INSUFFICIENT"
RESEARCH="SECONDARY_CANDIDATE_NOT_OPERATIONALLY_APPROVED"

def path_for(reservoir:str)->Path:
    if reservoir not in SOURCE_EXPECTED: raise ValueError("V913_UNKNOWN_RESERVOIR")
    return DIR/f"order174_v913_{reservoir}_volume_grid_candidate.json"

def _dec(value,field):
    if isinstance(value,bool) or not isinstance(value,(str,int,float,Decimal)):
        raise ValueError("V913_INVALID_NUMERIC_"+field)
    try:x=Decimal(str(value))
    except InvalidOperation as exc:raise ValueError("V913_INVALID_NUMERIC_"+field) from exc
    if not x.is_finite():raise ValueError("V913_NONFINITE_"+field)
    return x

def load_candidate(reservoir):
    p=path_for(reservoir)
    d=json.loads(p.read_text(encoding="utf-8"))
    validate_volume_candidate(d,reservoir)
    return d

def validate_volume_candidate(d,reservoir):
    if not isinstance(d,dict) or reservoir not in SOURCE_EXPECTED:
        raise ValueError("V913_UNRECOGNIZED_TABLE")
    e=SOURCE_EXPECTED[reservoir]
    source=d.get("source")
    if (not isinstance(source,dict) or source.get("primary_official_original_authenticity_verified") is not False
        or source.get("licensing_review_completed") is not False
        or source.get("publisher")!="SudAct.ru secondary legal-publication reproduction"
        or source.get("retrieved_day")!="2026-11-22"
        or f"/prilozhenie-n-{e['appendix']}/" not in source.get("url","")):
        raise ValueError("V913_UNKNOWN_SOURCE_OR_FORGED_APPROVAL")
    if (d.get("artifact")!="MAGADAN-V913-PUBLIC-ORDER174-CURVE-CANDIDATE-1"
        or d.get("reservoir")!=reservoir or d.get("appendix")!=e["appendix"]
        or d.get("candidate_only_not_an_approved_interpolation_curve") is not True
        or d.get("operational_use_allowed") is not False or d.get("production_ready") is not False):
        raise ValueError("V913_CANDIDATE_NOT_QUARANTINED")
    unit=d.get("units",{})
    if (unit.get("stage")!="m" or unit.get("stage_datum")!=e["datum"]
        or unit.get("volume")!="km3"
        or unit.get("grid_resolution_m")!="0.10"
        or unit.get("volume_precision_km3")!="0.001"
        or d.get("column_offsets_m")!=[f"{i/10:.2f}" for i in range(10)]):
        raise ValueError("V913_UNIT_OR_GRID_CONTRACT")
    rows=d.get("rows")
    if not isinstance(rows,list) or len(rows)!=e["rows"]:
        raise ValueError("V913_TABLE_ROW_COUNT_MISMATCH")
    if (d.get("expected_sources_row_count")!=e["rows"] or
        d.get("expected_coordinate_count")!=e["points"]):
        raise ValueError("V913_TABLE_COMPLETENESS_DRIFT")
    data=[];last=None;ties=0
    for i,row in enumerate(rows):
        if row.get("source_row_index")!=i+1:
            raise ValueError("V913_SOURCE_ROW_INDEX_DRIFT")
        stage=_dec(row.get("stage_bs_base_m"),"STAGE")
        if stage!=_dec(e["first_bs"],"EXPECTED_STAGE")+i:
            raise ValueError("V913_STAGE_ROW_GAP")
        if reservoir=="kolyma":
            os=_dec(row.get("stage_os_base_m"),"OS")
            if os!=_dec(e["start_os"],"EXPECTED_OS")+i or os-stage!=Decimal("0.94"):
                raise ValueError("V913_OS_BS_DATUM_MISMATCH")
        elif row.get("stage_os_base_m") is not None:
            raise ValueError("V913_FAKE_UST_OS_DATUM")
        vs=row.get("volume_km3_by_0p1m_offset")
        expected_len=1 if i==e["rows"]-1 else 10
        if not isinstance(vs,list) or len(vs)!=expected_len:
            raise ValueError("V913_POINT_GAP_OR_SURPLUS")
        for j,s in enumerate(vs):
            if not isinstance(s,str) or not re.fullmatch(r"\d+\.\d{3}",s):
                raise ValueError("V913_ROUNDED_VOLUME_FORMAT")
            v=_dec(s,"VOLUME")
            z=stage+STEP*j
            if last is not None:
                lastz,lastv=last
                if z-lastz!=STEP or v<lastv:
                    raise ValueError("V913_STAGE_GAP_OR_VOLUME_DECREASE")
                ties+=int(v==lastv)
            data.append((z,v))
            last=(z,v)
    if len(data)!=e["points"] or ties!=e["ties"]:
        raise ValueError("V913_INCOMPLETE_TABLE_OR_PLATEAU_DRIFT")
    if (data[0][0]!=_dec(e["first_bs"],"MIN") or
        data[-1][0]!=_dec(e["last_bs"],"MAX") or
        data[0][1]!=_dec(e["first_volume"],"MINV") or
        data[-1][1]!=_dec(e["last_volume"],"MAXV")):
        raise ValueError("V913_END_POINT_DRIFT")
    observations=[]
    by_stage=dict(data)
    for z,target in zip(e["anchor_levels"],e["anchors"]):
        observed=by_stage.get(_dec(z,"ANCHOR_LEVEL"))
        if observed!=_dec(target,"ANCHOR_VOLUME"):
            raise ValueError("V913_STATUTORY_ANCHOR_DRIFT")
        observations.append(str(observed))
    anchors=d.get("observed_anchors_from_independent_section_V")
    if anchors!={"umo_km3":observations[0],"npu_km3":observations[1],"fpu_km3":observations[2]}:
        raise ValueError("V913_CANDIDATE_ANCHOR_LEDGER_DRIFT")
    if d.get("adjacent_equal_rounded_volumes")!=ties:
        raise ValueError("V913_TIE_COUNT_DRIFT")
    return {
        "reservoir":reservoir,
        "source_rows":len(rows),"numeric_coordinates":len(data),
        "adjacent_equal_rounded_volumes":ties,
        "strict_inverse_unique_for_all_values":ties==0,
        "observed_anchors_km3":dict(zip(("umo","npu","fpu"),observations)),
        "source_is_secondary":True,
        "physical_operation_admitted":False,
    }

def candidate_volume_at_stage(reservoir,stage_bs_m,*,mode="research"):
    """Only a visibly marked rounded-table research lookup, never actual MW."""
    if mode!="research":
        return {"status":MISSING,"reason":"V913_PRIMARY_CURVES_AND_ENGINEERING_SIGNOFF_ABSENT",
                "volume_km3":None,"approved_real_curve":False}
    d=load_candidate(reservoir)
    z=_dec(stage_bs_m,"STAGE")
    points=[]
    for row in d["rows"]:
        z0=_dec(row["stage_bs_base_m"],"BS")
        for j,v in enumerate(row["volume_km3_by_0p1m_offset"]):
            points.append((z0+STEP*j,_dec(v,"V")))
    if z<points[0][0] or z>points[-1][0]:
        raise ValueError("V913_EXTRAPOLATION_NOT_PERMITTED")
    for left,right in zip(points,points[1:]):
        z0,v0=left;z1,v1=right
        if z==z0:result=v0;interpolated=False;break
        if z0<z<z1:
            result=v0+(v1-v0)*(z-z0)/(z1-z0)
            interpolated=True;break
    else:
        result=points[-1][1]
        interpolated=False
    return {"status":RESEARCH,"reservoir":reservoir,
            "stage_m_bs":str(z),"rounded_table_volume_km3":str(result),
            "interpolated_within_0p1m_published_grid":interpolated,
            "approved_real_curve":False,"firm_capacity_mw":None}

def candidate_exact_inverse(reservoir,volume_km3):
    """No fake unique inverse when published rounding produces plateaus."""
    d=load_candidate(reservoir)
    target=_dec(volume_km3,"VOLUME")
    matches=[]
    for row in d["rows"]:
        z0=_dec(row["stage_bs_base_m"],"BS")
        for j,v in enumerate(row["volume_km3_by_0p1m_offset"]):
            if _dec(v,"V")==target: matches.append(z0+STEP*j)
    if len(matches)>1:
        return {"status":"AMBIGUOUS_INVERSE_DUE_TO_ROUNDED_PLATEAU",
                "candidate_stage_interval_m_bs":[str(min(matches)),str(max(matches))],
                "unique_stage_m_bs":None,"approved_real_curve":False}
    if not matches: raise ValueError("V913_INVERSE_ONLY_EXACT_PUBLISHED_VOLUME_ALLOWED")
    return {"status":RESEARCH,"unique_stage_m_bs":str(matches[0]),
            "approved_real_curve":False}

def review_quarantined_public_tables():
    info={}
    for key,(app,expected_rows) in OTHER.items():
        p=DIR/f"order174_v913_{key}_candidate.json"
        d=json.loads(p.read_text(encoding="utf-8"))
        source=d.get("source",{})
        if (d.get("appendix")!=app or d.get("table_key")!=key
                or d.get("operator_admitted") is not False
                or d.get("numeric_geometry_ready") is not False
                or d.get("production_ready") is not False
                or source.get("primary_original_bytes_verified") is not False
                or f"/prilozhenie-n-{app}/" not in source.get("url","")
                or len(d.get("raw_table_lines",[]))!=expected_rows):
            raise ValueError("V913_QUARANTINE_TABLE_CONTRACT_FAILED:"+key)
        if any(not isinstance(x.get("raw"),str) or not x["raw"].startswith("|")
               for x in d["raw_table_lines"]):
            raise ValueError("V913_SOURCE_ROW_LOST")
        if key=="ust_tailwater":
            readings=d.get("readings",[])
            if len(readings)!=11:
                raise ValueError("V913_TAILWATER_INCOMPLETE")
            if any(readings[i]["discharge_m3_s"]>=readings[i+1]["discharge_m3_s"]
                   for i in range(10)):
                raise ValueError("V913_TAILWATER_Q_NONINCREASING")
            q={row["discharge_m3_s"]:row for row in readings}
            if not (q[6000]["stage_series_2_m_bs"]==231.78
                    and q[8000]["stage_series_2_m_bs"]==229.33
                    and q[10000]["stage_series_2_m_bs"]==231.78):
                raise ValueError("V913_TAILWATER_FLAGGED_ANOMALY_CHANGED")
            decline=q[6000]["stage_series_2_m_bs"]-q[8000]["stage_series_2_m_bs"]
            if abs(decline-2.45)>1e-9 or len(d.get("quarantined_declines",[]))!=1:
                raise ValueError("V913_TAILWATER_NEGATIVE_SLOPE_NOT_FLAGGED")
            info[key]={"published_series_count":2,"raw_readings":len(readings),
                       "nonmonotonic_series_2_drop_m":2.45,
                       "active_tailwater_function":False}
        else:
            info[key]={"raw_table_lines":len(d["raw_table_lines"]),
                       "active_tailwater_function":False,
                       "active_zone_dispatch":False}
    return info
