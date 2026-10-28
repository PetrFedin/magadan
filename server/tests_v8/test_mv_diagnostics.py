from copy import deepcopy
from hydro_api.measurement_quality_v8 import evaluate_quality
from hydro_api.measurement_v79 import MVScreenV79
from tests_v79.test_measurement import sample


def test_research_envelope_and_joint_support_are_reproducible():
    case=MVScreenV79.model_validate(sample())
    q=evaluate_quality(case)
    assert q==evaluate_quality(case)
    assert q['certified_realized_savings'] is False
    assert q['error_envelope_kwh']>=0
    assert q['indicative_lower_kwh']<=q['observed_signed_difference_kwh']<=q['indicative_upper_kwh']
    assert 0<=q['post_joint_support_fraction']<=1
    assert 'NOT_PROBABILISTIC' in q['envelope_kind']


def test_joint_support_can_flag_unseen_combinations_inside_marginal_ranges():
    case=MVScreenV79.model_validate(sample())
    # Mark all post locations at a corner of the rectangle; independent bounds can pass
    # yet the joint load/temperature convex hull can reject.
    d=sample()
    train=d['baseline'][:36]
    maxload=max(x['mean_delivered_load_mw'] for x in train)
    maxtemp=max(x['mean_ambient_temperature_c'] for x in train)
    for row in d['post']:
        row['mean_delivered_load_mw']=maxload
        row['mean_ambient_temperature_c']=maxtemp
    quality=evaluate_quality(MVScreenV79.model_validate(d))
    assert quality['post_windows_outside_joint_support']
    assert quality['certified_realized_savings'] is False


def test_quality_route_uses_auth_and_replays_original(env):
    c=env['client'];h=env['h']
    base='/v79/orgs/magadan-lab/measurement-screens'
    created=c.post(base,headers=h('lead'),json=sample());assert created.status_code==201,created.text
    mid=created.json()['id']
    r=c.get('/v8/orgs/magadan-lab/measurement-screens/'+mid+'/quality',headers=h('audit'))
    assert r.status_code==200,r.text
    assert r.json()['quality']['industrial_approval_eligible'] is False
    assert c.get('/v8/orgs/separate-org/measurement-screens/'+mid+'/quality',headers=h('otheraudit')).status_code==404
