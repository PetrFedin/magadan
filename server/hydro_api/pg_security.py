"""PostgreSQL runtime boundary. NO schema creation and NO owner credentials.
SQL execution requires the dedicated migration set and native integration tests.
"""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker


def setup_postgres(url: str):
    if not url.startswith('postgresql+psycopg://'):
        raise RuntimeError('Use explicit postgresql+psycopg DSN')
    engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5,
                          connect_args={'connect_timeout': 5, 'application_name':'hydrokontur-v71-api'})
    with engine.connect() as conn:
        role = conn.execute(text('SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).first()
        if role is None or role[0] != 'hk_app' or role[1] or role[2]:
            raise RuntimeError('Runtime must use non-owner hk_app without BYPASSRLS or superuser')
        tables = conn.execute(text("SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,pg_get_userbyid(c.relowner) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r'")).all()
        if not tables or any(not r[1] or not r[2] or r[3] == role[0] for r in tables):
            raise RuntimeError('FORCED_RLS_OR_ROLE_OWNERSHIP_CHECK_FAILED')
    factory = sessionmaker(engine, expire_on_commit=False)

    @event.listens_for(factory, 'after_begin')
    def bind(session, transaction, connection):
        token = session.info.get('opaque_token')
        if token:
            connection.execute(text('SELECT hk_security.bind_session(:token,:org)'),
                               {'token':token,'org':session.info.get('org_id','')})
    return engine, factory


def append_pg_audit(db, org_id, event_type, object_type, object_id, payload):
    import json
    return db.scalar(text('SELECT hk_security.append_audit(:org,:event,:kind,:id,CAST(:payload AS jsonb))'),
                     {'org':org_id,'event':event_type,'kind':object_type,'id':object_id,
                      'payload':json.dumps(payload,ensure_ascii=False,allow_nan=False)})


def pg_audit_status(db, org_id):
    pending=db.scalar(text('SELECT count(*) FROM audit_outbox WHERE org_id=:org AND delivered_at IS NULL'),{'org':org_id})
    delivered=db.scalar(text('SELECT count(*) FROM audit_receipts WHERE org_id=:org'),{'org':org_id})
    return {'pending_events':pending,'receipted_events':delivered,
            'externally_sealed':bool(db.scalar(text('SELECT hk_security.audit_ready(:org)'),{'org':org_id})),
            'corporate_worm_verified':False}
