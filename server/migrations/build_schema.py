"""Generate inspectable PostgreSQL DDL from the preserved V7 ORM metadata.
This is a compile check only. It is NOT a PostgreSQL execution test.
"""
from pathlib import Path
import sys
if "--preview" not in sys.argv:
    raise SystemExit("HISTORICAL_MIGRATIONS_FROZEN: use --preview for an isolated schema draft; never rewrite 001/020")
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import postgresql
from hydro_api.storage import Base
root=Path(__file__).parent
output=root/"preview_current_orm_NOT_A_MIGRATION"
output.mkdir(exist_ok=True)
header='''-- Dedicated empty database. Role passwords must be set out-of-band by bootstrap.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public') THEN
  RAISE EXCEPTION 'REFUSE_NONEMPTY_DATABASE'; END IF;
END $$;
CREATE ROLE hk_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE hk_app LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE hk_authenticator LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE hk_exporter LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO hk_app,hk_authenticator,hk_exporter,hk_owner;
'''
ddl=[header]
for t in Base.metadata.sorted_tables:
 ddl += [str(CreateTable(t).compile(dialect=postgresql.dialect()))+';',
         f'ALTER TABLE public.{t.name} OWNER TO hk_owner;']
 ddl += [str(CreateIndex(i).compile(dialect=postgresql.dialect()))+';' for i in t.indexes]
(output/'001_schema.sql').write_text('\n'.join(ddl)+'\n')

parts=['-- RLS with a transaction-bound signed context; no trust in plain org_id GUC.']
for table in Base.metadata.sorted_tables:
 t=table.name
 parts += [f'ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY;',f'ALTER TABLE public.{t} FORCE ROW LEVEL SECURITY;',
  f'CREATE POLICY owner_{t} ON public.{t} TO hk_owner USING(true) WITH CHECK(true);']
 if t=='users': expr='id=hk_security.actor()'
 elif t=='memberships': expr='user_id=hk_security.actor() AND active'
 elif t=='organizations':expr='hk_security.allowed(id)'
 else:expr='hk_security.allowed(org_id)'
 parts += [f'CREATE POLICY read_{t} ON public.{t} FOR SELECT TO hk_app USING({expr});',
           f'GRANT SELECT ON public.{t} TO hk_app;']
parts += ['CREATE POLICY auth_principals ON public.users FOR SELECT TO hk_authenticator USING(true);']
policy={
 'assets':"hk_security.allowed(org_id,ARRAY['admin','engineer'])",
 'evidence':"hk_security.allowed(org_id,CASE kind WHEN 'financial_report' THEN ARRAY['economist'] WHEN 'approval_memo' THEN ARRAY['manager'] WHEN 'outcome_report' THEN ARRAY['auditor'] ELSE ARRAY['engineer'] END) AND created_by=hk_security.actor()",
 'model_versions':"hk_security.allowed(org_id,ARRAY['engineer']) AND created_by=hk_security.actor()",
 'evidence_reviews':"hk_security.allowed(org_id,ARRAY['auditor']) AND actor_id=hk_security.actor() AND EXISTS(SELECT 1 FROM public.evidence e WHERE e.org_id=evidence_reviews.org_id AND e.id=evidence_id AND e.created_by<>hk_security.actor())",
 'model_reviews':"hk_security.allowed(org_id,ARRAY['auditor']) AND actor_id=hk_security.actor() AND EXISTS(SELECT 1 FROM public.model_versions m WHERE m.org_id=model_reviews.org_id AND m.id=model_id AND m.created_by<>hk_security.actor())",
 'calculation_runs':"hk_security.allowed(org_id,ARRAY['engineer']) AND created_by=hk_security.actor() AND EXISTS(SELECT 1 FROM public.model_reviews mr WHERE mr.org_id=calculation_runs.org_id AND mr.model_id=calculation_runs.model_id AND mr.accepted) AND EXISTS(SELECT 1 FROM public.evidence_reviews er WHERE er.org_id=calculation_runs.org_id AND er.evidence_id=calculation_runs.evidence_id AND er.accepted)",
 'initiatives':"hk_security.allowed(org_id,ARRAY['engineer']) AND created_by=hk_security.actor() AND state='draft' AND revision=0 AND engineer_approver IS NULL AND finance_approver IS NULL",
 'initiative_evidence':"hk_security.allowed(org_id,ARRAY['engineer','economist','manager','auditor']) AND EXISTS(SELECT 1 FROM public.initiatives i JOIN public.evidence e ON e.org_id=i.org_id AND e.asset_id=i.asset_id JOIN public.evidence_reviews r ON r.evidence_id=e.id AND r.org_id=e.org_id WHERE i.id=initiative_id AND i.org_id=initiative_evidence.org_id AND e.id=initiative_evidence.evidence_id AND r.accepted AND i.state<>'verified' AND (e.kind NOT IN ('engineering_report','financial_report','outcome_report') OR e.payload->>'run_id'=i.run_id))",
 'transitions':"hk_security.allowed(org_id) AND actor_id=hk_security.actor() AND EXISTS(SELECT 1 FROM public.initiatives i WHERE i.org_id=transitions.org_id AND i.id=initiative_id AND i.revision=transitions.revision AND i.state=to_state)"
}
for t,expr in policy.items():
 parts += [f'CREATE POLICY insert_{t} ON public.{t} FOR INSERT TO hk_app WITH CHECK({expr});',
           f'GRANT INSERT ON public.{t} TO hk_app;']
