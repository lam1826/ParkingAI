"""A local recovery proof must be signed, fresh and bound to this deployment."""
import base64
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

import recovery_attestation as recovery

NOW = datetime(2026, 10, 2, 3, 0, tzinfo=timezone.utc)
TARGET = "a" * 40
SOURCE = "b" * 40
REF = "abcdefghijklmnopqrst"
SCHEMA = "20261005_12"


@pytest.fixture
def proof():
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    payload = {
        "version": 1, "kind": "parkingai-local-recovery", "repository": "lam1826/ParkingAI",
        "fly_app": "parkingai-api-lam1826", "scope": "postgres:public",
        "source_fingerprint": recovery.source_fingerprint(REF), "target_sha": TARGET,
        "source_release": SOURCE, "source_schema": SCHEMA, "verified_target_schema": SCHEMA,
        "snapshot_at": (NOW - timedelta(minutes=30)).isoformat(),
        "backup_completed_at": (NOW - timedelta(minutes=25)).isoformat(),
        "restore_verified_at": (NOW - timedelta(minutes=15)).isoformat(),
        "signed_at": (NOW - timedelta(minutes=10)).isoformat(),
        "dump_sha256": "1" * 64, "dump_bytes": 10240, "table_count": 80,
        "source_tables_sha256": "2" * 64, "restored_tables_sha256": "2" * 64,
        "restore_proof_sha256": "3" * 64,
        "checks": {name: True for name in (
            "archive_restore", "deep_readiness", "table_counts", "fingerprints", "schema", "migration")},
    }
    return key, public, payload


def verify(envelope, public, **overrides):
    expected = dict(expected_target_sha=TARGET, expected_source_release=SOURCE,
                    expected_source_fingerprint=recovery.source_fingerprint(REF),
                    expected_target_schema=SCHEMA, now=NOW)
    expected.update(overrides)
    return recovery.verify_attestation(envelope, public, **expected)


def test_real_ed25519_signature_accepts_only_bound_recovery(proof):
    key, public, payload = proof
    envelope = recovery.sign_attestation(payload, key)
    assert verify(envelope, public) == payload
    # Different JSON layout must not change the canonical signed payload.
    assert verify(json.dumps(json.loads(envelope), indent=2), public) == payload
    assert REF not in envelope


def test_payload_change_without_resigning_and_other_key_are_rejected(proof):
    key, public, payload = proof
    envelope = json.loads(recovery.sign_attestation(payload, key))
    envelope["payload"]["dump_bytes"] += 1
    with pytest.raises(recovery.RecoveryAttestationError):
        verify(json.dumps(envelope), public)
    wrong = Ed25519PrivateKey.generate()
    with pytest.raises(recovery.RecoveryAttestationError):
        verify(recovery.sign_attestation(payload, wrong), public)


@pytest.mark.parametrize("field,value", [
    ("version", True), ("version", 2), ("kind", "anything"),
    ("repository", "other/ParkingAI"), ("fly_app", "other-app"), ("scope", "postgres:other"),
    ("target_sha", "c" * 40), ("source_release", "c" * 40),
    ("source_fingerprint", "c" * 64), ("verified_target_schema", "20260923_09"),
    ("source_schema", "invalid"), ("dump_sha256", "invalid"), ("dump_sha256", "A" * 64),
    ("dump_bytes", 0), ("dump_bytes", True), ("table_count", 0), ("table_count", 1.5),
    ("source_tables_sha256", "4" * 64), ("restore_proof_sha256", ""),
    ("snapshot_at", "2026-10-02"), ("signed_at", "2026-10-02T03:00:01+00:00"),
    ("backup_completed_at", "2026-10-02T02:00:00+00:00"),
    ("restore_verified_at", "2026-10-02T02:59:00+00:00"),
    ("snapshot_at", "2026-10-02T00:59:59+00:00"),
])
def test_signed_but_wrong_or_incomplete_recovery_is_rejected(proof, field, value):
    key, public, payload = proof
    payload[field] = value
    with pytest.raises(recovery.RecoveryAttestationError):
        verify(recovery.sign_attestation(payload, key), public)


@pytest.mark.parametrize("name", ["archive_restore", "deep_readiness", "table_counts", "fingerprints", "schema", "migration"])
@pytest.mark.parametrize("value", [False, 1, "true", None])
def test_every_restore_check_requires_literal_success(proof, name, value):
    key, public, payload = proof
    payload["checks"][name] = value
    with pytest.raises(recovery.RecoveryAttestationError):
        verify(recovery.sign_attestation(payload, key), public)


def test_freshness_uses_snapshot_not_a_new_signature(proof):
    key, public, payload = proof
    payload["snapshot_at"] = (NOW - timedelta(hours=2)).isoformat()
    assert verify(recovery.sign_attestation(payload, key), public)
    payload["snapshot_at"] = (NOW - timedelta(hours=2, microseconds=1)).isoformat()
    payload["signed_at"] = NOW.isoformat()
    with pytest.raises(recovery.RecoveryAttestationError):
        verify(recovery.sign_attestation(payload, key), public)


