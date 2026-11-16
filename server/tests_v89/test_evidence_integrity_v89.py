"""Isolated V8.9 synthetic content integrity and pinned dual-signature tests."""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from hydro_api.evidence_integrity_v89 import (
    EvidenceClaim, SignedEvidence, TrustedVerifier, PinnedTrustPolicy,
    OWNER_DOMAIN, REVIEWER_DOMAIN, signed_bytes, verify_synthetic_evidence,
    verify_synthetic_batch,
)

NOW = datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc)


def b64(value: bytes) -> str:
    return base64.b64encode(value).decode('ascii')


def make_packet(folder, name='SYNTHETIC-evidence-001.json', content=b'{"synthetic": true}\n'):
    path = folder / name
    path.write_bytes(content)
    owner_key, reviewer_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    owner_pub = owner_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    reviewer_pub = reviewer_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    trust = PinnedTrustPolicy(keys=[
        TrustedVerifier(key_id='lab_owner_v1', role='SYNTHETIC_OWNER', public_key_b64=b64(owner_pub)),
        TrustedVerifier(key_id='lab_reviewer_v1', role='INDEPENDENT_TEST_REVIEWER', public_key_b64=b64(reviewer_pub)),
    ])
    claim = EvidenceClaim(
        contract_version='V89-SYNTHETIC-EVIDENCE-1',
        claim_id='SYNTHETIC-claim-001',
        source_id='SYNTHETIC-source-001',
        source_revision='SYNTHETIC-source-v001',
        recorded_forecast_revision='SYNTHETIC-forecast-rev1',
        file_name=name,
        file_sha256=hashlib.sha256(content).hexdigest(),
        file_size_bytes=len(content),
        declared_use='SYNTHETIC_TEST_ONLY',
        source_permission_ref='SYNTHETIC-test-only',
        owner_key_id='lab_owner_v1', reviewer_key_id='lab_reviewer_v1',
        issued_at_utc=NOW - timedelta(minutes=10),
        expires_at_utc=NOW + timedelta(days=20),
    )
    packet = SignedEvidence(
        claim=claim,
        owner_signature_b64=b64(owner_key.sign(OWNER_DOMAIN + signed_bytes(claim))),
        reviewer_signature_b64=b64(reviewer_key.sign(REVIEWER_DOMAIN + signed_bytes(claim))),
    )
    return packet, trust, owner_key, reviewer_key


def test_synthetic_integrity_proof_never_grants_rights_or_capacity(tmp_path):
    packet, trust, _, _ = make_packet(tmp_path)
    report = verify_synthetic_evidence(packet, trust, tmp_path, NOW)
    assert report['status'] == 'SYNTHETIC_CRYPTOGRAPHIC_INTEGRITY_PASS_ONLY'
    assert report['pinned_owner_signature_valid'] is True
    assert report['pinned_reviewer_signature_valid'] is True
    assert not report['real_source_rights_verified']
    assert not report['real_source_owner_authority_verified']
    assert not report['n_minus_one_independently_verified']
    assert report['real_available_capacity_mw'] is None
    assert report['investment_decision'] == 'HOLD'
    assert not report['production_ready']
    assert not report['receipt_is_worm_record']
    assert report == verify_synthetic_evidence(packet, trust, tmp_path, NOW)


def test_modified_file_is_rejected_even_with_valid_signatures(tmp_path):
    packet, trust, _, _ = make_packet(tmp_path)
    (tmp_path / packet.claim.file_name).write_bytes(b'different synthetic input!')
    with pytest.raises(ValueError, match='EVIDENCE_BYTE_SIZE_OR_SHA256_MISMATCH'):
        verify_synthetic_evidence(packet, trust, tmp_path, NOW)


def test_same_length_modified_file_is_rejected_by_sha(tmp_path):
    data = b'A' * 32
    packet, trust, _, _ = make_packet(tmp_path, content=data)
    (tmp_path / packet.claim.file_name).write_bytes(b'B' * 32)
    with pytest.raises(ValueError, match='EVIDENCE_BYTE_SIZE_OR_SHA256_MISMATCH'):
        verify_synthetic_evidence(packet, trust, tmp_path, NOW)


def test_unsigned_claim_metadata_tampering_fails(tmp_path):
    packet, trust, _, _ = make_packet(tmp_path)
    changed = packet.model_copy(deep=True)
    changed.claim.source_revision = 'SYNTHETIC-source-v002'
    with pytest.raises(ValueError, match='EVIDENCE_SIGNATURE_OR_PINNED_KEY_INVALID'):
        verify_synthetic_evidence(changed, trust, tmp_path, NOW)


