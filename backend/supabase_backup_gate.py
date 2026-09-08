"""Validate Supabase backup metadata before a production schema migration."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


MAX_BACKUP_AGE = timedelta(hours=36)


def _timestamp(value) -> datetime | None:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def validate_backup_metadata(payload: dict, *, now: datetime | None = None) -> str:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if payload.get("pitr_enabled") is True:
        latest = _timestamp((payload.get("physical_backup_data") or {}).get("latest_physical_backup_date_unix"))
        if latest is None or latest <= now:
            return "PITR enabled"

    completed = [
        _timestamp(item.get("inserted_at"))
        for item in payload.get("backups", [])
        if isinstance(item, dict) and str(item.get("status", "")).upper() == "COMPLETED"
    ]
    completed = [stamp for stamp in completed if stamp is not None and stamp <= now]
    if completed and now - max(completed) <= MAX_BACKUP_AGE:
        return f"completed backup at {max(completed).isoformat()}"
    raise RuntimeError("No active PITR or completed Supabase backup within the last 36 hours")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        raise SystemExit("Usage: python supabase_backup_gate.py <backup-metadata.json>")
    path = Path(args[0])
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Supabase backup response must be a JSON object")
    mode = validate_backup_metadata(payload)
    print(f"Supabase recovery gate passed: {mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
