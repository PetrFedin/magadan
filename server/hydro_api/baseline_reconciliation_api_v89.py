"""Tenant-scoped synthetic-only baseline cross-record reconciliation endpoint.

Never identifies actual additional demand or allocates firm grid capacity.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .baseline_reconcile_v89 import BaselineReconcileCase, assess_baseline_reconciliation


def install_baseline_reconciliation_v89_routes(app, get_db, current_user, access, sha, canonical):
    router = APIRouter()

    @router.get("/v89/meta/baseline-reconciliation-readiness")
    def readiness():
        return {
            "release": "V8.9-STRICT-SYNTHETIC-BASELINE-JOIN",
            "multi_point_consumer_allocation_check": True,
            "partial_baseline_inclusion_supported": True,
            "authentic_forecast_source_verified": False,
            "source_rights_independently_verified": False,
            "actual_additional_demand_mw_verified": False,
            "n_minus_one_verified": False,
            "investment_approved": False,
            "production_ready": False,
        }

    @router.post("/v89/orgs/{org_id}/baseline/reconcile")
    def reconcile(org_id: str, body: BaselineReconcileCase,
                  user=Depends(current_user), db: Session = Depends(get_db)):
        access(org_id, {"engineer", "auditor"}, user, db)
        data = body.model_dump(mode="json")
        if len(canonical(data).encode("utf-8")) > 1_000_000:
            raise HTTPException(413, "V89_SYNTHETIC_BASELINE_CASE_TOO_LARGE")
        result = assess_baseline_reconciliation(body)
        return {
            "org_id": org_id,
            "report": result,
            "proof": {
                "input_sha256": sha({"org_id": org_id, "data": data}),
                "report_sha256": sha(result),
                "engine_sha256": hashlib.sha256(Path(__file__).with_name("baseline_reconcile_v89.py").read_bytes()).hexdigest(),
                "declared_source_hash_independently_verified": False,
                "actual_grid_capacity_verified": False,
                "owner_data_usage_rights_verified": False,
                "financial_ledger_written": False,
                "database_written": False,
                "production_approved": False,
            },
        }

    app.include_router(router)