parts += ["CREATE POLICY update_initiatives ON public.initiatives FOR UPDATE TO hk_app USING(hk_security.allowed(org_id)) WITH CHECK(hk_security.allowed(org_id));",
 'GRANT UPDATE(state,revision,engineer_approver,finance_approver) ON public.initiatives TO hk_app;']
for t in ['assets','evidence','model_versions','calculation_runs','initiatives']:
 parts += [f'ALTER TABLE public.{t} ADD CONSTRAINT {t}_tenant_id UNIQUE(org_id,id);']
for t in ['evidence','model_versions','calculation_runs']:
 parts += [f'ALTER TABLE public.{t} ADD CONSTRAINT {t}_tenant_asset_id UNIQUE(org_id,asset_id,id);']
fks=[('evidence','asset_id','assets'),('model_versions','asset_id','assets'),('evidence_reviews','evidence_id','evidence'),
     ('model_reviews','model_id','model_versions'),('calculation_runs','asset_id','assets'),('initiatives','asset_id','assets'),
     ('initiative_evidence','initiative_id','initiatives'),('initiative_evidence','evidence_id','evidence'),('transitions','initiative_id','initiatives')]
for t,col,target in fks:
 parts += [f'ALTER TABLE public.{t} ADD CONSTRAINT {t}_{col}_tenant_fk FOREIGN KEY(org_id,{col}) REFERENCES public.{target}(org_id,id);']
for t,col,target in [('calculation_runs','model_id','model_versions'),('calculation_runs','evidence_id','evidence'),('initiatives','run_id','calculation_runs')]:
 parts += [f'ALTER TABLE public.{t} ADD CONSTRAINT {t}_{col}_asset_fk FOREIGN KEY(org_id,asset_id,{col}) REFERENCES public.{target}(org_id,asset_id,id);']
parts += [
 "ALTER TABLE public.memberships ADD CONSTRAINT known_role CHECK(role IN ('engineer','economist','manager','auditor','admin','viewer'));",
 "ALTER TABLE public.evidence_reviews ADD CONSTRAINT single_evidence_review UNIQUE(org_id,evidence_id);",
 "ALTER TABLE public.model_reviews ADD CONSTRAINT single_model_review UNIQUE(org_id,model_id);",
 "ALTER TABLE public.transitions ADD CONSTRAINT unique_transition_revision UNIQUE(org_id,initiative_id,revision);",
 "ALTER TABLE public.audit_events ADD CONSTRAINT valid_audit_seq CHECK(seq>0 AND timestamp_ms>0);"
]
(output/'020_rls_and_links.sql').write_text('\n'.join(parts)+'\n')
print('Wrote NON-APPLICABLE ORM PREVIEW only. Historical migrations remain frozen; not an upgrade path.')
