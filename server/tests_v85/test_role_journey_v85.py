"""Synthetic HTTP golden journey across separately authenticated role clients.

These tests use the repository's isolated SQLite lab fixture. They do not
establish PostgreSQL RLS, real browser E2E, corporate identity or field safety.
"""
from contextlib import ExitStack
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from hydro_api.storage import Asset, BenefitReservationV79, Membership, StudyRun, User
from tests_v83.fixture import cascade_case_v83

FORECAST = '/v82/orgs/magadan-lab/hydroforecast/evaluate'
CASCADE = '/v83/orgs/magadan-lab/cascade/forecast-screen'
OTHER_CASCADE = '/v83/orgs/separate-org/cascade/forecast-screen'


@pytest.fixture
def role_lab(env):
    with env['db']() as db:
        db.add(Asset(id='v83-lower', org_id='magadan-lab',
                     name='SYNTHETIC-LOWER-ROLE-JOURNEY',
                     classification='LAB_REFERENCE'))
        db.commit()
    return env


def stored_counts(env):
    with env['db']() as db:
        return (
            db.scalar(select(func.count()).select_from(StudyRun)),
            db.scalar(select(func.count()).select_from(BenefitReservationV79)),
        )


def test_independent_role_sessions_forecast_to_cascade_without_financial_post(role_lab):
    """Engineer/auditor can reproduce while finance/viewer/other org cannot."""
    env = role_lab
    assert len({env['tokens'][name] for name in
                ('lead', 'audit', 'finance', 'viewer', 'other')}) == 5
    body = cascade_case_v83()
    baseline = stored_counts(env)
    with ExitStack() as stack:
        clients = {name: stack.enter_context(TestClient(env['app'])) for name in
                   ('lead', 'audit', 'finance', 'viewer', 'other', 'anonymous')}

        def post(name, path, data):
            headers = {} if name == 'anonymous' else env['h'](name)
            return clients[name].post(path, headers=headers, json=data)

        forecast = post('lead', FORECAST, body['forecast'])
        assert forecast.status_code == 200, forecast.text
        f = forecast.json()
        assert f['proof']['stateful_record_saved'] is False
        assert f['proof']['industrial_approval_eligible'] is False

        engineer = post('lead', CASCADE, body)
        auditor = post('audit', CASCADE, body)
        assert engineer.status_code == 200, engineer.text
        assert auditor.status_code == 200, auditor.text
        a, b = engineer.json(), auditor.json()
        assert a['report'] == b['report']
        assert a['proof'] == b['proof']
        assert a['report']['forecast_selected_model'] == f['report']['selected_model']
        assert a['report']['scenarios'][1]['upper_forecast_inflow_cms'] == (
            f['report']['forecast']['point_cms'])
        assert a['report']['target_day_end_utc'] == f['report']['forecast']['target_at']
        assert a['report']['conditional_future_assumptions_flag']
        assert a['proof']['benefit_registry_updated'] is False
        assert a['report']['eligible_for_financial_ledger'] is False
        assert a['report']['monetary_benefit_rub'] is None
        assert a['report']['recommended_dispatch_cms'] is None
        assert a['report']['production_ready'] is False

        assert post('finance', CASCADE, body).status_code == 403
        assert post('viewer', CASCADE, body).status_code == 403
        assert post('anonymous', CASCADE, body).status_code == 401
        assert post('other', CASCADE, body).status_code == 404
        assert post('lead', OTHER_CASCADE, body).status_code == 404
        cross_org = deepcopy(body)
        cross_org['lower']['asset_id'] = 'feeder-b'
        assert post('lead', CASCADE, cross_org).status_code == 404
    assert stored_counts(env) == baseline


def test_revocation_invalidates_existing_sessions_without_harming_other_role(role_lab):
    env = role_lab
    body = cascade_case_v83()
    baseline = stored_counts(env)
    with ExitStack() as stack:
        engineer = stack.enter_context(TestClient(env['app']))
        auditor = stack.enter_context(TestClient(env['app']))
        assert engineer.post(CASCADE, headers=env['h']('lead'), json=body).status_code == 200
        assert auditor.post(CASCADE, headers=env['h']('audit'), json=body).status_code == 200
        with env['db']() as db:
            membership = db.scalar(select(Membership).where(
                Membership.org_id == 'magadan-lab',
                Membership.user_id == env['users']['lead']))
            assert membership is not None
            membership.active = False
            db.commit()
        assert engineer.post(CASCADE, headers=env['h']('lead'), json=body).status_code == 404
        assert auditor.post(CASCADE, headers=env['h']('audit'), json=body).status_code == 200
        with env['db']() as db:
            auditor_user = db.get(User, env['users']['audit'])
            auditor_user.token_version += 1
            db.commit()
        assert auditor.post(CASCADE, headers=env['h']('audit'), json=body).status_code == 401
    assert stored_counts(env) == baseline


def test_peak_violation_cannot_enter_money_or_dispatch_in_any_role(role_lab):
    env = role_lab
    body = cascade_case_v83()
    body['upper_other_local_inflow_cms'] = 1000
    body['upper']['rated_capacity_mw'] = 110
    baseline = stored_counts(env)
    with TestClient(env['app']) as engineer:
        result = engineer.post(CASCADE, headers=env['h']('lead'), json=body)
        assert result.status_code == 200, result.text
        report = result.json()['report']
        assert report['monetary_benefit_rub'] is None
        assert report['recommended_dispatch_cms'] is None
        assert report['eligible_for_financial_ledger'] is False
        assert report['feasible_all_three_synthetic_scenarios'] is False
        assert all(
            'ELECTRICAL_RATED_CAPACITY_EXCEEDED' in s['upper']['violations']
            and s['total_energy_mwh'] is None for s in report['scenarios']
        )
        invalid = deepcopy(body)
        invalid['hydrological_mapping_ref'] = 'SCADA-UNATTESTED-REAL-INPUT'
        assert engineer.post(CASCADE, headers=env['h']('lead'), json=invalid).status_code == 422
    assert stored_counts(env) == baseline
