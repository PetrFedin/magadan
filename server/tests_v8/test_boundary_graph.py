"""V8 physical metering identity laboratory tests, including DB constraint enforcement."""
import pytest
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, text
from hydro_api.storage import Asset, Membership
from tests_v79.test_benefit_registry import payload, annual_source, handoff_source

BASE='/v8/orgs/magadan-lab'
BOUNDARY='SYNTHETIC-GRID-MAGADAN-SCOPE-A'
PARENT='SYNTHETIC-GRID-MAGADAN-PARENT'
OTHER='SYNTHETIC-GRID-MAGADAN-SCOPE-B'


def admin(env):
    with env['db']() as db:
        m=db.scalar(select(Membership).where(Membership.user_id==env['users']['manager']))
        m.role='admin';db.commit()
    return env['h']('manager')


def add_asset(env,aid):
    with env['db']() as db:
        db.add(Asset(id=aid,org_id='magadan-lab',name='Synthetic test '+aid,
                     classification='LAB_REFERENCE'));db.commit()


def boundary(env,ident,parent=None,quantity='ELECTRIC_ENERGY'):
    r=env['client'].post(BASE+'/meter-boundaries',headers=admin(env),json={
        'id':ident,'parent_id':parent,'quantity_class':quantity,
        'source_ref':'SYNTHETIC-SCOPE-AUTHORING-RESEARCH-2026'})
    assert r.status_code==201,r.text
    return r.json()


def assign(env,asset_id,bid):
    r=env['client'].post(BASE+'/boundary-asset-assignments',headers=admin(env),json={
      'asset_id':asset_id,'boundary_id':bid,
      'evidence_ref':'SYNTHETIC-SCOPE-ASSIGNMENT-EVIDENCE-2026'})
    assert r.status_code==201,r.text
    return r


def test_alias_assets_same_physical_scope_block_claim(env):
    add_asset(env,'feeder-clone')
    boundary(env,BOUNDARY)
    assign(env,'feeder-a',BOUNDARY)
    assign(env,'feeder-clone',BOUNDARY)
    a=handoff_source(env,'one');b=handoff_source(env,'two')
    # Cannot re-use an engine source pinned to another asset; test source at same asset.
    c=env['client'];h=env['h']
    src=annual_source(env)
    ok=c.post('/v79/orgs/magadan-lab/benefit-reservations',headers=h('finance'),json=payload(src))
    assert ok.status_code==201,ok.text
    # Direct SQL attempts cannot bypass the materialized boundary conflict guard.
    with env['db']() as db:
        from hydro_api.storage import BenefitReservationV79
        from hydro_api.main import sha
        row=BenefitReservationV79(org_id='magadan-lab',asset_id='feeder-clone',
          family='ELECTRIC_ENERGY_COST',start_year=2030,end_year=2031,
          source_kind='GRID_ANNUAL_V78',source_id='SYNTHETIC-OTHER',source_sha256='0'*64,
          source_fingerprint='1'*64,measurement_plan_ref='SYNTHETIC-LAB-SCOPE-PLAN-2026',
          measurement_boundary_description='Another alias of the exact same physical synthetic scope.',
          comparison_normalization='Same profile and metering boundary represented by different assets in the same lab.',
          reservation_sha256='2'*64,created_by=env['users']['finance'])
        db.add(row)
        with pytest.raises(Exception):db.flush()
        db.rollback()
    audit=c.get(BASE+'/boundary-audit',headers=h('viewer'))
    assert audit.status_code==200,audit.text
    assert audit.json()['claim_graph_frozen'] is True
    assert audit.json()['cannot_publish_consolidated_savings'] is True
    # Graph changes after first reservation must fail even in direct SQL.
    attempt=c.post(BASE+'/meter-boundaries',headers=admin(env),json={
      'id':'SYNTHETIC-NEW-LAB-BOUNDARY','quantity_class':'ELECTRIC_ENERGY',
      'source_ref':'SYNTHETIC-MAP-AFTER-CLAIM-2026'})
    assert attempt.status_code==409


