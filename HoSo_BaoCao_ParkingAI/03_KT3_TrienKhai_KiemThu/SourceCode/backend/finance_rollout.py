"""Explicit legacy backfill and shared SQLite financial/card backstops.

Only deployment tooling calls backfill_legacy_finance. Importing this module
never connects to a database or infers a historical operator/payment method.
"""

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text

from core.clock import BUSINESS_TZ
from core.money import require_exact_vnd


MONTHLY_CARD_SQLITE_TRIGGERS = (
    "CREATE TRIGGER IF NOT EXISTS trg_monthly_paid_immutable_update BEFORE UPDATE ON monthly_passes FOR EACH ROW WHEN ((OLD.card_id IS NOT NULL AND NEW.card_id IS NOT OLD.card_id) OR (EXISTS (SELECT 1 FROM payments WHERE source_type = 'monthly_pass' AND source_id = CAST(OLD.id AS TEXT) AND kind = 'receipt') AND (NEW.customer_id IS NOT OLD.customer_id OR NEW.vehicle_id IS NOT OLD.vehicle_id OR NEW.pass_code IS NOT OLD.pass_code OR NEW.price IS NOT OLD.price OR NEW.start_date IS NOT OLD.start_date OR NEW.end_date IS NOT OLD.end_date))) BEGIN SELECT RAISE(ABORT, 'paid monthly period is immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS trg_monthly_paid_immutable_delete BEFORE DELETE ON monthly_passes FOR EACH ROW WHEN EXISTS (SELECT 1 FROM payments WHERE source_type = 'monthly_pass' AND source_id = CAST(OLD.id AS TEXT) AND kind = 'receipt') BEGIN SELECT RAISE(ABORT, 'paid monthly period is immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS trg_monthly_card_binding_insert BEFORE INSERT ON monthly_passes FOR EACH ROW WHEN NEW.card_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM parking_cards WHERE id = NEW.card_id AND customer_id = NEW.customer_id AND vehicle_id = NEW.vehicle_id) BEGIN SELECT RAISE(ABORT, 'monthly card binding mismatch'); END",
    "CREATE TRIGGER IF NOT EXISTS trg_monthly_card_binding_update BEFORE UPDATE OF card_id, customer_id, vehicle_id ON monthly_passes FOR EACH ROW WHEN NEW.card_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM parking_cards WHERE id = NEW.card_id AND customer_id = NEW.customer_id AND vehicle_id = NEW.vehicle_id) BEGIN SELECT RAISE(ABORT, 'monthly card binding mismatch'); END",
    "CREATE TRIGGER IF NOT EXISTS trg_parking_card_identity_immutable BEFORE UPDATE ON parking_cards FOR EACH ROW WHEN EXISTS (SELECT 1 FROM monthly_passes WHERE card_id = OLD.id) AND (NEW.id IS NOT OLD.id OR NEW.code IS NOT OLD.code OR NEW.customer_id IS NOT OLD.customer_id OR NEW.vehicle_id IS NOT OLD.vehicle_id) BEGIN SELECT RAISE(ABORT, 'parking card identity is immutable'); END",
)


def validate_finance_invariants(connection) -> None:
    """Read-only checks shared by both database deployment gates."""
    invalid_confirmation_receipt = connection.execute(text(
        "SELECT session.id FROM parking_sessions session LEFT JOIN payments receipt "
        "ON receipt.source_type = 'parking_session' AND receipt.source_id = session.id AND receipt.kind = 'receipt' "
        "WHERE session.checkout_quote_hash IS NOT NULL AND ("
        "(session.parking_fee = 0 AND receipt.id IS NOT NULL) OR "
        "(session.parking_fee > 0 AND (receipt.id IS NULL OR receipt.amount != session.parking_fee "
        "OR receipt.method != session.checkout_payment_method OR receipt.collected_by_id IS NULL "
        "OR receipt.collected_by_id != session.staff_out_id))) ORDER BY session.id LIMIT 1"
    )).first()
    if invalid_confirmation_receipt:
        raise RuntimeError(
            "Bất biến checkout confirmation/phiếu thu không hợp lệ: "
            f"{tuple(invalid_confirmation_receipt)}"
        )
    invalid_coverage = connection.execute(text(
        "SELECT session.id FROM parking_sessions session LEFT JOIN monthly_passes period ON period.id = session.monthly_pass_id "
        "WHERE session.monthly_coverage_end IS NOT NULL AND (period.id IS NULL "
        "OR session.monthly_coverage_end < period.end_date "
        "OR CAST(session.monthly_coverage_end AS TEXT) < substr(CAST(session.check_in_time AS TEXT), 1, 10)) "
        "ORDER BY session.id LIMIT 1"
    )).first()
    if invalid_coverage:
        raise RuntimeError(f"Bất biến snapshot quyền lợi vé tháng không hợp lệ: {tuple(invalid_coverage)}")
    invalid_card = connection.execute(text(
        "SELECT period.id FROM monthly_passes period LEFT JOIN parking_cards card ON card.id = period.card_id "
        "WHERE period.card_id IS NOT NULL AND (card.id IS NULL OR card.customer_id != period.customer_id "
        "OR card.vehicle_id != period.vehicle_id) ORDER BY period.id LIMIT 1"
    )).first()
    if invalid_card:
        raise RuntimeError(f"Bất biến liên kết thẻ/vé tháng không hợp lệ: {tuple(invalid_card)}")
    invalid_receipt = connection.execute(text(
        "SELECT receipt.id FROM payments receipt "
        "LEFT JOIN monthly_passes period ON receipt.source_type = 'monthly_pass' AND receipt.source_id = CAST(period.id AS TEXT) "
        "LEFT JOIN parking_sessions session ON receipt.source_type = 'parking_session' AND receipt.source_id = session.id "
        "WHERE receipt.kind = 'receipt' AND ((receipt.source_type = 'monthly_pass' AND (period.id IS NULL OR receipt.amount != period.price)) "
        "OR (receipt.source_type = 'parking_session' AND (session.id IS NULL OR session.status != 'completed' OR session.parking_fee IS NULL OR receipt.amount != session.parking_fee))) "
        "ORDER BY receipt.id LIMIT 1"
    )).first()
    if invalid_receipt:
        raise RuntimeError(f"Bất biến phiếu thu/nguồn thu không hợp lệ: {tuple(invalid_receipt)}")
    invalid_refund = connection.execute(text(
        "SELECT refund.id FROM payments refund LEFT JOIN payments original ON original.id = refund.original_payment_id "
        "WHERE refund.kind = 'refund' AND (original.id IS NULL OR original.kind != 'receipt' "
        "OR refund.source_type != original.source_type OR refund.source_id != original.source_id "
        "OR refund.created_at < original.created_at OR original.amount < "
        "(SELECT SUM(amount) FROM payments WHERE kind = 'refund' AND original_payment_id = original.id)) "
        "ORDER BY refund.id LIMIT 1"
    )).first()
    if invalid_refund:
        raise RuntimeError(f"Bất biến hoàn tiền không hợp lệ: {tuple(invalid_refund)}")


