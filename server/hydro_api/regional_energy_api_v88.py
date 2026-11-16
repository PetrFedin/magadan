"""V8.8 authenticated and stateless regional supply / demand and NPV screening.

This endpoint never mutates DB, never treats nameplate capacity as deliverable,
never certifies financial savings, production dispatch or an actual grid node.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .regional_energy_v88 import (
    ENGINE_TAG, RegionalEnergyDecisionV88, evaluate_regional_energy_v88,
)
from .storage import User


def install_regional_energy_v88_routes(app, get_db, current_user, access, sha, canonical):
    router = APIRouter()

    @router.get("/v88/meta/regional-energy-readiness")
    def readiness():
        return {
            "release": "8.8-SYNTHETIC-LAB",
            "engine": ENGINE_TAG,
            "monthly_energy_adequacy": True,
            "coincident_peak_and_network_screen": True,
            "scenario_codes": ["NORMAL", "LOW_WATER", "NETWORK_CONTINGENCY"],
            "conditionally_modelled_npv": True,
            "real_magadan_source_data_verified": False,
            "regional_nodal_grid_model_verified": False,
            "n_minus_one_verified": False,
            "actual_grid_connection_capacity_verified": False,
            "financial_benefits_certified": False,
            "investment_approval_eligible": False,
            "production_ready": False,
        }

    @router.post("/v88/orgs/{org_id}/regional-energy/evaluate")
    def research_balance(
        org_id: str,
        body: RegionalEnergyDecisionV88,
        u: User = Depends(current_user),
        db: Session = Depends(get_db),
    ):
        access(org_id, {"engineer", "auditor"}, u, db)
        payload = body.model_dump(mode="json")
        if len(canonical(payload).encode("utf-8")) > 220_000:
            raise HTTPException(413, "REGIONAL_SYNTHETIC_INPUT_TOO_LARGE")
        try:
            result = evaluate_regional_energy_v88(body)
        except (ValueError, ArithmeticError, OverflowError):
            raise HTTPException(422, "INVALID_SYNTHETIC_REGIONAL_CALCULATION") from None
        engine_sha = hashlib.sha256(
            Path(__file__).with_name("regional_energy_v88.py").read_bytes()
        ).hexdigest()
        return {
            "org_id": org_id,
            "report": result,
            "proof": {
                "input_sha256": sha({"org_id": org_id, "payload": payload}),
                "report_sha256": sha(result),
                "engine_sha256": engine_sha,
                "stateful_record_saved": False,
                "regional_balance_certified": False,
                "source_data_attested": False,
                "native_postgresql17_rls_verified_by_this_call": False,
                "financial_ledger_updated": False,
                "corporate_investment_approval": False,
                "dispatch_recommendation": None,
                "production_approved": False,
            },
        }

    app.include_router(router)
