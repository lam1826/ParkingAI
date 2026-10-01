"""Verify trusted-operator recovery evidence; CI does not possess the backup.

The local signing caller must perform the real dump/restore checks. This module
authenticates its evidence and release binding; it never creates a recovery point
and cannot independently prove the private backup's continued availability.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timedelta, timezone

from alembic.config import Config
from alembic.script import ScriptDirectory
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
import requests


DOMAIN = b"ParkingAI release recovery attestation v1\x00"
MAX_SNAPSHOT_AGE = timedelta(hours=2)
MAX_ENVELOPE_BYTES = 16384
CHECKS = frozenset({"archive_restore", "deep_readiness", "table_counts", "fingerprints", "schema", "migration"})
FIELDS = frozenset({
    "version", "kind", "repository", "fly_app", "scope", "source_fingerprint", "target_sha",
    "source_release", "source_schema", "verified_target_schema", "snapshot_at", "backup_completed_at",
    "restore_verified_at", "signed_at", "dump_sha256", "dump_bytes", "table_count",
    "source_tables_sha256", "restored_tables_sha256", "restore_proof_sha256", "checks",
})


class RecoveryAttestationError(ValueError):
    """Safe error category: never includes attestation or credential contents."""


def _reject(code: str):
    raise RecoveryAttestationError(f"Recovery proof rejected ({code})")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical(payload: dict) -> bytes:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeError):
        _reject("encoding")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _reject("duplicate-field")
        result[key] = value
    return result


def _base64(value, size):
    try:
        if not isinstance(value, str):
            _reject("key-or-signature")
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) != size or base64.b64encode(decoded).decode("ascii") != value:
            _reject("key-or-signature")
        return decoded
    except (ValueError, UnicodeError):
        _reject("key-or-signature")


def _hex(value, size):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(size) + r"}", value) is not None


def source_fingerprint(project_ref: str) -> str:
    if not isinstance(project_ref, str) or not re.fullmatch(r"[a-z]{20}", project_ref):
        _reject("source-identity")
    return hashlib.sha256(f"supabase:{project_ref}:postgres:public".encode("ascii")).hexdigest()


def sign_attestation(payload: dict, private_key: Ed25519PrivateKey) -> str:
    """Cryptographic helper only; the caller must verify real local recovery first.

    It intentionally does not claim that supplying a payload performs or proves
    a restore. The private key is accepted in memory, never printed or saved.
    """
    if not isinstance(payload, dict) or not isinstance(private_key, Ed25519PrivateKey):
        _reject("signing-input")
    signature = private_key.sign(DOMAIN + _canonical(payload))
    return json.dumps({"payload": payload, "signature": base64.b64encode(signature).decode("ascii")},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _utc_timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value
    ):
        _reject("timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _reject("timestamp")


def verify_attestation(envelope: str, public_key: str, *, expected_target_sha: str,
                       expected_source_release: str, expected_source_fingerprint: str,
                       expected_target_schema: str, now: datetime | None = None) -> dict:
    if not isinstance(envelope, str):
        _reject("envelope")
    try:
        if not 0 < len(envelope.encode("utf-8")) <= MAX_ENVELOPE_BYTES:
            _reject("envelope")
        data = json.loads(envelope, object_pairs_hook=_unique_object,
                          parse_constant=lambda _value: _reject("encoding"))
    except (ValueError, TypeError, RecursionError, UnicodeError):
        _reject("envelope")
    if not isinstance(data, dict) or set(data) != {"payload", "signature"} or not isinstance(data["payload"], dict):
        _reject("envelope")
    payload = data["payload"]
    try:
        Ed25519PublicKey.from_public_bytes(_base64(public_key, 32)).verify(
            _base64(data["signature"], 64), DOMAIN + _canonical(payload))
    except (InvalidSignature, ValueError, TypeError):
        _reject("signature")

    if set(payload) != FIELDS or type(payload["version"]) is not int or payload["version"] != 1:
        _reject("contract")
    for key, required in (("kind", "parkingai-local-recovery"), ("repository", "lam1826/ParkingAI"),
                          ("fly_app", "parkingai-api-lam1826"), ("scope", "postgres:public")):
        if payload[key] != required:
            _reject("scope")
    if not _hex(expected_target_sha, 40) or not _hex(expected_source_release, 40) or not _hex(expected_source_fingerprint, 64):
        _reject("trusted-context")
    if (payload["target_sha"] != expected_target_sha or payload["source_release"] != expected_source_release
            or payload["source_fingerprint"] != expected_source_fingerprint):
        _reject("release-binding")
    if (not isinstance(expected_target_schema, str) or not re.fullmatch(r"\d{8}_\d{2}", expected_target_schema)
            or payload["verified_target_schema"] != expected_target_schema
            or not isinstance(payload["source_schema"], str)
            or not re.fullmatch(r"\d{8}_\d{2}", payload["source_schema"])):
        _reject("schema")
    for key in ("dump_sha256", "source_tables_sha256", "restored_tables_sha256", "restore_proof_sha256"):
        if not _hex(payload[key], 64):
            _reject("digest")
    if payload["source_tables_sha256"] != payload["restored_tables_sha256"]:
        _reject("restored-data")
    if any(type(payload[key]) is not int or payload[key] <= 0 for key in ("dump_bytes", "table_count")):
        _reject("backup-size")
    if (not isinstance(payload["checks"], dict) or set(payload["checks"]) != CHECKS
            or any(value is not True for value in payload["checks"].values())):
        _reject("restore-checks")
    times = [_utc_timestamp(payload[key]) for key in (
        "snapshot_at", "backup_completed_at", "restore_verified_at", "signed_at")]
    instant = now or utc_now()
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        _reject("clock")
    instant = instant.astimezone(timezone.utc)
    if times != sorted(times) or times[-1] > instant or instant - times[0] > MAX_SNAPSHOT_AGE:
        _reject("freshness")
    return payload


def current_repo_head() -> str:
    config = Config(str(Path(__file__).resolve().parent / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        _reject("migration-head")
    return heads[0]


def read_live_release(api_url: str) -> str:
    if not isinstance(api_url, str) or api_url.rstrip("/") != "https://api.parkingai.am":
        _reject("api-origin")
    try:
        response = requests.get("https://api.parkingai.am/", timeout=10, allow_redirects=False)
        if response.status_code != 200:
            _reject("live-release")
        body = response.json()
        release = body.get("release_id") if isinstance(body, dict) else None
        if not _hex(release, 40):
            _reject("live-release")
        return release
    except (requests.RequestException, ValueError, TypeError):
        _reject("live-release")


def main(argv: list[str] | None = None) -> int:
    try:
        if list(sys.argv[1:] if argv is None else argv):
            _reject("arguments")
        required = {name: os.environ.get(name, "") for name in (
            "PARKINGAI_RECOVERY_ATTESTATION", "PARKINGAI_RECOVERY_PUBLIC_KEY", "SUPABASE_PROJECT_REF",
            "RELEASE_SHA", "PUBLIC_API_URL")}
        if not all(required.values()):
            _reject("configuration")
        target = required["RELEASE_SHA"]
        verify_attestation(required["PARKINGAI_RECOVERY_ATTESTATION"], required["PARKINGAI_RECOVERY_PUBLIC_KEY"],
            expected_target_sha=target,
            expected_source_release=read_live_release(required["PUBLIC_API_URL"]),
            expected_source_fingerprint=source_fingerprint(required["SUPABASE_PROJECT_REF"]),
            expected_target_schema=current_repo_head())
        print(f"Trusted operator recovery attestation verified for release {target}; backup retained privately.")
        return 0
    except Exception:
        # Third-party exceptions can contain URLs/response text. Emit no body,
        # token, proof or connection detail even when a dependency fails.
        print("Recovery attestation gate failed; inspect private recovery evidence and configured release bindings.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
