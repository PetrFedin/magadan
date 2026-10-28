import json
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, BigInteger, Float, ForeignKey, Boolean, JSON, DateTime, Text, UniqueConstraint, ForeignKeyConstraint, event, text
from sqlalchemy.orm import declarative_base, mapped_column, sessionmaker, Mapped

Base=declarative_base()
def now():return datetime.now(timezone.utc)

def new_id():
    from uuid import uuid4
    return str(uuid4())

class Organization(Base):
    __tablename__='organizations'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    name:Mapped[str]=mapped_column(String,nullable=False)
    audit_seq:Mapped[int]=mapped_column(Integer,nullable=False,default=0)
    audit_tip:Mapped[str]=mapped_column(String,nullable=False,default='GENESIS')

class User(Base):
    __tablename__='users'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    email:Mapped[str]=mapped_column(String,unique=True,nullable=False,index=True)
    password_hash:Mapped[str]=mapped_column(Text,nullable=False)
    active:Mapped[bool]=mapped_column(Boolean,default=True,nullable=False)
    token_version:Mapped[int]=mapped_column(Integer,default=0,nullable=False)

class Membership(Base):
    __tablename__='memberships'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    user_id:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False,index=True)
    role:Mapped[str]=mapped_column(String,nullable=False)
    active:Mapped[bool]=mapped_column(Boolean,default=True,nullable=False)
    __table_args__=(UniqueConstraint('org_id','user_id',name='uq_org_user'),)

class Asset(Base):
    __tablename__='assets'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    name:Mapped[str]=mapped_column(String,nullable=False)
    classification:Mapped[str]=mapped_column(String,default='LAB_REFERENCE',nullable=False)
    __table_args__=(UniqueConstraint('org_id','id',name='uq_assets_org_id_sqlite_lab'),)

