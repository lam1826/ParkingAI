"""Known predecessor guards and copy-only schema changes for parking-fee credits."""
import re
from sqlalchemy import inspect
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import sqlite

from expansion.session_payment_legacy_guards import PRE_SESSION_CREDIT_ONLINE_GUARDS

PRE_CREDIT_SHARED_GUARDS = {'trg_cash_shift_site_immutable': 'CREATE TRIGGER IF NOT EXISTS trg_cash_shift_site_immutable BEFORE UPDATE OF site_id '
                                  "ON cash_shifts WHEN NEW.site_id IS NOT OLD.site_id BEGIN SELECT RAISE(ABORT, 'cash "
                                  "shift site is immutable'); END",
 'trg_paid_parking_session_delete': 'CREATE TRIGGER IF NOT EXISTS trg_paid_parking_session_delete BEFORE DELETE ON '
                                    'parking_sessions WHEN EXISTS (SELECT 1 FROM payments WHERE source_type = '
                                    "'parking_session' AND source_id = OLD.id) BEGIN SELECT RAISE(ABORT, 'paid parking "
                                    "session cannot be deleted'); END",
 'trg_parking_sessions_checkout_confirmation_update': 'CREATE TRIGGER IF NOT EXISTS '
                                                      'trg_parking_sessions_checkout_confirmation_update BEFORE UPDATE '
                                                      'ON parking_sessions FOR EACH ROW WHEN ((NEW.checkout_quote_hash '
                                                      'IS NOT OLD.checkout_quote_hash OR NEW.checkout_payment_method '
                                                      'IS NOT OLD.checkout_payment_method) AND NOT (OLD.status IS '
                                                      "'checking_out' AND NEW.status IS 'completed' AND "
                                                      'OLD.checkout_quote_hash IS NULL AND OLD.checkout_payment_method '
                                                      'IS NULL)) OR ((NEW.checkout_quote_hash IS NULL AND '
                                                      'NEW.checkout_payment_method IS NOT NULL) OR '
                                                      '(NEW.checkout_quote_hash IS NOT NULL AND '
                                                      "(typeof(NEW.checkout_quote_hash) != 'text' OR "
                                                      'length(NEW.checkout_quote_hash) != 64 OR '
                                                      'length(CAST(NEW.checkout_quote_hash AS BLOB)) != 64 OR '
                                                      "NEW.checkout_quote_hash GLOB '*[^0-9a-f]*' OR NEW.status IS NOT "
                                                      "'completed' OR NEW.staff_out_id IS NULL OR NEW.parking_fee IS "
                                                      'NULL OR NEW.parking_fee < 0 OR (NEW.parking_fee = 0 AND '
                                                      'NEW.checkout_payment_method IS NOT NULL) OR (NEW.parking_fee > '
                                                      "0 AND COALESCE(NEW.checkout_payment_method, '') NOT IN ('cash', "
                                                      "'transfer'))))) BEGIN SELECT RAISE(ABORT, 'checkout "
                                                      "confirmation invalid or immutable'); END",
 'trg_payment_receipt_source': 'CREATE TRIGGER IF NOT EXISTS trg_payment_receipt_source BEFORE INSERT ON payments WHEN '
                               "NEW.kind = 'receipt' AND ((NEW.source_type = 'parking_session' AND NOT EXISTS (SELECT "
                               "1 FROM parking_sessions WHERE id = NEW.source_id AND status = 'completed' AND "
                               "parking_fee = NEW.amount)) OR (NEW.source_type = 'monthly_pass' AND NOT EXISTS (SELECT "
                               '1 FROM monthly_passes WHERE CAST(id AS TEXT) = NEW.source_id AND price = NEW.amount))) '
                               "BEGIN SELECT RAISE(ABORT, 'payment source or amount invalid'); END",
 'trg_payment_site_guard': 'CREATE TRIGGER IF NOT EXISTS trg_payment_site_guard BEFORE INSERT ON payments WHEN\n'
                           "        (NEW.site_id IS NOT NULL AND NEW.kind = 'receipt' AND (\n"
                           "            (NEW.source_type = 'monthly_pass' AND NEW.site_id IS NOT (SELECT o.site_id "
                           "FROM monthly_passes p JOIN portal_orders o ON p.renewal_key='portal:' || o.id WHERE "
                           'CAST(p.id AS TEXT)=NEW.source_id)) OR\n'
                           "            (NEW.source_type = 'parking_session' AND NEW.site_id IS NOT (SELECT z.site_id "
                           'FROM parking_sessions p JOIN parking_slots s ON s.id=p.parking_slot_id JOIN zones z ON '
                           'z.id=s.zone_id WHERE p.id=NEW.source_id))))\n'
                           "        OR (NEW.kind = 'refund' AND NEW.site_id IS NOT (SELECT site_id FROM payments WHERE "
                           'id=NEW.original_payment_id))\n'
                           '        OR (NEW.shift_id IS NOT NULL AND EXISTS (SELECT 1 FROM cash_shifts c WHERE '
                           'c.id=NEW.shift_id AND c.site_id IS NOT NULL AND c.site_id IS NOT NEW.site_id))\n'
                           "        BEGIN SELECT RAISE(ABORT, 'payment site mismatch'); END"}
