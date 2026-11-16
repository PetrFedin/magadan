"""Isolated HTTP route contract; no real identity provider or field data."""
import hashlib
import json

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from hydro_api.baseline_reconciliation_api_v89 import install_baseline_reconciliation_v89_routes
from tests_v89.test_baseline_reconcile_v89 import sample


def build_app(role="engineer"):
    app = FastAPI()

    def current_user():
        return {"role": role, "org": "synthetic_lab"}

    def get_db():
        return object()

    def access(org_id, roles, actor, db):
        if org_id != actor["org"]:
            raise HTTPException(404, "unknown")
        if actor["role"] not in roles:
            raise HTTPException(403, "forbidden")

    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def sha(value):
        return hashlib.sha256(canonical(value).encode()).hexdigest()

    install_baseline_reconciliation_v89_routes(app, get_db, current_user, access, sha, canonical)
    return app


def test_http_read_only_reconciliation_and_separate_tenants():
    with TestClient(build_app()) as client:
        response = client.post("/v89/orgs/synthetic_lab/baseline/reconcile", json=sample())
        assert response.status_code == 200, response.text
        value = response.json()
        assert value["report"]["synthetic_additional_mw_total"] == "20"
        assert value["report"]["actual_available_capacity_mw"] is None
        assert value["proof"]["database_written"] is False
        assert value["proof"]["financial_ledger_written"] is False
        assert len(value["proof"]["report_sha256"]) == 64
        assert client.post("/v89/orgs/other_org/baseline/reconcile", json=sample()).status_code == 404
        assert client.get("/v89/meta/baseline-reconciliation-readiness").json()["production_ready"] is False


def test_http_ineligible_role_and_field_source_claim_are_rejected():
    with TestClient(build_app(role="economist")) as client:
        assert client.post("/v89/orgs/synthetic_lab/baseline/reconcile", json=sample()).status_code == 403
    data = sample()
    data["mode"] = "REAL_FIELD_SOURCE"
    with TestClient(build_app()) as client:
        assert client.post("/v89/orgs/synthetic_lab/baseline/reconcile", json=data).status_code == 422
