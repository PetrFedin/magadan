#!/usr/bin/env python3
"""V8.7 LOCAL ONLY: independently back up and restore a synthetic PG17 database.

Never points to production. Never drops an existing database or any database
other than the unique restore target this process just created.
The result is a smoke test, NOT a disaster-recovery RPO/RTO certification.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg import sql


def postgres_connection_parts(url: str):
    p = urlsplit(url.replace("postgresql+psycopg://", "postgresql://", 1))
    dbname = p.path.removeprefix("/")
    if (p.scheme != "postgresql" or p.hostname not in ("127.0.0.1", "localhost")
            or not p.username or not p.password or not re.fullmatch(r"hydrokontur_v72_acceptance_v87[a-z0-9_]*", dbname)):
        raise RuntimeError("V87_RESTORE_REFUSES_NON_SYNTHETIC_LOCAL_PG")
    return p, dbname


def run_pg(exe: str, args: list[str], env: dict):
    cp = subprocess.run([exe, *args], env=env, text=True, capture_output=True,
                        timeout=180, check=False)
    if cp.returncode:
        raise RuntimeError(f"V87_{exe.upper()}_FAILED_RC_{cp.returncode}")
    return cp


def inventory(conn):
    rels = conn.execute("""SELECT schemaname, tablename
        FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema','pg_toast')
        ORDER BY 1,2""").fetchall()
    counts = {}
    for schema, table in rels:
        counts[f"{schema}.{table}"] = conn.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(sql.Identifier(schema), sql.Identifier(table))
        ).fetchone()[0]
    policies = conn.execute("""SELECT schemaname,tablename,policyname,roles::text,cmd,
         permissive,qual,with_check FROM pg_policies ORDER BY 1,2,3""").fetchall()
    triggers = conn.execute("""SELECT n.nspname,c.relname,t.tgname
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE NOT t.tgisinternal AND n.nspname NOT IN ('pg_catalog','information_schema')
        ORDER BY 1,2,3""").fetchall()
    return {
        "tables": counts,
        "policies": [list(x) for x in policies],
        "triggers": [list(x) for x in triggers],
    }


# PostgreSQL 17's pg_dump/pg_restore may deparse identical text-array casts
# at different levels of the array expression. Normalize only this EXACT
# known representation; every other policy difference remains a hard failure.
_DUMP_ARRAY_CAST = "((ARRAY['engineering_report'::character varying, 'financial_report'::character varying, 'outcome_report'::character varying])::text[])"
_RESTORED_ELEMENT_CASTS = "ARRAY[('engineering_report'::character varying)::text, ('financial_report'::character varying)::text, ('outcome_report'::character varying)::text]"


def stable_policy_rows(rows):
    return [
        [value.replace(_DUMP_ARRAY_CAST, _RESTORED_ELEMENT_CASTS)
              .replace("ALL (" + _RESTORED_ELEMENT_CASTS + ")", "ALL " + _RESTORED_ELEMENT_CASTS)
         if isinstance(value, str) else value for value in row]
        for row in rows
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--native-config", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    cfg = json.loads(Path(args.native_config).read_text())
    p, dbname = postgres_connection_parts(cfg["admin_url"])
    env = dict(os.environ, PGPASSWORD=p.password)
    base = ["-h", p.hostname, "-p", str(p.port or 5432), "-U", p.username]
    def client_version(exe):
        try:
            return subprocess.run([exe, "--version"], capture_output=True,
                text=True, check=True).stdout.strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            return "NOT_INSTALLED"
    prefix, rest = client_version("pg_dump"), client_version("pg_restore")
    docker_pg17 = " 17." not in prefix or " 17." not in rest
    if docker_pg17 and (os.name != "posix" or not os.path.isfile("/proc/version")):
        raise RuntimeError("V87_REQUIRES_POSTGRESQL17_CLIENT_OR_LINUX_DOCKER")

    target = "hydrokontur_v72_restore_v87_" + secrets.token_hex(5)
    out = Path(args.output)
    if out.exists():
        raise RuntimeError("V87_REFUSES_OVERWRITE")
    out.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(out.parent, 0o700)
    backup = out.parent / (target + ".dump")
    if backup.exists():
        raise RuntimeError("V87_BACKUP_ALREADY_EXISTS")

    def backed_up_with_pg17(exe, params):
        if not docker_pg17:
            return run_pg(exe, params, env)
        # GitHub Ubuntu runner: use the SAME official postgres:17 image
        # as the disposable DB service. Rootless, host network, temp mount.
        converted = ["/backups/" + backup.name if x == str(backup) else x for x in params]
        cmd = [
            "docker", "run", "--rm", "--network=host",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--mount", f"type=bind,source={out.parent.resolve()},target=/backups",
            "-e", "PGPASSWORD", "postgres:17",
            exe, *converted
        ]
        cp = subprocess.run(cmd, env=env, text=True, capture_output=True,
                            timeout=240, check=False)
        if cp.returncode:
            raise RuntimeError(f"V87_DOCKER_{exe.upper()}_FAILED_RC_{cp.returncode}")
        return cp

    admin_kwargs = dict(host=p.hostname, port=p.port or 5432, user=p.username, password=p.password)
    created = False
    try:
        with psycopg.connect(dbname=dbname, **admin_kwargs) as source:
            version = int(source.execute("SHOW server_version_num").fetchone()[0])
            if not 170000 <= version < 180000:
                raise RuntimeError("NOT_POSTGRESQL17")
            before = inventory(source)
        if len(before["tables"]) < 30 or len(before["policies"]) < 80:
            raise RuntimeError("V87_SCHEMA_OR_RLS_INCOMPLETE")

        backed_up_with_pg17("pg_dump", [*base, "-Fc", "-f", str(backup), "-d", dbname])
        if backup.stat().st_size < 2048:
            raise RuntimeError("V87_BACKUP_TOO_SMALL")

        with psycopg.connect(dbname="postgres", autocommit=True, **admin_kwargs) as admin:
            exists = admin.execute("SELECT 1 FROM pg_database WHERE datname=%s", (target,)).fetchone()
            if exists:
                raise RuntimeError("RESTORE_TARGET_ALREADY_EXISTS")
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
            created = True
        backed_up_with_pg17("pg_restore", [*base, "--exit-on-error", "-d", target, str(backup)])
        with psycopg.connect(dbname=target, **admin_kwargs) as restored:
            after = inventory(restored)
        # Metadata names, GRANT roles, RLS predicates and CHECKs all compare.
        # The one documented PG17 text[] deparser rewrite is canonicalized.
        policy_deparser_rewrite = before["policies"] != after["policies"]
        before["policies"] = stable_policy_rows(before["policies"])
        after["policies"] = stable_policy_rows(after["policies"])
        if before != after:
            for group in ("tables", "policies", "triggers"):
                left, right = before[group], after[group]
                if left != right:
                    print("RESTORE_PARITY_DIAGNOSTIC", group,
                          "before", len(left), "after", len(right))
                    if group == "tables":
                        for name in sorted(set(left) | set(right)):
                            if left.get(name) != right.get(name):
                                print("COUNT_MISMATCH", name, left.get(name), right.get(name))
                    else:
                        for ix, (a, b) in enumerate(zip(left, right)):
                            if a != b:
                                print("FIRST_DIFFERENCE_INDEX", group, ix,
                                      "before", str(a)[:240], "after", str(b)[:240])
                                if group == "policies":
                                    import difflib
                                    for delta in list(difflib.unified_diff(
                                            str(a).splitlines(keepends=True),
                                            str(b).splitlines(keepends=True)) )[:25]:
                                        print("POLICY_DIFF", delta[:1800])
                                break
            raise RuntimeError("V87_RESTORE_PARITY_MISMATCH")

        app = urlsplit(cfg["app_url"])
        with psycopg.connect(dbname=target, host=p.hostname, port=p.port or 5432,
                            user=app.username, password=app.password) as lowpriv:
            r = lowpriv.execute("""SELECT current_user, rolsuper, rolbypassrls
                FROM pg_roles WHERE rolname=current_user""").fetchone()
            assert r == ("hk_app", False, False), "RESTORE_RUNTIME_PRIVILEGES_BAD"
            # No hk_security.bind_session: FORCE RLS must default DENY.
            assert lowpriv.execute("SELECT count(*) FROM public.assets").fetchone()[0] == 0, "RESTORED_RLS_DEFAULT_ALLOW"

        receipt = {
            "scope": "SYNTHETIC_LOCAL_PG17_BACKUP_RESTORE_SMOKE_ONLY",
            "postgres_server_version_num": version,
            "backup_client": "postgres:17 container" if docker_pg17 else prefix,
            "restore_client": "postgres:17 container" if docker_pg17 else rest,
            "table_count": len(before["tables"]),
            "total_rows": sum(before["tables"].values()),
            "rls_policy_count": len(before["policies"]),
            "trigger_count": len(before["triggers"]),
            "table_rows_equal": True,
            "rls_policies_equal": True,
            "restored_rls_without_session_default_deny": True,
            "policy_deparser_cast_rewrite_observed": policy_deparser_rewrite,
            "triggers_equal": True,
            "dump_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
            "production_ready": False,
            "rpo_rto_certified": False,
            "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        fd = os.open(out, os.O_EXCL | os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(receipt, stream, indent=2)
        print(json.dumps({k: receipt[k] for k in ("table_count", "total_rows",
            "rls_policy_count", "trigger_count", "production_ready")}))
        print("V87_PG17_BACKUP_RESTORE_PARITY_PASS")
    finally:
        if created:
            with psycopg.connect(dbname="postgres", autocommit=True, **admin_kwargs) as admin:
                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(target)))
        if backup.exists():
            backup.unlink()


if __name__ == "__main__":
    main()
