#!/usr/bin/env python3
"""V8.9.2 offline QA verifier. Never accepts real operational energy data.

Trust keys must be pinned by a separate administrator, not read out of the
untrusted claim. Does NOT prove legal permission or independent N-1 capacity.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import stat
import sys
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from hydro_api.evidence_integrity_v89 import (  # noqa: E402
    SignedEvidence, PinnedTrustPolicy, verify_synthetic_evidence,
)


def _json_manifest(path: Path) -> tuple[dict, bytes]:
    # Parse and hash EXACTLY the same bytes from a single file descriptor.
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("V89_MANIFEST_MUST_BE_PLAIN_SINGLE_LINK_FILE")
        if not 0 < before.st_size <= 128 * 1024:
            raise ValueError("V89_MANIFEST_TOO_LARGE_OR_EMPTY")
        raw = os.read(fd, 128 * 1024 + 1)
        after = os.fstat(fd)
        if (before.st_size, before.st_ino, before.st_dev, before.st_mtime_ns,
                before.st_ctime_ns) != (after.st_size, after.st_ino, after.st_dev,
                                          after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("V89_MANIFEST_CHANGED_WHILE_READING")
        if len(raw) != before.st_size:
            raise ValueError("V89_MANIFEST_SIZE_CHANGED")
    finally:
        os.close(fd)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("V89_EXPECTED_TOP_LEVEL_OBJECT")
    return data, raw


def main() -> int:
    ap = argparse.ArgumentParser(description="SYNTHETIC QA ONLY, NOT REAL DATA ADMISSION")
    ap.add_argument("--signed-manifest", required=True)
    ap.add_argument("--pinned-trust-policy", required=True)
    ap.add_argument("--synthetic-data-dir", required=True)
    ap.add_argument("--receipt", required=True)
    args = ap.parse_args()
    try:
        pinned = os.environ.get("HYDRO_V89_PINNED_TRUST_SHA256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", pinned):
            raise ValueError("PINNED_EXTERNAL_TRUST_DIGEST_REQUIRED")
        trust_path = Path(args.pinned_trust_policy)
        trust_data, trust_bytes = _json_manifest(trust_path)
        trust_sha = hashlib.sha256(trust_bytes).hexdigest()
        if not hmac.compare_digest(pinned, trust_sha):
            raise ValueError("EXTERNAL_TRUST_DIGEST_MISMATCH")
        manifest_data, _ = _json_manifest(Path(args.signed_manifest))
        envelope = SignedEvidence.model_validate(manifest_data)
        trust = PinnedTrustPolicy.model_validate(trust_data)
        receipt = verify_synthetic_evidence(envelope, trust, Path(args.synthetic_data_dir))
        dest = Path(args.receipt)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.umask(0o077)
        descriptor = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as out:
            json.dump(receipt, out, indent=2, ensure_ascii=True, sort_keys=True)
            out.write("\n")
        print("V89_SYNTHETIC_SIGNED_BYTES_PASS; OWNER_RIGHTS_AND_REAL_N1_HOLD")
        return 0
    except (ValidationError, ValueError, OSError, UnicodeError, json.JSONDecodeError):
        print("V89_EVIDENCE_PREFLIGHT_REJECTED; RIGHTS_AND_PRODUCTION_HOLD", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