def test_missing_extra_duplicate_and_nonfinite_fields_are_rejected(proof):
    key, public, payload = proof
    for changed in ({k: v for k, v in payload.items() if k != "dump_sha256"},
                    {**payload, "operator_override": True},
                    {**payload, "checks": {**payload["checks"], "extra": True}}):
        with pytest.raises(recovery.RecoveryAttestationError):
            verify(recovery.sign_attestation(changed, key), public)
    valid = recovery.sign_attestation(payload, key)
    for malformed in (valid.replace('"payload":', '"payload":{},"payload":', 1),
                      '{"payload":NaN,"signature":"invalid"}', "{}", "[]", "not JSON", "x" * 20000):
        with pytest.raises(recovery.RecoveryAttestationError):
            verify(malformed, public)


@pytest.mark.parametrize("public", ["", "!not-base64!", base64.b64encode(b"short").decode()])
def test_invalid_trust_anchor_fails_closed(proof, public):
    key, _, payload = proof
    with pytest.raises(recovery.RecoveryAttestationError):
        verify(recovery.sign_attestation(payload, key), public)


def test_cli_uses_env_pins_repo_head_and_current_public_release(proof, monkeypatch, capsys):
    key, public, payload = proof
    env = {
        "PARKINGAI_RECOVERY_ATTESTATION": recovery.sign_attestation(payload, key),
        "PARKINGAI_RECOVERY_PUBLIC_KEY": public, "SUPABASE_PROJECT_REF": REF,
        "RELEASE_SHA": TARGET, "PUBLIC_API_URL": "https://api.parkingai.am",
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(recovery, "utc_now", lambda: NOW)
    monkeypatch.setattr(recovery, "current_repo_head", lambda: SCHEMA)
    seen = []
    monkeypatch.setattr(recovery, "read_live_release", lambda url: seen.append(url) or SOURCE)
    assert recovery.main([]) == 0
    assert seen == ["https://api.parkingai.am"]
    output = capsys.readouterr().out
    assert TARGET in output and "operator" in output.lower()
    assert REF not in output and public not in output and env["PARKINGAI_RECOVERY_ATTESTATION"] not in output
    monkeypatch.setattr(recovery, "read_live_release", lambda url: "c" * 40)
    assert recovery.main([]) == 1
    output = capsys.readouterr()
    assert env["PARKINGAI_RECOVERY_ATTESTATION"] not in output.err + output.out


def test_cli_missing_secret_and_unexpected_dependency_errors_never_leak(proof, monkeypatch, capsys):
    monkeypatch.delenv("PARKINGAI_RECOVERY_ATTESTATION", raising=False)
    assert recovery.main([]) == 1
    _, public, payload = proof
    monkeypatch.setenv("PARKINGAI_RECOVERY_ATTESTATION", "private-envelope-marker")
    monkeypatch.setenv("PARKINGAI_RECOVERY_PUBLIC_KEY", public)
    monkeypatch.setenv("SUPABASE_PROJECT_REF", REF)
    monkeypatch.setenv("RELEASE_SHA", TARGET)
    monkeypatch.setenv("PUBLIC_API_URL", "https://api.parkingai.am")
    def broken(_url):
        raise RuntimeError("private-envelope-marker")
    monkeypatch.setattr(recovery, "read_live_release", broken)
    assert recovery.main([]) == 1
    output = capsys.readouterr()
    assert "private-envelope-marker" not in output.out + output.err


def test_repository_head_resolves_without_database_access():
    assert recovery.current_repo_head() == SCHEMA


@pytest.mark.parametrize("url", ["http://api.parkingai.am", "https://other.example", "https://api.parkingai.am@other.example", "https://api.parkingai.am/path"])
def test_live_release_url_cannot_redirect_read_to_an_untrusted_origin(url):
    with pytest.raises(recovery.RecoveryAttestationError):
        recovery.read_live_release(url)


def test_live_release_uses_bounded_nonredirecting_public_read(monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=200, json=lambda: {"release_id": SOURCE})
    monkeypatch.setattr(recovery.requests, "get", get)
    assert recovery.read_live_release("https://api.parkingai.am/") == SOURCE
    assert calls == [("https://api.parkingai.am/", {"timeout": 10, "allow_redirects": False})]


@pytest.mark.parametrize("status,body", [(302, {"release_id": SOURCE}), (500, {"release_id": SOURCE}),
                                      (200, {"release_id": "unavailable"}), (200, []), (200, {})])
def test_live_release_cannot_be_assumed_from_failed_or_invalid_response(monkeypatch, status, body):
    monkeypatch.setattr(recovery.requests, "get", lambda *_args, **_kwargs:
                        SimpleNamespace(status_code=status, json=lambda: body))
    with pytest.raises(recovery.RecoveryAttestationError):
        recovery.read_live_release("https://api.parkingai.am")
