"""V8.9 isolated HTTP adapter contract; no corporate access or production clients."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from hydro_api.data_admission_api_v89 import install_data_admission_v89_routes
from tests_v89.test_data_admission_v89 import synthetic_month


def build_test_app():
    app = FastAPI()

    def current_user():
        return {'role': 'engineer', 'org': 'isolated'}

    def get_db():
        return object()

    def access(org_id, roles, actor, db):
        if org_id != actor['org']:
            raise HTTPException(404, 'unavailable')
        if actor['role'] not in roles:
            raise HTTPException(403, 'forbidden')

    import json
    import hashlib

    def canonical(x):
        return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

    def sha(x):
        return hashlib.sha256(canonical(x).encode()).hexdigest()

    install_data_admission_v89_routes(app, get_db, current_user, access, sha, canonical)
    return app


def test_real_route_model_processing_local_only():
    with TestClient(build_test_app()) as client:
        result = client.post(
            '/v89/orgs/isolated/data-admission/preflight', json=synthetic_month()
        )
        assert result.status_code == 200, result.text
        payload = result.json()
        assert payload['report']['status'] == 'SYNTHETIC_QUALITY_PASS_ONLY'
        assert payload['report']['real_available_capacity_mw'] is None
        assert payload['proof']['data_written'] is False
        assert payload['proof']['financial_ledger_updated'] is False
        assert len(payload['proof']['engine_sha256']) == 64
        assert client.post(
            '/v89/orgs/other/data-admission/preflight', json=synthetic_month()
        ).status_code == 404
        meta = client.get('/v89/meta/data-admission-readiness').json()
        assert meta['production_ready'] is False
        assert meta['field_data_ingestion_enabled'] is False


def test_real_field_payload_rejected_before_handler_executes():
    data = synthetic_month()
    data['mode'] = 'PROPOSED_METADATA_ONLY'
    with TestClient(build_test_app()) as client:
        assert client.post(
            '/v89/orgs/isolated/data-admission/preflight', json=data
        ).status_code == 422