def test_parent_child_and_explicit_overlap(env):
    add_asset(env,'feeder-c');add_asset(env,'feeder-d')
    boundary(env,PARENT)
    boundary(env,BOUNDARY,parent=PARENT)
    boundary(env,OTHER)
    assign(env,'feeder-a',BOUNDARY)
    assign(env,'feeder-c',PARENT)
    assign(env,'feeder-d',OTHER)
    r=env['client'].post(BASE+'/boundary-overlaps',headers=admin(env),json={
      'boundary_a':PARENT,'boundary_b':OTHER,
      'evidence_ref':'SYNTHETIC-EXPLICIT-POTENTIAL-OVERLAP-EVIDENCE-2026'})
    assert r.status_code==201,r.text
    # Tree descendants of parent inherit peer overlap, and relations are symmetric.
    with env['db']() as db:
        from hydro_api.storage import BoundaryConflictV8
        edges=db.scalars(select(BoundaryConflictV8).where(
          BoundaryConflictV8.org_id=='magadan-lab')).all()
        pairs={(x.left_id,x.right_id) for x in edges}
        assert (BOUNDARY,PARENT) in pairs and (PARENT,BOUNDARY) in pairs
        assert (OTHER,BOUNDARY) in pairs and (BOUNDARY,OTHER) in pairs
    assert env['client'].get(BASE+'/boundary-audit',headers=env['h']('viewer')).json()['materialized_symmetric_overlap_links']>=9


def test_permissions_class_validation_and_forged_tenant(env):
    c=env['client'];h=env['h']
    data={'id':BOUNDARY,'quantity_class':'ELECTRIC_ENERGY',
          'source_ref':'SYNTHETIC-SCOPE-AUTHORING-RESEARCH-2026'}
    assert c.post(BASE+'/meter-boundaries',headers=h('lead'),json=data).status_code==403
    boundary(env,BOUNDARY)
    assert c.post(BASE+'/boundary-asset-assignments',headers=h('lead'),json={
      'asset_id':'feeder-a','boundary_id':BOUNDARY,
      'evidence_ref':'SYNTHETIC-SCOPE-ASSIGNMENT-EVIDENCE-2026'}).status_code==403
    wrong=c.post(BASE+'/meter-boundaries',headers=admin(env),json={
      'id':OTHER,'parent_id':BOUNDARY,'quantity_class':'HEAT_ENERGY',
      'source_ref':'SYNTHETIC-SCOPE-AUTHORING-RESEARCH-2026'})
    assert wrong.status_code==409
    assert c.post('/v8/orgs/separate-org/meter-boundaries',headers=h('manager'),json=data).status_code==404


def test_physically_incompatible_family_denied_at_db_level(env):
    boundary(env,BOUNDARY,quantity='HEAT_ENERGY')
    assign(env,'feeder-a',BOUNDARY)
    src=annual_source(env)
    r=env['client'].post('/v79/orgs/magadan-lab/benefit-reservations',
       headers=env['h']('finance'),json=payload(src))
    assert r.status_code==409,r.text
    assert 'DUPLICATE_OR_OVERLAPPING' in r.text


def test_graph_frozen_even_if_direct_sql_admin_bypasses_router(env):
    boundary(env,BOUNDARY)
    assign(env,'feeder-a',BOUNDARY)
    src=annual_source(env)
    c=env['client'];h=env['h']
    assert c.post('/v79/orgs/magadan-lab/benefit-reservations',
                  headers=h('finance'),json=payload(src)).status_code==201
    with env['db']() as db:
        from hydro_api.storage import MeterBoundaryV8
        db.add(MeterBoundaryV8(org_id='magadan-lab',id='SYNTHETIC-BYPASS-LAB-SCOPE',
               quantity_class='ELECTRIC_ENERGY',source_ref='SYNTHETIC-POST-CLAIM-MAP-2026',
               created_by=env['users']['manager']))
        with pytest.raises(Exception):db.flush()
        db.rollback()


