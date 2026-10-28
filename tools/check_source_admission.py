#!/usr/bin/env python3
"""Fail-closed admission gate: V7.9 source + immutable recovery manifest required.

A green recovery-tool test is *not* evidence that the actual HydroKontur source
has been restored. This separate gate deliberately fails on a docs-only repo.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re
import sys
import unicodedata

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_v79_snapshot import MIGRATIONS, REQUIRED, REJECT_DIRS, safe_path, release_spec


class AdmissionBlocked(Exception):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def check(root: Path, trusted_archive_sha256: str | None = None,
          require_external_pin: bool = False,
          trusted_manifest_sha256: str | None = None,
          require_manifest_pin: bool = False,
          expected_release: str | None = None) -> dict:
    """Verify known archive bytes and protected source roots, not application quality.

    A self-reported SHA-256 manifest is insufficient to establish independent
    source provenance. A trusted value must arrive through a separate channel.
    """
    root = root.resolve(strict=True)
    release = 'v8.0' if (root / 'server/migrations/150_boundary_graph_v8.sql').is_file() else 'v7.9'
    spec = release_spec(release)
    missing = [p for p in spec['required'] if not (root / p).is_file()]
    if missing:
        raise AdmissionBlocked('REQUIRED_SOURCE_FILES_MISSING: ' + ', '.join(missing))
    sql = sorted((root / 'server' / 'migrations').glob('[0-9][0-9][0-9]_*.sql'))
    numbers = sorted(p.name[:3] for p in sql)
    if numbers != list(spec['migrations']):
        raise AdmissionBlocked('MIGRATION_SEQUENCE_MISMATCH: ' + ','.join(numbers))
    if release == 'v8.0':
        required_files = list(root.rglob('server/hydro_api/*boundary*v8*.py'))
        required_tests = list(root.rglob('server/tests_v8/*.py'))
        if not required_files or not required_tests or any(x.is_symlink() for x in required_files + required_tests):
            raise AdmissionBlocked('V8_BOUNDARY_ENGINE_OR_TESTS_MISSING')
    mf = root / 'SOURCE_RECOVERY_MANIFEST.json'
    if mf.is_symlink() or not mf.is_file():
        raise AdmissionBlocked('PROVENANCE_MANIFEST_MISSING: original source archive has not been staged')
    # P0: an externally pinned *archive* hash cannot cryptographically bind a
    # freely editable manifest to that archive. Pin the manifest's exact bytes
    # separately to detect forged source plus forged manifest-row hashes.
    manifest_digest = sha256(mf)
    if trusted_manifest_sha256 is not None:
        if not isinstance(trusted_manifest_sha256, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', trusted_manifest_sha256):
            raise AdmissionBlocked('INVALID_EXTERNAL_MANIFEST_SHA256_PIN')
        if not hmac.compare_digest(manifest_digest, trusted_manifest_sha256.lower()):
            raise AdmissionBlocked('EXTERNAL_MANIFEST_SHA256_PIN_MISMATCH')
    elif require_manifest_pin:
        raise AdmissionBlocked('EXTERNAL_MANIFEST_SHA256_PIN_REQUIRED')
    try:
        info = json.loads(mf.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise AdmissionBlocked('INVALID_PROVENANCE_MANIFEST') from exc
    if info.get('source_release', 'v7.9') != release:
        raise AdmissionBlocked('SOURCE_RELEASE_MANIFEST_MISMATCH')
    if expected_release is not None and expected_release != release:
        raise AdmissionBlocked('EXPECTED_SOURCE_RELEASE_MISMATCH')
    if info.get('classification') != 'SOURCE_IMPORT_STAGED_NOT_ACCEPTED':
        raise AdmissionBlocked('BAD_SOURCE_CLASSIFICATION')
    if info.get('production_ready') is not False or info.get('native_postgresql_accepted') is not False:
        raise AdmissionBlocked('MANIFEST_FALSIFIES_ADMISSION_STATUS')
    digest = info.get('archive_sha256', '')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise AdmissionBlocked('ORIGINAL_ARCHIVE_SHA256_MISSING')
    if trusted_archive_sha256 is not None:
        if not re.fullmatch(r'[0-9a-fA-F]{64}', trusted_archive_sha256):
            raise AdmissionBlocked('UNRECOGNIZED_EXTERNAL_SHA256_PIN')
        if digest != trusted_archive_sha256.lower():
            raise AdmissionBlocked('ORIGINAL_ARCHIVE_SHA256_EXTERNAL_PIN_MISMATCH')
    elif require_external_pin:
        raise AdmissionBlocked('EXTERNAL_ARCHIVE_SHA256_PIN_REQUIRED')
    entries = info.get('files')
    if not isinstance(entries, list) or not entries:
        raise AdmissionBlocked('EMPTY_SOURCE_MANIFEST')
    if type(info.get('file_count')) is not int or info['file_count'] != len(entries):
        raise AdmissionBlocked('MANIFEST_FILE_COUNT_INVALID')
    seen: set[str] = set()
    folded_names: set[str] = set()
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
        folded = unicodedata.normalize('NFC', name).casefold()
        if name in seen or folded in folded_names:
            raise AdmissionBlocked('DUPLICATE_MANIFEST_PATH')
        seen.add(name)
        folded_names.add(folded)
        target = root / rel
        if target.is_symlink() or not target.is_file():
            raise AdmissionBlocked('SOURCE_FILE_MISSING_OR_SYMLINK: ' + name)
        if target.stat().st_size != rec.get('bytes'):
            raise AdmissionBlocked('SOURCE_FILE_SIZE_DRIFT: ' + name)
        if not re.fullmatch('[0-9a-f]{64}', claimed) or sha256(target) != claimed:
            raise AdmissionBlocked('SOURCE_FILE_SHA256_DRIFT: ' + name)
    if not set(spec['required']).issubset(seen):
        raise AdmissionBlocked('SOURCE_MANIFEST_INCOMPLETE')
    # The repo may also contain its own reviewed GitHub workflow, recovery tools,
    # tests, documentation and .git internals. Their hashes do not come from the
    # original archive. Never, however, silently admit NEW executable code,
    # test data or migrations under the imported source roots.
    protected_roots = {'server', 'v6-client', 'scripts'}
    for item in root.rglob('*'):
        rel = item.relative_to(root)
        if not rel.parts or rel.parts[0] not in protected_roots:
            continue
        if any(part in REJECT_DIRS for part in rel.parts):
            continue
        if item.is_symlink():
            raise AdmissionBlocked('UNMANIFESTED_OR_SYMLINK_SOURCE: ' + rel.as_posix())
        if item.is_file() and rel.suffix not in {'.pyc', '.pyo'} and rel.as_posix() not in seen:
            raise AdmissionBlocked('UNMANIFESTED_EXECUTABLE_SOURCE: ' + rel.as_posix())
    return {
        'status': 'SOURCE_TREE_AND_MANIFEST_MATCH_ONLY',
        'source_release': release,
        'file_count_verified': len(entries),
        'original_archive_sha256_claim': digest,
        'external_source_hash_pinned': trusted_archive_sha256 is not None,
        'external_manifest_hash_pinned': trusted_manifest_sha256 is not None,
        'source_manifest_sha256': manifest_digest,
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
    p.add_argument('--trusted-archive-sha256', default=None,
                   help='SHA-256 received from a source independent of the archive itself')
    p.add_argument('--require-external-pin', action='store_true',
                   help='Fail if trusted external archive SHA-256 is not provided')
    p.add_argument('--trusted-manifest-sha256', default=None,
                   help='SHA-256 of the exact source manifest from a separate trusted release record')
    p.add_argument('--require-manifest-pin', action='store_true',
                   help='Fail if externally pinned source manifest digest is absent')
    p.add_argument('--expected-release', choices=('v7.9','v8.0'), default='v7.9',
                   help='Exact pinned source release; cannot silently promote v7.9 to v8.0')
    args = p.parse_args()
    try:
        print(json.dumps(check(args.root, args.trusted_archive_sha256,
                               args.require_external_pin,
                               args.trusted_manifest_sha256,
                               args.require_manifest_pin,
                               args.expected_release), indent=2, ensure_ascii=False))
        return 0
    except (AdmissionBlocked, OSError) as exc:
        print('SOURCE_ADMISSION_BLOCKED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