PRE_CREDIT_GUARDS = {**PRE_CREDIT_SHARED_GUARDS, **PRE_SESSION_CREDIT_ONLINE_GUARDS}


def ensure_credit_tables(engine):
    # Create only new empty tables; referenced historical records are untouched.
    import models
    from database import Base
    for name in ("session_fee_quotes", "session_fee_credits"):
        Base.metadata.tables[name].create(engine, checkfirst=True)


def migrate_session_credit(engine):
    from expansion_rollout import _signature
    from expansion.timed_parking_rollout import _replace_check
    inspector = inspect(engine)
    exists = inspector.has_table("online_payment_links")
    needs_rebuild = False
    if exists:
        columns = {c["name"]: c for c in inspector.get_columns("online_payment_links")}
        checks = {c["name"]: c["sqltext"] for c in inspector.get_check_constraints("online_payment_links")}
        expected = "(order_id IS NOT NULL AND session_quote_id IS NULL) OR (order_id IS NULL AND session_quote_id IS NOT NULL)"
        target = checks.get("ck_online_link_target")
        if target is not None and _signature(target) != _signature(expected):
            raise RuntimeError("Unknown online payment target CHECK; migration refused")
        if "session_quote_id" not in columns:
            if columns["order_id"]["nullable"] or target is not None:
                raise RuntimeError("Unknown predecessor online payment target schema")
            needs_rebuild = True
        elif not columns["order_id"]["nullable"] or target is None:
            raise RuntimeError("Incomplete online payment target schema")
    ensure_credit_tables(engine)
    raw = engine.raw_connection()
    try:
        raw.commit()
        fk = raw.execute("PRAGMA foreign_keys").fetchone()[0]
        legacy = raw.execute("PRAGMA legacy_alter_table").fetchone()[0]
        raw.execute("PRAGMA foreign_keys=OFF")
        raw.execute("PRAGMA legacy_alter_table=ON")
        raw.execute("BEGIN IMMEDIATE")
        try:
            if needs_rebuild:
                ddl = raw.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='online_payment_links'").fetchone()[0]
                ddl, count = re.subn(r'(\border_id\s+VARCHAR\(36\))\s+NOT\s+NULL', r'\1', ddl, flags=re.I)
                if count != 1:
                    raise RuntimeError("Unknown online payment order column")
                constraint = re.search(r",\s*(?:CONSTRAINT\b|PRIMARY\s+KEY\b|FOREIGN\s+KEY\b|UNIQUE\s*\(|CHECK\s*\()", ddl, re.I)
                if constraint is None:
                    raise RuntimeError("Unknown online payment table constraints")
                at = constraint.start()
                ddl = ddl[:at] + ', session_quote_id VARCHAR(36) REFERENCES session_fee_quotes(id)' + ddl[at:]
                ddl = _replace_check(ddl, "ck_online_link_target", expected)
                ddl, count = re.subn(r'^CREATE\s+TABLE\s+"?online_payment_links"?\s*\(', 'CREATE TABLE "_credit_online_links" (', ddl, count=1, flags=re.I)
                if count != 1:
                    raise RuntimeError("Unknown online payment CREATE TABLE")
                objects = raw.execute("SELECT sql FROM sqlite_master WHERE tbl_name='online_payment_links' AND type IN ('index','trigger') AND sql IS NOT NULL ORDER BY type,name").fetchall()
                names = [r[1] for r in raw.execute('PRAGMA table_xinfo("online_payment_links")') if r[6] == 0]
                quoted = ','.join('"' + n.replace('"','""') + '"' for n in names)
                count = raw.execute('SELECT COUNT(*) FROM online_payment_links').fetchone()[0]
                raw.execute(ddl)
                raw.execute(f'INSERT INTO _credit_online_links ({quoted}) SELECT {quoted} FROM online_payment_links')
                if raw.execute('SELECT COUNT(*) FROM _credit_online_links').fetchone()[0] != count:
                    raise RuntimeError("Online mapping rows changed")
                raw.execute('DROP TABLE online_payment_links')
                raw.execute('ALTER TABLE _credit_online_links RENAME TO online_payment_links')
                for (sql,) in objects:
                    raw.execute(sql)
                raw.execute('CREATE UNIQUE INDEX uq_online_payment_links_session_quote_id ON online_payment_links(session_quote_id)')
            for name, old in PRE_CREDIT_GUARDS.items():
                row = raw.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",(name,)).fetchone()
                if row and _signature(row[0].replace("IF NOT EXISTS ","")) == _signature(old.replace("IF NOT EXISTS ","")):
                    raw.execute(f'DROP TRIGGER "{name}"')
            if raw.execute("PRAGMA foreign_key_check").fetchone():
                raise RuntimeError("Foreign key failure after online credit schema migration")
            raw.commit()
        except BaseException:
            raw.rollback()
            raise
        finally:
            raw.execute(f"PRAGMA legacy_alter_table={int(legacy)}")
            raw.execute(f"PRAGMA foreign_keys={int(fk)}")
    finally:
        raw.close()
