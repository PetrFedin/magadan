"""Synthetic M&V: never actual utility readings or grant evidence."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import text
from hydro_api.measurement_v79 import MVScreenV79,evaluate_mv_screen


def sample(start_year=2027):
    start=datetime(start_year,1,1,tzinfo=timezone.utc)
    commission=start+timedelta(days=65)
    baseline=[];post=[]
    for i in range(48):
        t=start+timedelta(hours=i*24)
        p=3+(i%7)*0.37
        temp=-17+(i*9%22)
        rate=2.6+0.55*p*p+0.09*temp + ((i%5)-2)*0.005
        baseline.append({'started_at':t.isoformat(),'available_at':(t+timedelta(hours=2)).isoformat(),
            'duration_hours':1,'mean_delivered_load_mw':p,'mean_ambient_temperature_c':temp,
            'metered_loss_kwh':rate,'source_ref':'SYNTHETIC-MV-BASELINE-OBS-'+str(i)})
    for i in range(12):
        t=commission+timedelta(days=1+i)
        p=3.1+(i%6)*0.39
        temp=-16+(i*7%20)
        original=2.6+0.55*p*p+0.09*temp
        post.append({'started_at':t.isoformat(),'available_at':(t+timedelta(hours=2)).isoformat(),
            'duration_hours':1,'mean_delivered_load_mw':p,'mean_ambient_temperature_c':temp,
            'metered_loss_kwh':original-1.1,'source_ref':'SYNTHETIC-MV-AFTER-OBS-'+str(i)})
    return {'asset_id':'feeder-a','commissioned_at':commission.isoformat(),
       'report_as_of':(commission+timedelta(days=25)).isoformat(),
       'baseline':baseline,'post':post,
       'measurement_boundary_ref':'SYNTHETIC-MV-BOUNDARY-MAGADAN-001',
       'adjustment_description':
           'Synthetic post-project counterfactual uses pre-project load, load squared and air temperature, chronologically held-out baseline, no actual measurements or expert assessment.'}


def test_mv_model_is_reproducible_and_conservative():
    case=MVScreenV79.model_validate(sample());result=evaluate_mv_screen(case)
    assert result['signed_normalized_difference_kwh']>10
    assert result['verified_actual_savings'] is False
    assert result['benefit_recognition_eligible'] is False
    assert result['train_observations']==36
    assert result['holdout_observations']==12
    assert result==evaluate_mv_screen(case)
    assert result['holdout_rmse_kw']<0.05


def test_mv_future_baseline_leakage_blocked():
    d=sample();d['baseline'][5]['available_at']=d['report_as_of']
    with pytest.raises(ValueError,match='BASELINE_USES_POST'):
        MVScreenV79.model_validate(d)


def test_mv_outside_baseline_support_blocked():
    d=sample();d['post'][0]['mean_delivered_load_mw']=90
    with pytest.raises(ValueError,match='OUT_OF_BASELINE_SUPPORT'):
        evaluate_mv_screen(MVScreenV79.model_validate(d))


def test_mv_unidentifiable_model_blocked():
    d=sample()
    for row in d['baseline']:
        row['mean_delivered_load_mw']=3.5
        row['mean_ambient_temperature_c']=1
    with pytest.raises(ValueError,match='NOT_IDENTIFIABLE'):
        evaluate_mv_screen(MVScreenV79.model_validate(d))


def test_mv_invalid_temporal_intervals_blocked():
    d=sample();d['baseline'][1]['started_at']=d['baseline'][0]['started_at']
    with pytest.raises(ValueError,match='TIMELINE_NOT_ORDERED_OR_DUPLICATE'):
        MVScreenV79.model_validate(d)
    d=sample();d['post'][3]['duration_hours']=300
    with pytest.raises(ValueError):MVScreenV79.model_validate(d)


def test_mv_observation_not_available_before_interval_end():
    d=sample();d['post'][0]['duration_hours']=3
    # Observation is available after 2 hours, but data covers 3 hours.
    with pytest.raises(ValueError,match='MEASUREMENT_AVAILABLE_BEFORE_WINDOW_END'):
        MVScreenV79.model_validate(d)


def test_mv_baseline_window_cannot_cross_commissioning():
    d=sample()
    from datetime import datetime,timezone,timedelta
    commissioned=datetime.fromisoformat(d['commissioned_at'])
    d['baseline'][-1]['started_at']=(commissioned-timedelta(minutes=30)).isoformat()
    d['baseline'][-1]['duration_hours']=1
    d['baseline'][-1]['available_at']=(commissioned+timedelta(minutes=30)).isoformat()
    with pytest.raises(ValueError,match='BASELINE_USES_POST'):
        MVScreenV79.model_validate(d)


def test_mv_post_observation_cannot_cross_report_timestamp():
    d=sample()
    from datetime import datetime,timedelta
    asof=datetime.fromisoformat(d['report_as_of'])
    d['post'][-1]['started_at']=(asof-timedelta(minutes=20)).isoformat()
    d['post'][-1]['duration_hours']=1
    d['post'][-1]['available_at']=(asof+timedelta(minutes=40)).isoformat()
    with pytest.raises(ValueError,match='POST_PERIOD_OUTSIDE_REPORT_TIME'):
        MVScreenV79.model_validate(d)


def test_mv_hour_duration_affects_energy_not_rate():
    d=sample();r=evaluate_mv_screen(MVScreenV79.model_validate(d))
    d['post'][0]['duration_hours']=2
    d['post'][0]['metered_loss_kwh']*=2
    r2=evaluate_mv_screen(MVScreenV79.model_validate(d))
    assert r2['signed_normalized_difference_kwh'] > r['signed_normalized_difference_kwh']


def test_mv_roles_tenants_audit_and_deduplication(env):
    c,h=env['client'],env['h'];url='/v79/orgs/magadan-lab/measurement-screens';d=sample()
    assert c.post(url,headers=h('viewer'),json=d).status_code==403
    res=c.post(url,headers=h('lead'),json=d)
    assert res.status_code==201,res.text
    j=res.json();assert j['report']['verified_actual_savings'] is False
    assert j['report']['signed_normalized_difference_kwh']>0
    assert c.post(url,headers=h('finance'),json=d).status_code==409
    assert c.get(url+'/'+j['id'],headers=h('viewer')).status_code==200
    assert c.post(url+'/'+j['id']+'/reproduce',headers=h('finance')).status_code==403
    r=c.post(url+'/'+j['id']+'/reproduce',headers=h('audit'))
    assert r.status_code==200,r.text
    assert r.json()['audit_reproduced'] is True
    assert c.get('/v79/orgs/separate-org/measurement-screens/'+j['id'],headers=h('otheraudit')).status_code==404
    assert c.get('/v7/orgs/magadan-lab/audit/verify',headers=h('audit')).json()['valid'] is True


def test_mv_immutable_and_tamper_detection(env):
    c,h=env['client'],env['h'];url='/v79/orgs/magadan-lab/measurement-screens'
    id=c.post(url,headers=h('lead'),json=sample()).json()['id']
    with env['db']() as db:
        with pytest.raises(Exception):
            db.execute(text('DELETE FROM measurement_screens_v79 WHERE id=:i'),{'i':id});db.commit()
        db.rollback()
        db.execute(text('DROP TRIGGER lock_measurement_screens_v79_update'))
        db.execute(text("UPDATE measurement_screens_v79 SET report_sha256='"+'0'*64+"' WHERE id=:i"),{'i':id})
        db.commit()
    assert c.get(url+'/'+id,headers=h('audit')).status_code==409


def test_measurement_native_sql_contract():
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'migrations'/'140_measurement_screen_v79.sql'
    sql=path.read_text()
    for token in ('FORCE ROW LEVEL SECURITY','hk_security.allowed',
                  'hk_private.reject_mutation','hk_private.audit_business_change',
                  'SYNTHETIC_MV_RESEARCH_NO_REALIZED_SAVINGS',
                  "benefit_recognition_eligible' IS NOT DISTINCT FROM 'false'"):
        assert token in sql
