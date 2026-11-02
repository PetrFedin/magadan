"""V8.3 stateless API role, tenant and non-financial boundary checks."""
from copy import deepcopy
from sqlalchemy import select,func
from hydro_api.storage import Asset,StudyRun,BenefitReservationV79
from tests_v83.fixture import cascade_case_v83

ENDPOINT='/v83/orgs/magadan-lab/cascade/forecast-screen'


def permitted(env):
    with env['db']() as db:
        db.add(Asset(id='v83-lower',org_id='magadan-lab',name='SYNTHETIC SECOND RESERVOIR',
                     classification='LAB_REFERENCE'))
        db.commit()


def test_authorized_two_assets_is_deterministic_and_hashed(env):
    permitted(env)
    c,h=env['client'],env['h'];body=cascade_case_v83()
    r=c.post(ENDPOINT,headers=h('lead'),json=body)
    assert r.status_code==200,r.text
    obj=r.json()
    assert obj['org_id']=='magadan-lab'
    assert obj['upper_asset_id']=='feeder-a'
    assert obj['lower_asset_id']=='v83-lower'
    assert len(obj['report']['scenarios'])==3
    assert obj['report']['feasible_all_three_synthetic_scenarios']
    assert obj['report']['monetary_benefit_rub'] is None
    assert obj['report']['eligible_for_financial_ledger'] is False
    assert obj['proof']['stateful_record_saved'] is False
    assert obj['proof']['benefit_registry_updated'] is False
    assert obj['proof']['native_postgresql17_rls_verified'] is False
    for key in ('input_sha256','report_sha256','engine_sha256','forecast_engine_sha256'):
        assert len(obj['proof'][key])==64
    x=c.post(ENDPOINT,headers=h('audit'),json=body)
    assert x.status_code==200,x.text
    assert x.json()['report']==obj['report']
    assert x.json()['proof']==obj['proof']


def test_roles_and_not_logged_in_are_denied(env):
    permitted(env);c,h=env['client'],env['h'];d=cascade_case_v83()
    assert c.post(ENDPOINT,json=d).status_code==401
    for role in ('finance','viewer','manager'):
        assert c.post(ENDPOINT,headers=h(role),json=d).status_code==403
    assert c.post(ENDPOINT,headers=h('lead'),json=d).status_code==200


def test_other_tenant_assets_cannot_be_read(env):
    c,h=env['client'],env['h'];d=cascade_case_v83()
    # feeder-b exists, but only in separate-org. The API must not leak it.
    d['lower']['asset_id']='feeder-b'
    assert c.post(ENDPOINT,headers=h('lead'),json=d).status_code==404
    assert c.post(ENDPOINT,headers=h('other'),json=d).status_code==404
    assert c.post('/v83/orgs/separate-org/cascade/forecast-screen',headers=h('lead'),json=d).status_code==404


def test_real_classified_or_missing_asset_is_rejected(env):
    permitted(env);c,h=env['client'],env['h'];d=cascade_case_v83()
    with env['db']() as db:
        a=db.scalar(select(Asset).where(Asset.id=='v83-lower',Asset.org_id=='magadan-lab'))
        a.classification='REAL';db.commit()
    assert c.post(ENDPOINT,headers=h('lead'),json=d).status_code==409
    d['lower']['asset_id']='absent-case'
    assert c.post(ENDPOINT,headers=h('lead'),json=d).status_code==404


def test_forecast_horizon_and_wrong_source_fail_closed(env):
    permitted(env);c,h=env['client'],env['h']
    d=cascade_case_v83();d['forecast']['horizon_days']=1
    assert c.post(ENDPOINT,headers=h('lead'),json=d).status_code==422
    d=cascade_case_v83();d['hydrological_mapping_ref']='REAL-INTERNAL-SCADA'
    assert c.post(ENDPOINT,headers=h('lead'),json=d).status_code==422
    d=cascade_case_v83();d['water_density_kg_m3']=True
    assert c.post(ENDPOINT,headers=h('lead'),json=d).status_code==422


def test_produced_report_does_not_mutate_saved_studies_or_benefit_ledger(env):
    permitted(env);c,h=env['client'],env['h']
    with env['db']() as db:
        before=(db.scalar(select(func.count()).select_from(StudyRun)),
                db.scalar(select(func.count()).select_from(BenefitReservationV79)))
    assert c.post(ENDPOINT,headers=h('audit'),json=cascade_case_v83()).status_code==200
    with env['db']() as db:
        after=(db.scalar(select(func.count()).select_from(StudyRun)),
               db.scalar(select(func.count()).select_from(BenefitReservationV79)))
    assert before==after


def test_metadata_never_claims_real_world_ready(env):
    c=env['client'];r=c.get('/v83/meta/cascade-readiness')
    assert r.status_code==200,r.text
    d=r.json()
    assert d['forecast_horizon_eligible_days']==[2]
    assert not d['real_hydrological_reservoir_curves_verified']
    assert not d['financial_benefit_certified']
    assert not d['production_ready']


def test_api_rejects_tampered_curve_and_untrusted_future_observation(env):
    permitted(env);c,h=env['client'],env['h']
    d=cascade_case_v83();d['upper']['storage_curve'][-1]['volume_m3']=900_000_000
    assert c.post(ENDPOINT,headers=h('lead'),json=d).status_code==422
    d=cascade_case_v83();d['forecast']['observations'][-1]['available_at']='2033-01-01T00:00:00+00:00'
    assert c.post(ENDPOINT,headers=h('lead'),json=d).status_code==422


def test_v832_peak_capacity_failure_does_not_claim_financial_energy(env):
    permitted(env)
    c,h=env['client'],env['h'];body=cascade_case_v83()
    body['upper_other_local_inflow_cms']=1000
    body['upper']['rated_capacity_mw']=110
    r=c.post(ENDPOINT,headers=h('lead'),json=body)
    assert r.status_code==200,r.text
    report=r.json()['report']
    assert report['production_ready'] is False
    assert report['monetary_benefit_rub'] is None
    assert report['eligible_for_financial_ledger'] is False
    assert not report['feasible_all_three_synthetic_scenarios']
    assert all(
        'ELECTRICAL_RATED_CAPACITY_EXCEEDED' in item['upper']['violations']
        and item['total_energy_mwh'] is None
        for item in report['scenarios']
    )
    assert r.json()['proof']['benefit_registry_updated'] is False