class Evidence(Base):
    __tablename__='evidence'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    asset_id:Mapped[str]=mapped_column(String,ForeignKey('assets.id'),nullable=False)
    kind:Mapped[str]=mapped_column(String,nullable=False)
    source_ref:Mapped[str]=mapped_column(String,nullable=False)
    payload:Mapped[dict]=mapped_column(JSON,nullable=False)
    content_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class EvidenceReview(Base):
    __tablename__='evidence_reviews'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    evidence_id:Mapped[str]=mapped_column(String,ForeignKey('evidence.id'),nullable=False)
    actor_id:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    accepted:Mapped[bool]=mapped_column(Boolean,nullable=False)
    note:Mapped[str]=mapped_column(Text,nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class ModelVersion(Base):
    __tablename__='model_versions'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    asset_id:Mapped[str]=mapped_column(String,ForeignKey('assets.id'),nullable=False)
    algorithm:Mapped[str]=mapped_column(String,nullable=False)
    params:Mapped[dict]=mapped_column(JSON,nullable=False)
    content_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class ModelReview(Base):
    __tablename__='model_reviews'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    model_id:Mapped[str]=mapped_column(String,ForeignKey('model_versions.id'),nullable=False)
    actor_id:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    accepted:Mapped[bool]=mapped_column(Boolean,nullable=False)
    note:Mapped[str]=mapped_column(Text,nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class CalculationRun(Base):
    __tablename__='calculation_runs'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    asset_id:Mapped[str]=mapped_column(String,ForeignKey('assets.id'),nullable=False)
    model_id:Mapped[str]=mapped_column(String,ForeignKey('model_versions.id'),nullable=False)
    evidence_id:Mapped[str]=mapped_column(String,ForeignKey('evidence.id'),nullable=False)
    input_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    result_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    result:Mapped[dict]=mapped_column(JSON,nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Initiative(Base):
    __tablename__='initiatives'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    asset_id:Mapped[str]=mapped_column(String,ForeignKey('assets.id'),nullable=False)
    run_id:Mapped[str]=mapped_column(String,ForeignKey('calculation_runs.id'),nullable=False)
    title:Mapped[str]=mapped_column(String,nullable=False)
    effect_key:Mapped[str]=mapped_column(String,nullable=False)
    state:Mapped[str]=mapped_column(String,nullable=False,default='draft')
    revision:Mapped[int]=mapped_column(Integer,nullable=False,default=0)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    engineer_approver:Mapped[str|None]=mapped_column(String,nullable=True)
    finance_approver:Mapped[str|None]=mapped_column(String,nullable=True)
    __table_args__=(UniqueConstraint('org_id','effect_key',name='uq_org_effect'),)

class InitiativeEvidence(Base):
    __tablename__='initiative_evidence'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    initiative_id:Mapped[str]=mapped_column(String,ForeignKey('initiatives.id'),nullable=False)
    evidence_id:Mapped[str]=mapped_column(String,ForeignKey('evidence.id'),nullable=False)
    __table_args__=(UniqueConstraint('initiative_id','evidence_id',name='uq_initiative_evidence'),)

class Transition(Base):
    __tablename__='transitions'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    initiative_id:Mapped[str]=mapped_column(String,ForeignKey('initiatives.id'),nullable=False)
    from_state:Mapped[str]=mapped_column(String,nullable=False)
    to_state:Mapped[str]=mapped_column(String,nullable=False)
    revision:Mapped[int]=mapped_column(Integer,nullable=False)
    actor_id:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    audit_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class AuditEvent(Base):
    __tablename__='audit_events'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    seq:Mapped[int]=mapped_column(Integer,nullable=False)
    actor_id:Mapped[str]=mapped_column(String,nullable=False)
    event_type:Mapped[str]=mapped_column(String,nullable=False)
    object_type:Mapped[str]=mapped_column(String,nullable=False)
    object_id:Mapped[str]=mapped_column(String,nullable=False)
    payload:Mapped[dict]=mapped_column(JSON,nullable=False)
    previous_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    event_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    timestamp_ms:Mapped[int]=mapped_column(BigInteger,nullable=False)
    __table_args__=(UniqueConstraint('org_id','seq',name='uq_org_seq'),)



class StudyRun(Base):
    """Append-only exploratory study: never an authorized investment decision."""
    __tablename__='study_runs'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    asset_id:Mapped[str]=mapped_column(String,ForeignKey('assets.id'),nullable=False)
    module:Mapped[str]=mapped_column(String(40),nullable=False)
    source_ref:Mapped[str]=mapped_column(String(220),nullable=False)
    scenario_group:Mapped[str]=mapped_column(String(100),nullable=False)
    case_payload:Mapped[dict]=mapped_column(JSON,nullable=False)
    input_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    result:Mapped[dict]=mapped_column(JSON,nullable=False)
    result_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    engine_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint('org_id','id',name='study_runs_tenant_id'),)


class GridEconomicDossier(Base):
    """Synthetic evidence-linked network economics; NEVER a real investment approval."""
    __tablename__='grid_economic_dossiers'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    asset_id:Mapped[str]=mapped_column(String,ForeignKey('assets.id'),nullable=False)
    baseline_run_id:Mapped[str]=mapped_column(String,ForeignKey('study_runs.id'),nullable=False)
    proposed_run_id:Mapped[str]=mapped_column(String,ForeignKey('study_runs.id'),nullable=False)
    benefit_key:Mapped[str]=mapped_column(String(100),nullable=False)
    finance_input:Mapped[dict]=mapped_column(JSON,nullable=False)
    result:Mapped[dict]=mapped_column(JSON,nullable=False)
    result_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    pinned_engine_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(
        UniqueConstraint('org_id','id',name='grid_dossier_tenant_id'),
        UniqueConstraint('org_id','benefit_key',name='grid_dossier_unique_effect_key'),
        UniqueConstraint('org_id','baseline_run_id','proposed_run_id',name='grid_dossier_unique_pair'),
    )



class ResearchProgramme(Base):
    """Append-only research envelope; NEVER an industrial investment approval."""
    __tablename__='research_programmes'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    reference_code:Mapped[str]=mapped_column(String(80),nullable=False)
    title:Mapped[str]=mapped_column(String(180),nullable=False)
    purpose:Mapped[str]=mapped_column(Text,nullable=False)
    capital_input:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    snapshot:Mapped[dict]=mapped_column(JSON,nullable=False)
    snapshot_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(
        UniqueConstraint('org_id','reference_code',name='uq_programme_org_reference'),
        UniqueConstraint('org_id','id',name='uq_programme_org_id'),
    )

class ResearchProgrammeStudy(Base):
    __tablename__='research_programme_studies'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,nullable=False)
    programme_id:Mapped[str]=mapped_column(String,nullable=False)
    study_id:Mapped[str]=mapped_column(String,nullable=False)
    __table_args__=(
        UniqueConstraint('org_id','programme_id','study_id',name='uq_programme_study'),
        ForeignKeyConstraint(['org_id','programme_id'],['research_programmes.org_id','research_programmes.id']),
        ForeignKeyConstraint(['org_id','study_id'],['study_runs.org_id','study_runs.id']),
    )

class ResearchProgrammeFinance(Base):
    __tablename__='research_programme_finance'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,nullable=False)
    programme_id:Mapped[str]=mapped_column(String,nullable=False)
    dossier_id:Mapped[str]=mapped_column(String,nullable=False)
    __table_args__=(
        UniqueConstraint('org_id','programme_id','dossier_id',name='uq_programme_finance'),
        ForeignKeyConstraint(['org_id','programme_id'],['research_programmes.org_id','research_programmes.id']),
        ForeignKeyConstraint(['org_id','dossier_id'],['grid_economic_dossiers.org_id','grid_economic_dossiers.id']),
    )

