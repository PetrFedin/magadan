"""Real PostgreSQL 17 security gate for V8 synthetic physical boundaries.

Must execute on a freshly bootstrapped PostgreSQL 17 instance. A local SQLite
pass does NOT validate RLS, serializable claims or an externally operated grid.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

if not os.environ.get("HYDRO_NATIVE_CONFIG"):
    if os.environ.get("HYDRO_NATIVE_TESTS_REQUIRED") == "1":
        raise RuntimeError("NATIVE_ACCEPTANCE_BLOCKED: missing PostgreSQL 17 config")
    pytest.skip("Real PostgreSQL 17 missing; native gate not accepted", allow_module_level=True)
try:
    import psycopg  # noqa: F401
except ImportError:
    if os.environ.get("HYDRO_NATIVE_TESTS_REQUIRED") == "1":
        raise RuntimeError("NATIVE_ACCEPTANCE_BLOCKED: missing psycopg")
    pytest.skip("PostgreSQL driver missing; native gate not accepted", allow_module_level=True)

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests_v71.test_postgres_native import n, native, bind
from tests_v75.test_handoff_api import maintenance_payload

pytestmark = pytest.mark.native_pg
SAMPLES = Path(__file__).resolve().parents[1] / "ui" / "samples_v72.json"


def graph(n, other_asset=None):
    """Insert the test graph with DBA credentials, not hk_app privileges."""
    org = n["org"]
    left = "SYNTHETIC-BOUNDARY-V8-" + uuid4().hex[:14]
    right = ("SYNTHETIC-BOUNDARY-V8-" + uuid4().hex[:14]) if other_asset else None
    with n["admin"].begin() as c:
        def node(id, parent):
            c.execute(text("""INSERT INTO public.meter_boundaries_v8
                (org_id,id,parent_id,quantity_class,source_ref,created_by)
                VALUES(:org,:id,:parent,'EQUIPMENT_MAINTENANCE',:ref,:actor)"""),
                {"org":org,"id":id,"parent":parent,"actor":n["ids"]["engineer"],
                 "ref":"SYNTHETIC-GRAPH-EVIDENCE-"+uuid4().hex})
        def mapping(asset, boundary):
            c.execute(text("""INSERT INTO public.boundary_assets_v8
                (org_id,asset_id,boundary_id,evidence_ref,created_by)
                VALUES(:org,:asset,:boundary,:ref,:actor)"""),
                {"org":org,"asset":asset,"boundary":boundary,"actor":n["ids"]["engineer"],
                 "ref":"SYNTHETIC-ASSIGNMENT-EVIDENCE-"+uuid4().hex})
        node(left,None)
        mapping(n["asset"],left)
        if other_asset:
            node(right,left)
            mapping(other_asset,right)
            for a,b in ((left,right),(right,left)):
                c.execute(text("""INSERT INTO public.boundary_conflicts_v8
                    (org_id,left_id,right_id,reason)
                    VALUES(:org,:l,:r,'PARENT_CHILD_SCOPE')"""),
                    {"org":org,"l":a,"r":b})
    return left,right


def source(n,asset,tag):
    case=json.loads(SAMPLES.read_text())["turbine"]
    study=n["client"].post(f'/v72/orgs/{n["org"]}/studies',
        headers=n["h"]("engineer"),json={
            "asset_id":asset,"module":"turbine",
            "scenario_group":"synthetic-pg17-v8",
            "source_ref":"SYNTHETIC-PG17-V8-"+tag,"case":case})
    assert study.status_code==201,study.text
    payload=maintenance_payload({"turbine":study.json()["id"]})
    payload["maintenance_bridge"]["planning_reference"]+="-"+tag
    handoff=n["client"].post(f'/v75/orgs/{n["org"]}/handoffs',
        headers=n["h"]("engineer"),json=payload)
    assert handoff.status_code==201,handoff.text
    return handoff.json()["id"]


def claim(n,asset,source_id):
    res=n["client"].post(f'/v79/orgs/{n["org"]}/benefit-reservations',
        headers=n["h"]("economist"),json={
            "asset_id":asset,"family":"MAINTENANCE_COST",
            "start_year":2030,"end_year":2035,
            "source_kind":"MAINTENANCE_HANDOFF_V75","source_id":source_id,
            "measurement_plan_ref":"SYNTHETIC-V8-NATIVE-PLAN-"+uuid4().hex,
            "measurement_boundary_description":
                "Synthetic lab boundary, not real meters or permission from an operator.",
            "comparison_normalization":
                "Demand, dates, physical asset and all repairs must be normalized by an independent reviewer."})
    return res.status_code


def test_v8_native_rls_and_no_app_graph_authoring(n):
    tables=("meter_boundaries_v8","boundary_assets_v8","boundary_conflicts_v8")
    with n["admin"].connect() as conn:
        assert int(conn.scalar(text("SHOW server_version_num"))) >= 170000
        for tbl in tables:
            row=conn.execute(text("""SELECT c.relrowsecurity,c.relforcerowsecurity,r.rolname
                FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner
                WHERE c.oid=to_regclass(:tbl)"""),{"tbl":"public."+tbl}).one()
            assert tuple(row)==(True,True,"hk_owner")
            for privilege in ("INSERT","UPDATE","DELETE","TRUNCATE"):
                assert conn.scalar(text("SELECT has_table_privilege('hk_app',:tbl,:p)"),
                    {"tbl":"public."+tbl,"p":privilege}) is False
    left,_=graph(n)
    with n["appengine"].connect() as conn:
        assert conn.execute(text("SELECT id FROM public.meter_boundaries_v8")).all()==[]
    with n["appengine"].begin() as conn:
        bind(conn,n,"engineer")
        assert conn.scalar(text("SELECT count(*) FROM public.meter_boundaries_v8 WHERE id=:id"),
                           {"id":left})==1
    with pytest.raises(DBAPIError):
        with n["appengine"].begin() as conn:
            bind(conn,n,"engineer")
            conn.execute(text("""INSERT INTO public.meter_boundaries_v8
                (org_id,id,quantity_class,source_ref,created_by)
                VALUES(:org,:id,'EQUIPMENT_MAINTENANCE',:ref,:actor)"""),
                {"org":n["org"],"id":"SYNTHETIC-BOUNDARY-V8-"+uuid4().hex[:14],
                 "ref":"SYNTHETIC-UNAUTHORIZED-TEST-"+uuid4().hex,
                 "actor":n["ids"]["engineer"]})
    with n["appengine"].begin() as conn:
        bind(conn,n,"other",n["other"])
        assert conn.scalar(text("SELECT count(*) FROM public.meter_boundaries_v8"))==0


def test_v8_native_graph_freezes_after_claim(n):
    graph(n)
    first=source(n,n["asset"],"FREEZE-"+uuid4().hex[:8])
    assert claim(n,n["asset"],first)==201
    with pytest.raises(DBAPIError):
        with n["admin"].begin() as conn:
            conn.execute(text("""INSERT INTO public.meter_boundaries_v8
                (org_id,id,quantity_class,source_ref,created_by)
                VALUES(:org,:id,'EQUIPMENT_MAINTENANCE',:ref,:actor)"""),
                {"org":n["org"],"id":"SYNTHETIC-BOUNDARY-V8-"+uuid4().hex[:14],
                 "ref":"SYNTHETIC-FORBIDDEN-TOPOLOGY-EDIT-"+uuid4().hex,
                 "actor":n["ids"]["engineer"]})


def test_v8_native_concurrent_nested_boundary_claims(n):
    created=n["client"].post(f'/v7/orgs/{n["org"]}/assets',
        headers=n["h"]("engineer"),
        json={"name":"Synthetic second metering-boundary alias"})
    assert created.status_code==201,created.text
    second=created.json()["id"]
    graph(n,second)
    first_source=source(n,n["asset"],"LEFT-"+uuid4().hex[:8])
    second_source=source(n,second,"RIGHT-"+uuid4().hex[:8])
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(claim,n,n["asset"],first_source)
        other=pool.submit(claim,n,second,second_source)
        statuses=sorted((first.result(),other.result()))
    assert statuses==[201,409],statuses
    with n["appengine"].begin() as conn:
        bind(conn,n,"auditor")
        assert conn.scalar(text("SELECT count(*) FROM public.benefit_reservations_v79 WHERE org_id=:o"),
                           {"o":n["org"]})==1