def test_reviewer_signature_must_use_independent_key(tmp_path):
    packet, trust, owner, _ = make_packet(tmp_path)
    changed = packet.model_copy(deep=True)
    changed.reviewer_signature_b64 = b64(owner.sign(REVIEWER_DOMAIN + signed_bytes(changed.claim)))
    with pytest.raises(ValueError, match='EVIDENCE_SIGNATURE_OR_PINNED_KEY_INVALID'):
        verify_synthetic_evidence(changed, trust, tmp_path, NOW)


def test_owner_signature_must_use_correct_domain(tmp_path):
    packet, trust, owner, _ = make_packet(tmp_path)
    changed = packet.model_copy(deep=True)
    changed.owner_signature_b64 = b64(owner.sign(REVIEWER_DOMAIN + signed_bytes(changed.claim)))
    with pytest.raises(ValueError, match='EVIDENCE_SIGNATURE_OR_PINNED_KEY_INVALID'):
        verify_synthetic_evidence(changed, trust, tmp_path, NOW)


def test_wrong_pinned_role_fails(tmp_path):
    packet, trust, _, _ = make_packet(tmp_path)
    wrong = trust.model_copy(deep=True)
    wrong.keys[0].role = 'INDEPENDENT_TEST_REVIEWER'
    with pytest.raises(ValueError, match='OWNER_NOT_IN_INDEPENDENT_PINNED_TRUST'):
        verify_synthetic_evidence(packet, wrong, tmp_path, NOW)


def test_same_owner_and_reviewer_id_is_schema_error(tmp_path):
    packet, _, _, _ = make_packet(tmp_path)
    data = packet.claim.model_dump(mode='json')
    data['reviewer_key_id'] = data['owner_key_id']
    with pytest.raises(ValidationError, match='OWNER_AND_REVIEWER_KEYS_MUST_DIFFER'):
        EvidenceClaim.model_validate(data)


def test_untrusted_owner_id_rejected(tmp_path):
    packet, trust, _, _ = make_packet(tmp_path)
    changed = packet.model_copy(deep=True)
    changed.claim.owner_key_id = 'new_owner_unknown'
    with pytest.raises(ValueError, match='OWNER_NOT_IN_INDEPENDENT_PINNED_TRUST'):
        verify_synthetic_evidence(changed, trust, tmp_path, NOW)


def test_expired_evidence_rejected(tmp_path):
    packet, trust, _, _ = make_packet(tmp_path)
    with pytest.raises(ValueError, match='EVIDENCE_EXPIRED'):
        verify_synthetic_evidence(packet, trust, tmp_path, NOW + timedelta(days=21))


def test_naive_verifier_clock_rejected(tmp_path):
    packet, trust, _, _ = make_packet(tmp_path)
    with pytest.raises(ValueError, match='VERIFIER_TIME_MUST_BE_UTC'):
        verify_synthetic_evidence(packet, trust, tmp_path, datetime(2026, 11, 13))


def test_future_issued_evidence_rejected(tmp_path):
    packet, trust, _, _ = make_packet(tmp_path)
    with pytest.raises(ValueError, match='EVIDENCE_ISSUED_IN_FUTURE'):
        verify_synthetic_evidence(packet, trust, tmp_path, NOW - timedelta(hours=1))


def test_symlink_file_not_followed(tmp_path):
    packet, trust, _, _ = make_packet(tmp_path)
    original = tmp_path / packet.claim.file_name
    moved = tmp_path / 'separate.txt'
    original.rename(moved)
    original.symlink_to(moved)
    with pytest.raises(ValueError, match='EVIDENCE_FILE_OPEN_REJECTED'):
        verify_synthetic_evidence(packet, trust, tmp_path, NOW)


def test_hard_linked_file_not_accepted(tmp_path):
    packet, trust, _, _ = make_packet(tmp_path)
    (tmp_path / 'extra-copy.txt').hardlink_to(tmp_path / packet.claim.file_name)
    with pytest.raises(ValueError, match='EVIDENCE_NOT_A_SINGLE_LINK_REGULAR_FILE'):
        verify_synthetic_evidence(packet, trust, tmp_path, NOW)