class ResearchProgrammeLink(Base):
    __tablename__='research_programme_links'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,nullable=False)
    programme_id:Mapped[str]=mapped_column(String,nullable=False)
    from_study_id:Mapped[str]=mapped_column(String,nullable=False)
    to_study_id:Mapped[str]=mapped_column(String,nullable=False)
    relationship:Mapped[str]=mapped_column(String(70),nullable=False)
    __table_args__=(
        UniqueConstraint('org_id','programme_id','from_study_id','to_study_id','relationship',name='uq_programme_link'),
        ForeignKeyConstraint(['org_id','programme_id'],['research_programmes.org_id','research_programmes.id']),
        ForeignKeyConstraint(['org_id','from_study_id'],['study_runs.org_id','study_runs.id']),
        ForeignKeyConstraint(['org_id','to_study_id'],['study_runs.org_id','study_runs.id']),
    )


class ResearchHandoff(Base):
    """Immutable synthetic calculation handoff, NOT industrial approval evidence."""
    __tablename__='research_handoffs'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    asset_id:Mapped[str]=mapped_column(String,ForeignKey('assets.id'),nullable=False)
    kind:Mapped[str]=mapped_column(String(40),nullable=False)
    left_study_id:Mapped[str]=mapped_column(String,nullable=False)
    right_study_id:Mapped[str|None]=mapped_column(String,nullable=True)
    programme_id:Mapped[str|None]=mapped_column(String,nullable=True)
    input_payload:Mapped[dict]=mapped_column(JSON,nullable=False)
    input_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    snapshot:Mapped[dict]=mapped_column(JSON,nullable=False)
    snapshot_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    engine_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(
        UniqueConstraint('org_id','id',name='uq_handoff_tenant_id'),
        UniqueConstraint('org_id','kind','input_sha256',name='uq_handoff_tenant_kind_source'),
        ForeignKeyConstraint(['org_id','left_study_id'],['study_runs.org_id','study_runs.id']),
        ForeignKeyConstraint(['org_id','right_study_id'],['study_runs.org_id','study_runs.id']),
        ForeignKeyConstraint(['org_id','programme_id'],['research_programmes.org_id','research_programmes.id']),
    )


class GridReferenceComparisonV77(Base):
    """Append-only, untrusted reported reference values, not engineering certification."""
    __tablename__='grid_reference_comparisons_v77'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    asset_id:Mapped[str]=mapped_column(String,nullable=False)
    study_id:Mapped[str]=mapped_column(String,nullable=False)
    source_input_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    submission:Mapped[dict]=mapped_column(JSON,nullable=False)
    submission_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    report:Mapped[dict]=mapped_column(JSON,nullable=False)
    report_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    engine_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(
        UniqueConstraint('org_id','id',name='uq_ref_v77_org_id'),
        UniqueConstraint('org_id','study_id','submission_sha256',name='uq_ref_v77_same_source'),
        ForeignKeyConstraint(['org_id','asset_id'],['assets.org_id','assets.id']),
        ForeignKeyConstraint(['org_id','study_id'],['study_runs.org_id','study_runs.id']),
    )