def backfill_legacy_finance(connection) -> None:
    """Backfill a migrated SQLite candidate inside the caller's transaction.

    Existing monthly created_at is UTC metadata, used as the best available
    historical collection instant; it is not a verified historical payment
    timestamp. Session checkout time already uses naive business-local time.
    Imported receipts have unknown method, no shift, and no inferred collector.
    A source that already has a receipt is left completely unchanged.
    """
    for period in connection.execute(text(
        "SELECT id, pass_code, customer_id, vehicle_id, created_at FROM monthly_passes "
        "WHERE card_id IS NULL AND pass_code IS NOT NULL ORDER BY id"
    )).mappings().all():
        card = connection.execute(text("SELECT id, customer_id, vehicle_id FROM parking_cards WHERE code = :code"), {"code": period["pass_code"]}).mappings().first()
        if card is None:
            card_id = connection.execute(text(
                "INSERT INTO parking_cards (code, customer_id, vehicle_id, created_at) "
                "VALUES (:code, :customer, :vehicle, :created) RETURNING id"
            ), {"code": period["pass_code"], "customer": period["customer_id"], "vehicle": period["vehicle_id"], "created": period["created_at"]}).scalar_one()
        else:
            if card["customer_id"] != period["customer_id"] or card["vehicle_id"] != period["vehicle_id"]:
                raise RuntimeError(f"Legacy monthly period {period['id']} conflicts with its physical card owner")
            card_id = card["id"]
        connection.execute(text("UPDATE monthly_passes SET card_id = :card WHERE id = :id"), {"card": card_id, "id": period["id"]})

    sources = (
        ("parking_session", "SELECT id, parking_fee AS amount, check_out_time AS collected_at FROM parking_sessions WHERE status = 'completed' AND parking_fee IS NOT NULL AND checkout_quote_hash IS NULL"),
        ("monthly_pass", "SELECT id, price AS amount, created_at AS collected_at FROM monthly_passes"),
    )
    for source_type, source_sql in sources:
        rows = connection.execute(text(
            f"SELECT source.* FROM ({source_sql}) AS source WHERE NOT EXISTS "
            "(SELECT 1 FROM payments WHERE source_type = :source_type "
            "AND source_id = CAST(source.id AS TEXT) AND kind = 'receipt')"
        ), {"source_type": source_type}).mappings().all()
        for row in rows:
            amount = require_exact_vnd(row["amount"])
            when = row["collected_at"]
            if isinstance(when, str):
                when = datetime.fromisoformat(when)
            if when is None:
                raise RuntimeError(f"Legacy receipt {source_type}:{row['id']} has no collection timestamp")
            if source_type == "monthly_pass":
                when = when.replace(tzinfo=timezone.utc).astimezone(BUSINESS_TZ).replace(tzinfo=None)
            key = f"receipt:{source_type}:{row['id']}"
            connection.execute(text(
                "INSERT INTO payments (id, source_type, source_id, kind, amount, method, "
                "collected_by_id, shift_id, created_at, idempotency_key, original_payment_id, reason) "
                "VALUES (:id, :source, :source_id, 'receipt', :amount, 'legacy_unknown', "
                "NULL, NULL, :created, :key, NULL, :reason)"
            ), {"id": str(uuid5(NAMESPACE_URL, key)), "source": source_type, "source_id": str(row["id"]),
                "amount": amount, "created": when.isoformat(sep=" ", timespec="microseconds"), "key": key,
                "reason": "Nhập dữ liệu cũ; thời điểm vé tháng dựa trên ngày tạo, chưa ghi nhận phương thức/người thu."})