def test_symlink_root_not_accepted(tmp_path):
    base = tmp_path / 'data'
    base.mkdir()
    packet, trust, _, _ = make_packet(base)
    (tmp_path / 'alias').symlink_to(base, target_is_directory=True)
    with pytest.raises(ValueError, match='EVIDENCE_ROOT_NOT_A_PLAIN_DIRECTORY'):
        verify_synthetic_evidence(packet, trust, tmp_path / 'alias', NOW)


def test_path_traversal_cannot_be_claimed(tmp_path):
    packet, _, _, _ = make_packet(tmp_path)
    data = packet.claim.model_dump(mode='json')
    data['file_name'] = '../secret.csv'
    with pytest.raises(ValidationError):
        EvidenceClaim.model_validate(data)


def test_real_data_mode_not_in_schema(tmp_path):
    packet, _, _, _ = make_packet(tmp_path)
    data = packet.claim.model_dump(mode='json')
    data['declared_use'] = 'REAL_OPERATIONAL_DATA'
    with pytest.raises(ValidationError):
        EvidenceClaim.model_validate(data)


def test_unknown_fields_or_fake_owner_verification_rejected(tmp_path):
    packet, _, _, _ = make_packet(tmp_path)
    data = packet.claim.model_dump(mode='json')
    data['real_source_rights_verified'] = True
    with pytest.raises(ValidationError, match='extra_forbidden'):
        EvidenceClaim.model_validate(data)


def test_bad_timestamp_timezone_and_invalid_interval(tmp_path):
    packet, _, _, _ = make_packet(tmp_path)
    data = packet.claim.model_dump(mode='json')
    data['issued_at_utc'] = '2026-11-13T15:00:00+03:00'
    with pytest.raises(ValidationError):
        EvidenceClaim.model_validate(data)
    data = packet.claim.model_dump(mode='json')
    data['expires_at_utc'] = data['issued_at_utc']
    with pytest.raises(ValidationError, match='EXPIRY_MUST_FOLLOW_ISSUANCE'):
        EvidenceClaim.model_validate(data)


def test_invalid_bool_size_and_excessive_size_rejected(tmp_path):
    packet, _, _, _ = make_packet(tmp_path)
    data = packet.claim.model_dump(mode='json')
    data['file_size_bytes'] = True
    with pytest.raises(ValidationError):
        EvidenceClaim.model_validate(data)
    data['file_size_bytes'] = 3 * 1024 * 1024
    with pytest.raises(ValidationError):
        EvidenceClaim.model_validate(data)


def test_duplicate_claim_rejected_as_batch_not_silently_double_counted(tmp_path):
    packet, trust, _, _ = make_packet(tmp_path)
    with pytest.raises(ValueError, match='DUPLICATE_CLAIM_ID_IN_BATCH'):
        verify_synthetic_batch([packet, packet], trust, tmp_path, NOW)


def test_unique_source_revision_batch_receipt_has_no_real_capacity(tmp_path):
    packet, trust, owner, reviewer = make_packet(tmp_path)
    second_name = 'SYNTHETIC-evidence-002.json'
    second_content = b'{"synthetic": "second"}\n'
    (tmp_path / second_name).write_bytes(second_content)
    claim2 = packet.claim.model_copy(deep=True)
    claim2.claim_id = 'SYNTHETIC-claim-002'
    claim2.source_id = 'SYNTHETIC-source-002'
    claim2.file_name = second_name
    claim2.file_size_bytes = len(second_content)
    claim2.file_sha256 = hashlib.sha256(second_content).hexdigest()
    second = SignedEvidence(claim=claim2,
                            owner_signature_b64=b64(owner.sign(OWNER_DOMAIN + signed_bytes(claim2))),
                            reviewer_signature_b64=b64(reviewer.sign(REVIEWER_DOMAIN + signed_bytes(claim2))))
    report = verify_synthetic_batch([packet, second], trust, tmp_path, NOW)
    assert report['count'] == 2
    assert report['status'] == 'SYNTHETIC_BATCH_INTEGRITY_PASS_ONLY'
    assert report['real_available_capacity_mw'] is None
    assert report['investment_decision'] == 'HOLD'


def test_duplicate_key_ids_in_pinned_policy_rejected(tmp_path):
    packet, trust, _, _ = make_packet(tmp_path)
    data = trust.model_dump(mode='json')
    data['keys'][1]['key_id'] = data['keys'][0]['key_id']
    with pytest.raises(ValidationError, match='DUPLICATE_PINNED_KEY_ID'):
        PinnedTrustPolicy.model_validate(data)