def setup_engine(url):
    kw={'connect_args':{'check_same_thread':False, 'timeout':20}} if url.startswith('sqlite') else {}
    engine=create_engine(url,**kw)
    if url.startswith('sqlite'):
        @event.listens_for(engine,'connect')
        def sqlite_pragma(dbapi_conn, _):
            cur=dbapi_conn.cursor(); cur.execute('PRAGMA foreign_keys=ON');cur.execute('PRAGMA busy_timeout=20000');cur.close()
    Base.metadata.create_all(engine)
    if url.startswith('sqlite'):
        with engine.begin() as conn:
            for table in ['audit_events','transitions','calculation_runs','evidence','evidence_reviews','model_versions','model_reviews','initiative_evidence','study_runs','grid_economic_dossiers','research_programmes','research_programme_studies','research_programme_finance','research_programme_links','research_handoffs','assurance_packs_v76','grid_reference_comparisons_v77','grid_annual_dossiers_v78','benefit_reservations_v79','measurement_screens_v79','meter_boundaries_v8','boundary_assets_v8','boundary_conflicts_v8']:
                conn.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS lock_{table}_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END")
                conn.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS lock_{table}_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END")
            conn.exec_driver_sql("DROP TRIGGER IF EXISTS guard_benefit_overlap_v79")
            conn.exec_driver_sql("""CREATE TRIGGER guard_benefit_overlap_v79
                BEFORE INSERT ON benefit_reservations_v79
                BEGIN
                  SELECT RAISE(ABORT,'BENEFIT_BOUNDARY_PERIOD_OVERLAP')
                  WHERE EXISTS (
                    SELECT 1 FROM benefit_reservations_v79 x
                    WHERE x.org_id=NEW.org_id
                    AND (x.family=NEW.family
                    OR (x.family IN ('ELECTRIC_ENERGY_COST','GENERATION_VALUE')
                        AND NEW.family IN ('ELECTRIC_ENERGY_COST','GENERATION_VALUE'))
                    OR (x.family IN ('MAINTENANCE_COST','RELIABILITY_RISK')
                        AND NEW.family IN ('MAINTENANCE_COST','RELIABILITY_RISK')))
                    AND x.start_year<=NEW.end_year
                    AND x.end_year>=NEW.start_year
                    AND (x.asset_id=NEW.asset_id OR EXISTS(
                      SELECT 1 FROM boundary_conflicts_v8 c
                      JOIN boundary_assets_v8 a ON a.org_id=c.org_id AND a.boundary_id=c.left_id
                      JOIN boundary_assets_v8 b ON b.org_id=c.org_id AND b.boundary_id=c.right_id
                      WHERE c.org_id=NEW.org_id AND a.asset_id=NEW.asset_id AND b.asset_id=x.asset_id
                    ))
                  );
                END""")
            conn.exec_driver_sql("""CREATE TRIGGER IF NOT EXISTS guard_benefit_mapped_scope_v8
                BEFORE INSERT ON benefit_reservations_v79 BEGIN
                  SELECT RAISE(ABORT,'UNMAPPED_PHYSICAL_SCOPE_CANNOT_RESERVE')
                  WHERE EXISTS(SELECT 1 FROM meter_boundaries_v8 WHERE org_id=NEW.org_id)
                    AND NOT EXISTS(SELECT 1 FROM boundary_assets_v8
                                   WHERE org_id=NEW.org_id AND asset_id=NEW.asset_id);
                END""")
            conn.exec_driver_sql("""CREATE TRIGGER IF NOT EXISTS guard_benefit_quantity_v8
                BEFORE INSERT ON benefit_reservations_v79 BEGIN
                  SELECT RAISE(ABORT,'BOUNDARY_QUANTITY_CLASS_MISMATCH')
                  WHERE EXISTS(SELECT 1 FROM boundary_assets_v8 a
                     JOIN meter_boundaries_v8 b ON b.org_id=a.org_id AND b.id=a.boundary_id
                     WHERE a.org_id=NEW.org_id AND a.asset_id=NEW.asset_id AND
                     b.quantity_class != CASE
                       WHEN NEW.family IN ('ELECTRIC_ENERGY_COST','GENERATION_VALUE') THEN 'ELECTRIC_ENERGY'
                       WHEN NEW.family='HEAT_ENERGY_COST' THEN 'HEAT_ENERGY'
                       WHEN NEW.family IN ('MAINTENANCE_COST','RELIABILITY_RISK') THEN 'EQUIPMENT_MAINTENANCE'
                       ELSE 'FINANCIAL_PROCESS' END);
                END""")
            for table in ('meter_boundaries_v8','boundary_assets_v8','boundary_conflicts_v8'):
                conn.exec_driver_sql(f"""CREATE TRIGGER IF NOT EXISTS freeze_{table}_after_claims
                    BEFORE INSERT ON {table} BEGIN
                    SELECT RAISE(ABORT,'BOUNDARY_GRAPH_FROZEN_AFTER_FIRST_CLAIM')
                    WHERE EXISTS(SELECT 1 FROM benefit_reservations_v79 WHERE org_id=NEW.org_id);
                    END""")
    return engine,sessionmaker(engine,expire_on_commit=False)

