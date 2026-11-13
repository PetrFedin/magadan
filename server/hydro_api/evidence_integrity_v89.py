"""Offline *synthetic-only* integrity proof for HydroKontur V8.9.

A good signature authenticates a pinned test key and a local byte digest. It
DOES NOT grant third-party data-use rights, certify a source authority, establish
real network capacity, or replace protected audit/WORM infrastructure.

This module never ingests field data, writes to a database or logs file contents.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_SYNTHETIC_BYTES = 2 * 1024 * 1024
OWNER_DOMAIN = b"HYDROKONTUR-V89-OWNER-EVIDENCE\x00"
REVIEWER_DOMAIN = b"HYDROKONTUR-V89-REVIEWER-EVIDENCE\x00"
FILE_PATTERN = r"^SYNTHETIC-[A-Za-z0-9_.-]{4,100}\.(json|csv|txt|bin)$"
ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{3,90}$"
SYNTH_PATTERN = r"^SYNTHETIC-[A-Za-z0-9_.-]{4,120}$"
DIGEST_PATTERN = r"^[0-9a-f]{64}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class EvidenceClaim(Strict):
    contract_version: Literal["V89-SYNTHETIC-EVIDENCE-1"]
    claim_id: str = Field(pattern=SYNTH_PATTERN)
    source_id: str = Field(pattern=SYNTH_PATTERN)
    source_revision: str = Field(pattern=SYNTH_PATTERN)
    recorded_forecast_revision: str = Field(pattern=SYNTH_PATTERN)
    file_name: str = Field(pattern=FILE_PATTERN)
    file_sha256: str = Field(pattern=DIGEST_PATTERN)
    file_size_bytes: int = Field(gt=0, le=MAX_SYNTHETIC_BYTES)
    declared_use: Literal["SYNTHETIC_TEST_ONLY"]
    source_permission_ref: str = Field(pattern=SYNTH_PATTERN)
    owner_key_id: str = Field(pattern=ID_PATTERN)
    reviewer_key_id: str = Field(pattern=ID_PATTERN)
    issued_at_utc: datetime
    expires_at_utc: datetime

    @field_validator("file_size_bytes", mode="before")
    @classmethod
    def forbid_boolean_byte_count(cls, value):
        if isinstance(value, bool):
            raise ValueError("BOOLEAN_IS_NOT_BYTE_COUNT")
        return value

    @field_validator("issued_at_utc", "expires_at_utc")
    @classmethod
    def require_real_utc(cls, value):
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("TIMESTAMPS_MUST_BE_EXPLICIT_UTC")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def require_distinct_people_and_valid_interval(self):
        if self.owner_key_id == self.reviewer_key_id:
            raise ValueError("OWNER_AND_REVIEWER_KEYS_MUST_DIFFER")
        if self.expires_at_utc <= self.issued_at_utc:
            raise ValueError("EXPIRY_MUST_FOLLOW_ISSUANCE")
        if self.expires_at_utc - self.issued_at_utc > timedelta(days=31):
            raise ValueError("TEST_EVIDENCE_VALIDITY_OVER_31_DAYS")
        return self


class SignedEvidence(Strict):
    claim: EvidenceClaim
    owner_signature_b64: str = Field(min_length=80, max_length=100)
    reviewer_signature_b64: str = Field(min_length=80, max_length=100)


class TrustedVerifier(Strict):
    key_id: str = Field(pattern=ID_PATTERN)
    role: Literal["SYNTHETIC_OWNER", "INDEPENDENT_TEST_REVIEWER"]
    public_key_b64: str = Field(min_length=40, max_length=60)


class PinnedTrustPolicy(Strict):
    keys: list[TrustedVerifier] = Field(min_length=2, max_length=20)

    @model_validator(mode="after")
    def distinct_key_ids(self):
        if len({k.key_id for k in self.keys}) != len(self.keys):
            raise ValueError("DUPLICATE_PINNED_KEY_ID")
        return self


def signed_bytes(claim: EvidenceClaim) -> bytes:
    """Stable canonical signing surface; signatures are never signed themselves."""
    data = claim.model_dump(mode="json")
    return json.dumps(data, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _decode_base64(value: str, expected_length: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("INVALID_BASE64") from exc
    if len(decoded) != expected_length:
        raise ValueError("INVALID_KEY_OR_SIGNATURE_LENGTH")
    return decoded


def _read_synthetic_payload(root: Path, name: str) -> tuple[str, int]:
    """Hash only a regular non-linked file under a non-symlinked chosen directory.

    Holding a file descriptor while hashing limits rename/symlink tricks. The
    receipt cannot authorize a later read: downstream must reverify its bytes.
    """
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("NO_SYMLINK_SAFE_FILE_OPEN_SUPPORT")
    try:
        root_stat = os.lstat(root)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ValueError("EVIDENCE_ROOT_NOT_A_PLAIN_DIRECTORY")
        dir_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise ValueError("EVIDENCE_ROOT_NOT_ACCESSIBLE") from exc
    try:
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
        except OSError as exc:
            raise ValueError("EVIDENCE_FILE_OPEN_REJECTED") from exc
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError("EVIDENCE_NOT_A_SINGLE_LINK_REGULAR_FILE")
            if not 0 < before.st_size <= MAX_SYNTHETIC_BYTES:
                raise ValueError("EVIDENCE_FILE_SIZE_OUT_OF_BOUNDS")
            total = 0
            digest = hashlib.sha256()
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SYNTHETIC_BYTES:
                    raise ValueError("EVIDENCE_FILE_TOO_LARGE")
                digest.update(chunk)
            after = os.fstat(fd)
            if (before.st_size, before.st_ino, before.st_dev, before.st_mtime_ns,
                    before.st_ctime_ns) != (after.st_size, after.st_ino, after.st_dev,
                                              after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError("EVIDENCE_CHANGED_DURING_HASH")
            return digest.hexdigest(), total
        finally:
            os.close(fd)
    finally:
        os.close(dir_fd)


def verify_synthetic_evidence(envelope: SignedEvidence, trust: PinnedTrustPolicy,
                              root: Path, now: datetime | None = None) -> dict:
    """Cryptographic *synthetic* byte integrity; never legal permission attestation."""
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise ValueError("VERIFIER_TIME_MUST_BE_UTC")
    claim = envelope.claim
    if claim.issued_at_utc > current + timedelta(minutes=5):
        raise ValueError("EVIDENCE_ISSUED_IN_FUTURE")
    if current >= claim.expires_at_utc:
        raise ValueError("EVIDENCE_EXPIRED")
    registry = {k.key_id: k for k in trust.keys}
    owner = registry.get(claim.owner_key_id)
    reviewer = registry.get(claim.reviewer_key_id)
    if not owner or owner.role != "SYNTHETIC_OWNER":
        raise ValueError("OWNER_NOT_IN_INDEPENDENT_PINNED_TRUST")
    if not reviewer or reviewer.role != "INDEPENDENT_TEST_REVIEWER":
        raise ValueError("REVIEWER_NOT_IN_INDEPENDENT_PINNED_TRUST")
    canonical = signed_bytes(claim)
    try:
        for role, entry, signature, domain in (
            ("OWNER", owner, envelope.owner_signature_b64, OWNER_DOMAIN),
            ("REVIEWER", reviewer, envelope.reviewer_signature_b64, REVIEWER_DOMAIN),
        ):
            public_key = Ed25519PublicKey.from_public_bytes(
                _decode_base64(entry.public_key_b64, 32))
            public_key.verify(_decode_base64(signature, 64), domain + canonical)
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("EVIDENCE_SIGNATURE_OR_PINNED_KEY_INVALID") from exc
    digest, size = _read_synthetic_payload(Path(root), claim.file_name)
    if size != claim.file_size_bytes or not hmac.compare_digest(digest, claim.file_sha256):
        raise ValueError("EVIDENCE_BYTE_SIZE_OR_SHA256_MISMATCH")
    return {
        "status": "SYNTHETIC_CRYPTOGRAPHIC_INTEGRITY_PASS_ONLY",
        "claim_id": claim.claim_id,
        "source_id": claim.source_id,
        "source_revision": claim.source_revision,
        "recorded_forecast_revision": claim.recorded_forecast_revision,
        "claim_sha256": hashlib.sha256(canonical).hexdigest(),
        "payload_sha256": digest,
        "payload_bytes": size,
        "pinned_owner_signature_valid": True,
        "pinned_reviewer_signature_valid": True,
        "real_source_rights_verified": False,
        "real_source_owner_authority_verified": False,
        "n_minus_one_independently_verified": False,
        "real_available_capacity_mw": None,
        "investment_decision": "HOLD",
        "production_ready": False,
        "receipt_is_worm_record": False,
    }


def verify_synthetic_batch(envelopes: list[SignedEvidence], trust: PinnedTrustPolicy,
                           root: Path, now: datetime | None = None) -> dict:
    """Fail-closed batch: partial success is never reported as overall acceptance."""
    if not 1 <= len(envelopes) <= 100:
        raise ValueError("EVIDENCE_BATCH_SIZE_OUT_OF_BOUNDS")
    claims = [item.claim for item in envelopes]
    for attribute in ("claim_id", "source_id", "file_name"):
        values = [getattr(c, attribute).casefold() for c in claims]
        if len(values) != len(set(values)):
            raise ValueError("DUPLICATE_" + attribute.upper() + "_IN_BATCH")
    reports = [verify_synthetic_evidence(x, trust, root, now) for x in envelopes]
    return {
        "status": "SYNTHETIC_BATCH_INTEGRITY_PASS_ONLY",
        "count": len(reports),
        "record_claim_sha256": sorted(row["claim_sha256"] for row in reports),
        "real_source_rights_verified": False,
        "real_available_capacity_mw": None,
        "investment_decision": "HOLD",
        "production_ready": False,
    }
