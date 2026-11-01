from copy import deepcopy
from datetime import datetime
import pytest
from hydro_api.storage import Asset
from tests_v82.fixture import daily_flow_fixture


BASE='/v82/orgs/magadan-lab/hydroforecast/evaluate'


def test_api_returns_independently_hashed_and_unpersisted_forecast(env):
    c,h=env['client'],env['h']
    data=daily_flow_fixture()
    r=c.post(BASE,headers=h('lead'),json=data)
    assert r.status_code==200,r.text
    obj=r.json()
    assert obj['org_id']=='magadan-lab'
    assert obj['asset_id']=='feeder-a'
    assert obj['report']['selected_model']
    assert len(obj['report']['holdout_rows'])==28
    assert obj['proof']['stateful_record_saved'] is False
    assert obj['proof']['source_attestation'] is False
    assert obj['proof']['industrial_approval_eligible'] is False
    assert len(obj['proof']['report_sha256'])==64
    assert len(obj['proof']['engine_sha256'])==64
    assert len(obj['proof']['input_sha256'])==64
    again=c.post(BASE,headers=h('audit'),json=data)
    assert again.status_code==200,again.text
    assert again.json()['proof']==obj['proof']
    assert again.json()['report']==obj['report']


def test_api_is_restricted_to_engineer_and_auditor(env):
    c,h=env['client'],env['h']
    d=daily_flow_fixture()
    for actor in ('viewer','finance','manager'):
        assert c.post(BASE,headers=h(actor),json=d).status_code==403
    assert c.post(BASE,json=d).status_code==401
    assert c.post(BASE,headers=h('lead'),json=d).status_code==200


def test_cross_tenant_and_unknown_asset_fail_closed(env):
    c,h=env['client'],env['h']
    d=daily_flow_fixture()
    assert c.post(BASE,headers=h('other'),json=d).status_code==404
    d['asset_id']='nonexistent-object'
    assert c.post(BASE,headers=h('lead'),json=d).status_code==404


def test_real_classified_asset_is_not_used_for_lab(env):
    c,h=env['client'],env['h']
    with env['db']() as db:
        db.add(Asset(id='restricted-real',org_id='magadan-lab',
                     name='Non-synthetic object',classification='REAL'))
        db.commit()
    d=daily_flow_fixture();d['asset_id']='restricted-real'
    r=c.post(BASE,headers=h('lead'),json=d)
    assert r.status_code==409,r.text
    assert 'REAL_ASSET_NOT_PERMITTED_IN_LAB_FORECAST' in r.text


def test_metadata_never_claims_field_operational_use(env):
    r=env['client'].get('/v82/meta/hydroforecast-readiness')
    assert r.status_code==200,r.text
    x=r.json()
    assert x['daily_forecast_generation'] is True
    assert x['statistical_coverage_is_independently_proven'] is False
    assert x['real_magadan_series_used'] is False
    assert x['production_ready'] is False


def test_api_rejects_bad_or_untimely_input(env):
    c,h=env['client'],env['h'];d=daily_flow_fixture()
    d['observations'][0]['source_ref']='SECRET_REAL_HYDROLOGICAL_STATION'
    assert c.post(BASE,headers=h('lead'),json=d).status_code==422
    d=daily_flow_fixture();d['observations'][7]['available_at']='2026-03-09T00:00:00+00:00'
    assert c.post(BASE,headers=h('lead'),json=d).status_code==422


def test_no_mutation_of_stored_studies_or_benefit_reservations(env):
    from sqlalchemy import select, func
    from hydro_api.storage import StudyRun, BenefitReservationV79
    c,h=env['client'],env['h']
    with env['db']() as db:
        before=(db.scalar(select(func.count()).select_from(StudyRun)),
                db.scalar(select(func.count()).select_from(BenefitReservationV79)))
    assert c.post(BASE,headers=h('lead'),json=daily_flow_fixture()).status_code==200
    with env['db']() as db:
        after=(db.scalar(select(func.count()).select_from(StudyRun)),
               db.scalar(select(func.count()).select_from(BenefitReservationV79)))
    assert before==after


def test_api_does_not_return_future_actuals(env):
    r=env['client'].post(BASE,headers=env['h']('lead'),json=daily_flow_fixture())
    data=r.json()['report']
    assert 'actual_cms' not in data['forecast']
    assert 'real_actual_energy_mwh' not in data
    assert data['forecast']['target_at'] > data['issued_at']
