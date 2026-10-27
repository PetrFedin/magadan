#!/usr/bin/env python3
"""Fail-closed admission gate: V7.9 source + immutable recovery manifest required.

A green recovery-tool test is *not* evidence that the actual HydroKontur source
has been restored. This separate gate deliberately fails on a docs-only repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_v79_snapshot import MIGRATIONS, REQUIRED, safe_path


class AdmissionBlocked(Exception):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def check(root: Path) -> dict:
    """Admit the exact staged SOURCE snapshot; no CI/test claims are implied."""
    root = root.resolve(strict=True)
    missing = [p for p in REQUIRED if not (root / p).is_file()]
    if missing:
        raise AdmissionBlocked('REQUIRED_SOURCE_FILES_MISSING: ' + ', '.join(missing))
    sql = sorted((root / 'server' / 'migrations').glob('[0-9][0-9][0-9]_*.sql'))
    numbers = sorted(p.name[:3] for p in sql)
    if numbers != list(MIGRATIONS):
        raise AdmissionBlocked('MIGRATION_SEQUENCE_MISMATCH: ' + ','.join(numbers))
    mf = root / 'SOURCE_RECOVERY_MANIFEST.json'
    if not mf.is_file():
        raise AdmissionBlocked('PROVENANCE_MANIFEST_MISSING: original source archive has not been staged')
    try:
        info = json.loads(mf.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise AdmissionBlocked('INVALID_PROVENANCE_MANIFEST') from exc
    if info.get('classification') != 'SOURCE_IMPORT_STAGED_NOT_ACCEPTED':
        raise AdmissionBlocked('BAD_SOURCE_CLASSIFICATION')
    if info.get('production_ready') is not False or info.get('native_postgresql_accepted') is not False:
        raise AdmissionBlocked('MANIFEST_FALSIFIES_ADMISSION_STATUS')
    digest = info.get('archive_sha256', '')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise AdmissionBlocked('ORIGINAL_ARCHIVE_SHA256_MISSING')
    entries = info.get('files')
    if not isinstance(entries, list) or not entries:
        raise AdmissionBlocked('EMPTY_SOURCE_MANIFEST')
    seen: set[str] = set()
    for rec in entries:
        if not isinstance(rec, dict):
            raise AdmissionBlocked('INVALID_MANIFEST_ROW')
        name, claimed = rec.get('path'), rec.get('sha256')
        if not isinstance(name, str) or not isinstance(claimed, str):
            raise AdmissionBlocked('INVALID_SOURCE_FILE_IDENTITY')
        try:
            rel = safe_path(name)
        except ValueError as exc:
            raise AdmissionBlocked('DANGEROUS_MANIFEST_PATH') from exc
        if name in seen:
            raise AdmissionBlocked('DUPLICATE_MANIFEST_PATH')
        seen.add(name)
        target = root / rel
        if target.is_symlink() or not target.is_file():
            raise AdmissionBlocked('SOURCE_FILE_MISSING_OR_SYMLINK: ' + name)
        if target.stat().st_size != rec.get('bytes'):
            raise AdmissionBlocked('SOURCE_FILE_SIZE_DRIFT: ' + name)
        if not re.fullmatch('[0-9a-f]{64}', claimed) or sha256(target) != claimed:
            raise AdmissionBlocked('SOURCE_FILE_SHA256_DRIFT: ' + name)
    if not set(REQUIRED).issubset(seen):
        raise AdmissionBlocked('SOURCE_MANIFEST_INCOMPLETE')
    return {
        'status': 'SOURCE_TREE_AND_MANIFEST_MATCH_ONLY',
        'file_count_verified': len(entries),
        'original_archive_sha256_claim': digest,
        'source_tests_executed': False,
        'github_ci_verified': False,
        'postgresql17_rls_native_accepted': False,
        'corporate_identity_accepted': False,
        'independent_grid_solver_accepted': False,
        'real_magadan_data_accepted': False,
        'industrial_approval_eligible': False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('.'))
    args = p.parse_args()
    try:
        print(json.dumps(check(args.root), indent=2, ensure_ascii=False))
        return 0
    except (AdmissionBlocked, OSError) as exc:
        print('SOURCE_ADMISSION_BLOCKED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())