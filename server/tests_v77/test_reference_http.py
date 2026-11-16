"""Full HTTP flow, RLS-like tenant check at API layer, append-only SQLite lab."""
import pytest
from sqlalchemy import text
from .test_reference_domain import reported_reference
from tests_v73.test_radial_and_finance import feeder


def make_run(env):
    c,h=env['client'],env['h']
    res=c.post('/v73/orgs/magadan-lab/radial-runs',headers=h('lead'),json={
      'asset_id':'feeder-a','scenario_group':'synthetic_v77_reference',
      'source_ref':'SYNTHETIC-REFERENCE-EXPORT-V77','case':feeder()})
    assert res.status_code==201,res.text
    return res.json()['run_id']


def test_import_export_reproduce_tenant_separation_and_duplicates(env):
    c,h=env['client'],env['h'];id=make_run(env)
    url='/v77/orgs/magadan-lab/grid-reference'
    request=c.get(url+'/request/'+id,headers=h('viewer'))
    assert request.status_code==200,request.text
    assert request.json()['not_field_approved'] is True
    ref=reported_reference()
    assert ref['case_sha256']==request.json()['case_sha256']
    body={'study_id':id,'submission':ref}
    assert c.post(url+'/comparisons',headers=h('viewer'),json=body).status_code==403
    assert c.post(url+'/comparisons',headers=h('finance'),json=body).status_code==403
    result=c.post(url+'/comparisons',headers=h('lead'),json=body)
    assert result.status_code==201,result.text
    cmp_id=result.json()['comparison_id']
    assert result.json()['status']=='LAB_NUMERICAL_MATCH_UNATTESTED'
    assert result.json()['independent_engineering_accepted'] is False
    assert c.post(url+'/comparisons',headers=h('lead'),json=body).status_code==409
    assert c.get(url+'/comparisons/'+cmp_id,headers=h('viewer')).status_code==200
    assert c.get('/v77/orgs/separate-org/grid-reference/comparisons/'+cmp_id,headers=h('other')).status_code==404
    assert c.get('/v77/orgs/separate-org/grid-reference/request/'+id,headers=h('other')).status_code==404
    assert c.post(url+'/comparisons/'+cmp_id+'/reproduce',headers=h('viewer')).status_code==403
    re=c.post(url+'/comparisons/'+cmp_id+'/reproduce',headers=h('audit'))
    assert re.status_code==200,re.text
    assert re.json()['reproduced'] and re.json()['reference_origin_verified'] is False
    assert c.get('/v7/orgs/magadan-lab/audit/verify',headers=h('audit')).json()['valid'] is True


def test_bad_hash_rejected_and_traces_not_inserted(env):
    c,h=env['client'],env['h'];sid=make_run(env)
    x=reported_reference();x['case_sha256']='0'*64
    result=c.post('/v77/orgs/magadan-lab/grid-reference/comparisons',headers=h('lead'),json={'study_id':sid,'submission':x})
    assert result.status_code==422 and 'REFERENCE_CASE_HASH_MISMATCH' in result.text
    with env['db']() as db:
        from hydro_api.storage import GridReferenceComparisonV77
        assert db.query(GridReferenceComparisonV77).count()==0


def test_sqlite_append_only_and_hash_validation(env):
    c,h=env['client'],env['h'];sid=make_run(env);url='/v77/orgs/magadan-lab/grid-reference/comparisons'
    result=c.post(url,headers=h('lead'),json={'study_id':sid,'submission':reported_reference()})
    assert result.status_code==201,result.text
    cmp=result.json()['comparison_id']
    with env['db']() as db:
        with pytest.raises(Exception,match='APPEND_ONLY'):
            db.execute(text('UPDATE grid_reference_comparisons_v77 SET report_sha256=:v WHERE id=:id'),{'v':'0'*64,'id':cmp});db.commit()
        db.rollback()
        with pytest.raises(Exception,match='APPEND_ONLY'):
            db.execute(text('DELETE FROM grid_reference_comparisons_v77 WHERE id=:id'),{'id':cmp});db.commit()
        db.rollback()
        db.execute(text('DROP TRIGGER lock_grid_reference_comparisons_v77_update'))
        db.execute(text('UPDATE grid_reference_comparisons_v77 SET report_sha256=:v WHERE id=:id'),{'v':'0'*64,'id':cmp});db.commit()
    assert c.post(url+'/'+cmp+'/reproduce',headers=h('audit')).status_code==409
