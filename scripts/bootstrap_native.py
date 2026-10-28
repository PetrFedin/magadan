#!/usr/bin/env python3
"""Bootstrap a fresh dedicated native PostgreSQL database for acceptance tests.
Refuses a database with any user tables. Never drop/replace an existing database.
Output contains random LOCAL TEST credentials; keep it outside the source tree.
"""
import argparse,json,os,secrets,sys
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,quote

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    url=os.environ.get('HYDRO_PG_ADMIN_URL','')
    if not url:
        raise SystemExit('BLOCKED: set HYDRO_PG_ADMIN_URL for a dedicated empty acceptance database')
    try:import psycopg
    except ImportError:raise SystemExit('BLOCKED: psycopg not installed; install server/requirements-v71.txt')
    from psycopg import sql
    root=Path(__file__).resolve().parents[1]
    parsed=urlsplit(url.replace('postgresql+psycopg://','postgresql://',1))
    if not parsed.path.lstrip('/').startswith('hydrokontur_v72_'):
        raise SystemExit('Refusing: database name must start with hydrokontur_v72_')
    output=Path(args.out)
    if output.exists():raise SystemExit('Refusing to overwrite existing credential file')
    credentials={'admin_url':url}
    with psycopg.connect(url.replace('postgresql+psycopg://','postgresql://',1)) as conn:
        count=conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')").fetchone()[0]
        if count:raise SystemExit('Refusing a non-empty database')
        version=conn.execute('SELECT version()').fetchone()[0]
        for path in sorted((root/'server'/'migrations').glob('*.sql')):
            conn.execute(path.read_text())
            print('Applied',path.name)
        for role,key in [('hk_app','app_url'),('hk_authenticator','auth_url'),('hk_exporter','export_url')]:
            password=secrets.token_urlsafe(36)
            conn.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
            host=parsed.hostname or '127.0.0.1';port=parsed.port or 5432
            credentials[key]=urlunsplit(('postgresql+psycopg',f'{role}:{quote(password,safe="")}@{host}:{port}',parsed.path,parsed.query,''))
        credentials['postgresql_version']=version
        credentials['audit_receipt_key_hex']=conn.execute("SELECT encode(secret,'hex') FROM hk_private.secrets WHERE purpose='receipt'").fetchone()[0]
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as out:json.dump(credentials,out)
    print('Native migrations applied. Test credentials written with mode 0600; values not logged.')
    print(version)

if __name__=='__main__':main()
