"""V8.9 stateless, authenticated, fail-closed data-quality preflight.

Synthetic numerical series only. Real source declarations must be metadata-only.
No writes, production equipment, or investment approvals.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .data_admission_v89 import MonthlyIntake, assess_v89
from .storage import User


def install_data_admission_v89_routes(app, get_db, current_user, access, sha, canonical):
    router = APIRouter()

    @router.get('/v89/meta/data-admission-readiness')
    def readiness():
        return {
            'release': '8.9-LAB',
            'hourly_utc_grain_contract': True,
            'canonical_consumer_deduplication': True,
            'owner_permission_independently_verified': False,
            'source_digests_independently_matched': False,
            'real_magadan_nodal_adequacy_verified': False,
            'field_data_ingestion_enabled': False,
            'external_reviewer_signed': False,
            'investment_eligible': False,
            'production_ready': False,
        }

    @router.post('/v89/orgs/{org_id}/data-admission/preflight')
    def preflight(org_id: str, body: MonthlyIntake,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
        access(org_id, {'engineer', 'auditor'}, user, db)
        payload = body.model_dump(mode='json')
        # Upper bound includes one full 31-day UTC month on up to 20 nodes.
        if len(canonical(payload).encode('utf-8')) > 4_000_000:
            raise HTTPException(413, 'V89_SYNTHETIC_INPUT_TOO_LARGE')
        result = assess_v89(body)
        return {
            'org_id': org_id,
            'report': result,
            'proof': {
                'input_sha256': sha({'org_id': org_id, 'payload': payload}),
                'report_sha256': sha(result),
                'engine_sha256': hashlib.sha256(Path(__file__).with_name('data_admission_v89.py').read_bytes()).hexdigest(),
                'data_written': False,
                'source_rights_confirmed': False,
                'actual_grid_capacity_confirmed': False,
                'financial_ledger_updated': False,
                'production_approved': False,
            },
        }

    app.include_router(router)
