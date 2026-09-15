"""Rehearse an upgrade on a new copy and compare every original table value."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4


def _quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def _read_original(path, columns=None):
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        if columns is None:
            names = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            columns = {name: [row[1] for row in connection.execute("PRAGMA table_info(" + _quote(name) + ")")]
                       for name in names}
        rows = {}
        for table, fields in columns.items():
            values = connection.execute("SELECT " + ",".join(map(_quote, fields)) + " FROM " + _quote(table)).fetchall()
            rows[table] = {"count": len(values), "sha256": hashlib.sha256(repr(sorted(map(repr, values))).encode()).hexdigest()}
        return columns, rows


def _validate_existing_free_pass_backfill(source, candidate, changed):
    """Allow only the documented old importer for unlinked free demo passes.

    P0 seeds contain three free periods without cards/receipts. The existing
    finance importer links cards and adds explicit zero legacy_unknown rows.
    Every old receipt and all other old values must still be identical.
    """
    if not changed <= {"monthly_passes", "parking_cards", "payments"}:
        raise AssertionError("Migration changed unrelated original table values")

    def tables(path):
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            return {name: {row["id"]: dict(row) for row in connection.execute("SELECT * FROM " + _quote(name))}
                    for name in ("monthly_passes", "parking_cards", "payments")}

    before, after = tables(source), tables(candidate)
    links = set()
    if before["monthly_passes"].keys() != after["monthly_passes"].keys():
        raise AssertionError("Migration added or removed monthly periods")
    for key, old in before["monthly_passes"].items():
        new = after["monthly_passes"][key]
        if old == new:
            continue
        if old["card_id"] is not None or old["price"] != 0 or new["card_id"] is None:
            raise AssertionError("Unexpected monthly period mutation")
        if {**old, "card_id": new["card_id"]} != new:
            raise AssertionError("Migration changed original monthly business data")
        card = after["parking_cards"].get(new["card_id"])
        if card is None or any(card[field] != old[source_field] for field, source_field in
                               (("code", "pass_code"), ("customer_id", "customer_id"),
                                ("vehicle_id", "vehicle_id"), ("created_at", "created_at"))):
            raise AssertionError("Imported card does not match its original period")
        links.add(new["card_id"])
    for table in ("parking_cards", "payments"):
        if any(after[table].get(key) != value for key, value in before[table].items()):
            raise AssertionError("Migration changed an existing card or receipt")
    new_cards = after["parking_cards"].keys() - before["parking_cards"].keys()
    if not new_cards <= links:
        raise AssertionError("Migration added unrelated cards")
    extras = after["payments"].keys() - before["payments"].keys()
    expected_periods = {str(key) for key, value in before["monthly_passes"].items()
                        if value["price"] == 0 and not any(row["source_type"] == "monthly_pass"
                            and row["source_id"] == str(key) and row["kind"] == "receipt"
                            for row in before["payments"].values())}
    imported_periods = set()
    for key in extras:
        row = after["payments"][key]
        if (row["source_type"] != "monthly_pass" or row["source_id"] not in expected_periods
                or row["kind"] != "receipt" or row["amount"] != 0 or row["method"] != "legacy_unknown"
                or any(row[field] is not None for field in ("site_id", "collected_by_id", "shift_id", "original_payment_id"))
                or row["idempotency_key"] != "receipt:monthly_pass:" + row["source_id"] or not row["reason"]):
            raise AssertionError("Unexpected financial backfill")
        period = before["monthly_passes"][int(row["source_id"])]
        expected_time = datetime.fromisoformat(period["created_at"]).replace(tzinfo=timezone.utc).astimezone(
            timezone(timedelta(hours=7))).replace(tzinfo=None)
        if datetime.fromisoformat(row["created_at"]) != expected_time:
            raise AssertionError("Imported free receipt has unexpected time attribution")
        imported_periods.add(row["source_id"])
    if imported_periods != expected_periods or len(extras) != len(imported_periods):
        raise AssertionError("Free legacy receipt import is incomplete or duplicated")
    return {"card_links": len(links), "new_cards": len(new_cards), "zero_legacy_receipts": len(extras),
            "original_receipts_unchanged": len(before["payments"]), "all_other_original_values_unchanged": True}


def verify(source):
    source = source.resolve()
    marker = json.loads(Path(str(source) + ".demo.json").read_text(encoding="utf-8"))
    if (marker.get("profile") != "single-lot-academic-v1" or marker.get("synthetic_history") is not True
            or marker.get("parkingai_demo") is not True):
        raise ValueError("Only an explicitly marked synthetic one-lot source is accepted")
    if not source.is_file():
        raise FileNotFoundError(source)
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["AI_ENABLED"] = "false"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from database import create_database_engine, _unicode_casefold
    from db_rollout import check_database_readiness, initialize_database, migrate_copy

    candidate = source.parent / ("upgraded-" + uuid4().hex + ".db")
    columns, original = _read_original(source)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    migrate_copy(source, candidate)
    _, migrated = _read_original(candidate, columns)
    changed = {table for table in original if original[table] != migrated[table]}
    finance_backfill = _validate_existing_free_pass_backfill(source, candidate, changed) if changed else None
    # Repeated setup must not rewrite saved history or fabricate billing data.
    initialize_database(candidate)
    _, repeated = _read_original(candidate, columns)
    if migrated != repeated or source_hash != hashlib.sha256(source.read_bytes()).hexdigest():
        raise AssertionError("Migration replay changed history or source")
    with sqlite3.connect(candidate.as_uri() + "?mode=ro", uri=True) as connection:
        connection.create_function("unicode_casefold", 1, _unicode_casefold, deterministic=True)
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise AssertionError("SQLite integrity failure")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise AssertionError("Foreign-key failure")
        legacy = connection.execute("SELECT COUNT(*) FROM parking_sessions WHERE billing_policy_version IS NULL").fetchone()[0]
        if "billing_policy_version" not in columns.get("parking_sessions", []) and legacy != original["parking_sessions"]["count"]:
            raise AssertionError("Migration invented legacy billing snapshots")
    engine = create_database_engine("sqlite:///" + candidate.as_posix())
    try:
        check_database_readiness(engine)
    finally:
        engine.dispose()
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "result": "PASS", "source": str(source),
            "candidate": str(candidate), "source_unchanged": True, "original_tables_equal": len(original) - len(changed),
            "tables_with_expected_free_pass_backfill": sorted(changed), "existing_finance_backfill": finance_backfill,
            "original_row_counts": {name: value["count"] for name, value in original.items()},
            "legacy_sessions_without_invented_snapshot": legacy, "repeat_migration": "PASS", "readiness": "PASS"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], "original_tables_equal": result["original_tables_equal"],
                      "legacy_sessions": result["legacy_sessions_without_invented_snapshot"], "output": str(args.output)}))
