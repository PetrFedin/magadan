"""Offline synthetic CLI proof: no real owners, grid measurements or production."""
import base64
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hydro_api.evidence_integrity_v89 import OWNER_DOMAIN, REVIEWER_DOMAIN, signed_bytes
from tests_v89.test_evidence_integrity_v89 import make_packet

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "v89_evidence_preflight.py"


def signed_packet(tmp_path):
    packet, trust, owner, reviewer = make_packet(tmp_path)
    current = datetime.now(timezone.utc)
    packet.claim.issued_at_utc = current - timedelta(minutes=1)
    packet.claim.expires_at_utc = current + timedelta(days=1)
    packet.owner_signature_b64 = base64.b64encode(
        owner.sign(OWNER_DOMAIN + signed_bytes(packet.claim))
    ).decode()
    packet.reviewer_signature_b64 = base64.b64encode(
        reviewer.sign(REVIEWER_DOMAIN + signed_bytes(packet.claim))
    ).decode()
    manifest, policy = tmp_path / "signed.json", tmp_path / "trust.json"
    manifest.write_text(packet.model_dump_json(), encoding="utf-8")
    policy.write_text(trust.model_dump_json(), encoding="utf-8")
    command = [
        sys.executable, str(SCRIPT),
        "--signed-manifest", str(manifest),
        "--pinned-trust-policy", str(policy),
        "--synthetic-data-dir", str(tmp_path),
        "--receipt", str(tmp_path / "receipt.json"),
    ]
    return command, manifest, policy, tmp_path / "receipt.json"


def test_signed_synthetic_cli_generates_private_receipt_and_refuses_overwrite(tmp_path):
    command, _, policy, receipt = signed_packet(tmp_path)
    env = dict(os.environ, HYDRO_V89_PINNED_TRUST_SHA256=hashlib.sha256(policy.read_bytes()).hexdigest())
    first = subprocess.run(command, text=True, capture_output=True, env=env)
    assert first.returncode == 0, first.stderr
    assert receipt.exists()
    assert os.stat(receipt).st_mode & 0o077 == 0
    report = json.loads(receipt.read_text())
    assert report["production_ready"] is False
    assert report["real_available_capacity_mw"] is None
    assert report["pinned_reviewer_signature_valid"] is True
    second = subprocess.run(command, text=True, capture_output=True, env=env)
    assert second.returncode == 2
    assert "REJECTED" in second.stderr


def test_cli_bad_json_refuses_without_receipt(tmp_path):
    command, manifest, policy, receipt = signed_packet(tmp_path)
    manifest.write_text("not json")
    env = dict(os.environ, HYDRO_V89_PINNED_TRUST_SHA256=hashlib.sha256(policy.read_bytes()).hexdigest())
    result = subprocess.run(command, text=True, capture_output=True, env=env)
    assert result.returncode == 2
    assert not receipt.exists()


def test_cli_missing_external_trust_anchor_fails_closed(tmp_path):
    command, _, _, receipt = signed_packet(tmp_path)
    env = dict(os.environ)
    env.pop("HYDRO_V89_PINNED_TRUST_SHA256", None)
    result = subprocess.run(command, text=True, capture_output=True, env=env)
    assert result.returncode == 2
    assert not receipt.exists()


def test_cli_swapped_trust_policy_refuses_even_if_packet_not_changed(tmp_path):
    command, _, policy, receipt = signed_packet(tmp_path)
    pinned_sha = hashlib.sha256(policy.read_bytes()).hexdigest()
    policy.write_text('{"keys": []}', encoding="utf-8")
    env = dict(os.environ, HYDRO_V89_PINNED_TRUST_SHA256=pinned_sha)
    result = subprocess.run(command, text=True, capture_output=True, env=env)
    assert result.returncode == 2
    assert not receipt.exists()