def test_prior_financial_dossiers_remain_unreconciled(env):
    src=annual_source(env)
    report=env['client'].get(BASE+'/boundary-audit',headers=env['h']('viewer')).json()
    assert report['preexisting_dossier_inventory']['annual_grid_v78']==1
    assert report['unreconciled_legacy_records_upper_bound']>=1
    assert report['cannot_publish_consolidated_savings'] is True
    assert report['lab_reserved_claims']==0


def test_cross_family_electric_overlap_is_conservatively_blocked(env):
    add_asset(env,'grid-district-aggregate')
    boundary(env,PARENT)
    boundary(env,BOUNDARY,parent=PARENT)
    assign(env,'feeder-a',BOUNDARY)
    assign(env,'grid-district-aggregate',PARENT)
    src=annual_source(env)
    assert env['client'].post('/v79/orgs/magadan-lab/benefit-reservations',
        headers=env['h']('finance'),json=payload(src)).status_code==201
    # Separate asset + benefit family can still re-price the SAME physical kWh.
    from hydro_api.storage import BenefitReservationV79
    with env['db']() as db:
        db.add(BenefitReservationV79(org_id='magadan-lab',asset_id='grid-district-aggregate',
            family='GENERATION_VALUE',start_year=2030,end_year=2031,
            source_kind='MAINTENANCE_HANDOFF_V75',source_id='SYNTHETIC-OTHER',
            source_sha256='0'*64,source_fingerprint='1'*64,
            measurement_plan_ref='SYNTHETIC-LAB-PHYSICAL-BOUNDARY-PLAN',
            measurement_boundary_description='Nested district grid measuring a common physical power flow.',
            comparison_normalization='Same physical electricity quantity cannot be monetized twice across distinct effect names.',
            reservation_sha256='2'*64,created_by=env['users']['finance']))
        with pytest.raises(Exception):db.flush()
        db.rollback()


def test_concurrent_alias_reservation_has_at_most_one_success(env):
    add_asset(env,'feeder-sibling')
    boundary(env,PARENT)
    assign(env,'feeder-a',PARENT)
    assign(env,'feeder-sibling',PARENT)
    from hydro_api.storage import BenefitReservationV79
    from sqlalchemy.exc import IntegrityError,OperationalError
    def write(aid):
        with env['db']() as db:
            db.add(BenefitReservationV79(org_id='magadan-lab',asset_id=aid,
                family='ELECTRIC_ENERGY_COST',start_year=2030,end_year=2031,
                source_kind='GRID_ANNUAL_V78',source_id='SYNTHETIC-SOURCE-'+aid,
                source_sha256='0'*64,source_fingerprint=(('1' if aid=='feeder-a' else '2')*64),
                measurement_plan_ref='SYNTHETIC-LAB-PHYSICAL-BOUNDARY-PLAN',
                measurement_boundary_description='Two aliases of the same synthetic feeder energy measurement boundary.',
                comparison_normalization='Strictly matching synthetic load and time conditions on a physically identical feeder boundary.',
                reservation_sha256='a'*64,created_by=env['users']['finance']))
            try:db.commit();return 'ok'
            except (IntegrityError,OperationalError):db.rollback();return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=sorted(pool.map(write,['feeder-a','feeder-sibling']))
    assert outcomes==['blocked','ok'],outcomes
    with env['db']() as db:
        assert db.query(BenefitReservationV79).count()==1


def test_unmapped_asset_cannot_claim_once_scope_graph_is_active(env):
    boundary(env,BOUNDARY)
    src=annual_source(env)
    response=env['client'].post('/v79/orgs/magadan-lab/benefit-reservations',
        headers=env['h']('finance'),json=payload(src))
    assert response.status_code==409,response.text
    assert env['client'].get(BASE+'/boundary-audit',headers=env['h']('viewer')).json()['lab_reserved_claims']==0