class AssurancePackV76(Base):
    """Version-pinned lab financial/engineering packet, never field acceptance."""
    __tablename__='assurance_packs_v76'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    programme_id:Mapped[str]=mapped_column(String,nullable=False)
    reference_code:Mapped[str]=mapped_column(String(100),nullable=False)
    benefit_key:Mapped[str]=mapped_column(String(100),nullable=False)
    source_bundle_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    input_payload:Mapped[dict]=mapped_column(JSON,nullable=False)
    input_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    snapshot:Mapped[dict]=mapped_column(JSON,nullable=False)
    snapshot_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    engine_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(
        UniqueConstraint('org_id','id',name='uq_assurance_v76_tenant_id'),
        UniqueConstraint('org_id','reference_code',name='uq_assurance_v76_reference'),
        UniqueConstraint('org_id','benefit_key',name='uq_assurance_v76_benefit'),
        UniqueConstraint('org_id','programme_id','source_bundle_sha256',name='uq_assurance_v76_source_bundle'),
        ForeignKeyConstraint(['org_id','programme_id'],['research_programmes.org_id','research_programmes.id']),
    )

class GridAnnualDossierV78(Base):
    """Single-intervention, synthetic physically priced DCF; NEVER an approval record."""
    __tablename__='grid_annual_dossiers_v78'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    asset_id:Mapped[str]=mapped_column(String,nullable=False)
    programme_id:Mapped[str]=mapped_column(String,nullable=False)
    baseline_run_id:Mapped[str]=mapped_column(String,nullable=False)
    proposed_run_id:Mapped[str]=mapped_column(String,nullable=False)
    benefit_key:Mapped[str]=mapped_column(String(100),nullable=False)
    source_bundle_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    finance_input:Mapped[dict]=mapped_column(JSON,nullable=False)
    input_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    report:Mapped[dict]=mapped_column(JSON,nullable=False)
    report_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    engine_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(
        UniqueConstraint('org_id','id',name='grid_dcf_v78_org_id'),
        UniqueConstraint('org_id','programme_id',name='grid_dcf_v78_unique_wbs_single_measure'),
        UniqueConstraint('org_id','benefit_key',name='grid_dcf_v78_unique_effect'),
        UniqueConstraint('org_id','baseline_run_id','proposed_run_id',name='grid_dcf_v78_unique_pair'),
        ForeignKeyConstraint(['org_id','asset_id'],['assets.org_id','assets.id']),
        ForeignKeyConstraint(['org_id','programme_id'],['research_programmes.org_id','research_programmes.id']),
        ForeignKeyConstraint(['org_id','baseline_run_id'],['study_runs.org_id','study_runs.id']),
        ForeignKeyConstraint(['org_id','proposed_run_id'],['study_runs.org_id','study_runs.id']),
    )


