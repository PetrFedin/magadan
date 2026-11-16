from pathlib import Path
from sqlalchemy import select
from hydro_api.storage import GridEconomicDossier,StudyRun,AuditEvent
from hydro_api.main import sha
from .test_radial_and_finance import pair,finance

ROOT=Path(__file__).resolve().parents[1]

def test_pg_migration_dossier_is_tenant_scoped_but_not_natively_accepted():
 sql=(ROOT/'migrations/070_grid_economic_dossiers_v73.sql').read_text()
 for key in ('CREATE TABLE public.grid_economic_dossiers','FORCE ROW LEVEL SECURITY',
             'FOREIGN KEY(org_id,asset_id)','FOREIGN KEY(org_id,baseline_run_id)',
             'FOREIGN KEY(org_id,proposed_run_id)','hk_security.allowed(org_id',
             'hk_private.reject_mutation()','hk_private.audit_business_change()',
             'grid_dossier_synthetic_finance_only','grid_dossier_research_status_only'):
  assert key in sql
 assert 'REFERENCES public.initiatives' not in sql
 assert 'grid_economic_dossiers' in GridEconomicDossier.metadata.tables

def test_append_only_dossier_and_audit_event_number_are_consistent(env):
 ids=pair(env)
 c,h=env['client'],env['h'];url='/v73/orgs/magadan-lab/economic-dossiers'
 with env['db']() as db:
  before=len(db.scalars(select(AuditEvent).where(AuditEvent.org_id=='magadan-lab')).all())
 r=c.post(url,headers=h('finance'),json={'asset_id':'feeder-a','baseline_run_id':ids[0],
  'proposed_run_id':ids[1],'benefit_key':'single-finance-audit','finance':finance()})
 assert r.status_code==201,r.text
 with env['db']() as db:
  after=len(db.scalars(select(AuditEvent).where(AuditEvent.org_id=='magadan-lab')).all())
  assert after-before==1
  d=db.scalar(select(GridEconomicDossier).where(GridEconomicDossier.id==r.json()['dossier_id']))
  assert d.result_sha256==sha(d.result)
  assert d.asset_id=='feeder-a'
  assert d.org_id=='magadan-lab'
  assert d.baseline_run_id!=d.proposed_run_id