class BenefitReservationV79(Base):
    """Append-only acknowledgement of a synthetic claim; NOT actual cash savings."""
    __tablename__ = 'benefit_reservations_v79'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    asset_id:Mapped[str]=mapped_column(String,nullable=False)
    family:Mapped[str]=mapped_column(String(50),nullable=False)
    start_year:Mapped[int]=mapped_column(Integer,nullable=False)
    end_year:Mapped[int]=mapped_column(Integer,nullable=False)
    source_kind:Mapped[str]=mapped_column(String(50),nullable=False)
    source_id:Mapped[str]=mapped_column(String(120),nullable=False)
    source_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    source_fingerprint:Mapped[str]=mapped_column(String(64),nullable=False)
    measurement_plan_ref:Mapped[str]=mapped_column(String(160),nullable=False)
    measurement_boundary_description:Mapped[str]=mapped_column(Text,nullable=False)
    comparison_normalization:Mapped[str]=mapped_column(Text,nullable=False)
    lab_estimated_gross_rub:Mapped[str|None]=mapped_column(String(80),nullable=True)
    reservation_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(
        UniqueConstraint('org_id','id',name='uq_benefit_v79_org_id'),
        UniqueConstraint('org_id','source_kind','source_id',name='uq_benefit_v79_single_source'),
        UniqueConstraint('org_id','source_fingerprint',name='uq_benefit_v79_source_fingerprint'),
        ForeignKeyConstraint(['org_id','asset_id'],['assets.org_id','assets.id']),
    )


class MeasurementScreenV79(Base):
    """Append-only, synthetic counterfactual screen, never verified savings."""
    __tablename__='measurement_screens_v79'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=new_id)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),nullable=False,index=True)
    asset_id:Mapped[str]=mapped_column(String,nullable=False)
    input_payload:Mapped[dict]=mapped_column(JSON,nullable=False)
    input_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    report:Mapped[dict]=mapped_column(JSON,nullable=False)
    report_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    engine_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(
       UniqueConstraint('org_id','id',name='uq_mv_v79_org_id'),
       UniqueConstraint('org_id','input_sha256',name='uq_mv_v79_repeat'),
       ForeignKeyConstraint(['org_id','asset_id'],['assets.org_id','assets.id']),
    )

class MeterBoundaryV8(Base):
    """LAB canonical metering scope. Immutable after creation."""
    __tablename__='meter_boundaries_v8'
    id:Mapped[str]=mapped_column(String(100),primary_key=True)
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),primary_key=True,index=True)
    parent_id:Mapped[str|None]=mapped_column(String(100),nullable=True)
    quantity_class:Mapped[str]=mapped_column(String(35),nullable=False)
    source_ref:Mapped[str]=mapped_column(String(160),nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(
        UniqueConstraint('org_id','id',name='uq_meter_boundary_v8_org_id'),
        ForeignKeyConstraint(['org_id','parent_id'],['meter_boundaries_v8.org_id','meter_boundaries_v8.id']),
    )

class BoundaryAssetV8(Base):
    """A single asset maps to one canonical boundary within its org."""
    __tablename__='boundary_assets_v8'
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),primary_key=True)
    asset_id:Mapped[str]=mapped_column(String,primary_key=True)
    boundary_id:Mapped[str]=mapped_column(String(100),nullable=False)
    evidence_ref:Mapped[str]=mapped_column(String(160),nullable=False)
    created_by:Mapped[str]=mapped_column(String,ForeignKey('users.id'),nullable=False)
    __table_args__=(
        ForeignKeyConstraint(['org_id','asset_id'],['assets.org_id','assets.id']),
        ForeignKeyConstraint(['org_id','boundary_id'],['meter_boundaries_v8.org_id','meter_boundaries_v8.id']),
    )

class BoundaryConflictV8(Base):
    """Materialized symmetric potential overlap of physical boundary scopes."""
    __tablename__='boundary_conflicts_v8'
    org_id:Mapped[str]=mapped_column(String,ForeignKey('organizations.id'),primary_key=True)
    left_id:Mapped[str]=mapped_column(String(100),primary_key=True)
    right_id:Mapped[str]=mapped_column(String(100),primary_key=True)
    reason:Mapped[str]=mapped_column(String(50),nullable=False)
    __table_args__=(
        ForeignKeyConstraint(['org_id','left_id'],['meter_boundaries_v8.org_id','meter_boundaries_v8.id']),
        ForeignKeyConstraint(['org_id','right_id'],['meter_boundaries_v8.org_id','meter_boundaries_v8.id']),
    )
