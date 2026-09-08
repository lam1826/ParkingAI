"""Bounded durable-inbox recovery and in-app reminders; no external payment I/O.

Run explicitly from the maintenance job. Each item commits independently and
uses the same transaction locks as HTTP confirmation; safe to run concurrently.
"""
from datetime import timedelta

from sqlalchemy import String, cast, literal, select

from core.clock import business_now
from expansion.portal_models import PortalPaymentEvent, PortalOrder, PortalAccountLink, PortalNotification
from expansion.portal_service import process_event, _lock_order_context, _notify
from models.monthly_pass import MonthlyPass


def run_portal_maintenance(db, limit=100):
    limit = max(1, min(int(limit), 500))
    now = business_now()
    result = {"processed": 0, "retry": 0, "expired": 0, "reminders": 0}
    event_ids = list(db.scalars(select(PortalPaymentEvent.id).where(PortalPaymentEvent.status == "received",
        (PortalPaymentEvent.next_attempt_at.is_(None)) | (PortalPaymentEvent.next_attempt_at <= now))
        .order_by(PortalPaymentEvent.received_at).limit(limit)))
    for event_id in event_ids:
        try:
            process_event(db, event_id)
            result["processed"] += 1
        except Exception:
            db.rollback()
            event = db.get(PortalPaymentEvent, event_id)
            if event and event.status == "received":
                event.attempts += 1
                event.next_attempt_at = now + timedelta(seconds=min(300, 2 ** min(event.attempts, 8)))
                event.error_code = "fulfillment_retry"
                db.commit()
                result["retry"] += 1
    order_ids = list(db.scalars(select(PortalOrder.id).where(PortalOrder.status == "pending", PortalOrder.expires_at < now)
        .order_by(PortalOrder.expires_at).limit(limit)))
    for identity in order_ids:
        order = _lock_order_context(db, identity)
        received = db.scalar(select(PortalPaymentEvent.id).where(PortalPaymentEvent.order_id == identity,
            PortalPaymentEvent.status == "received"))
        if order.status == "pending" and order.expires_at < now and received is None:
            order.status = "expired"
            result["expired"] += 1
        db.commit()
    for days in (1, 7):
        remaining = limit - result["reminders"]
        if remaining <= 0:
            break
        key = literal("pass:") + cast(MonthlyPass.id, String) + literal(f":expires:{days}")
        already_notified = select(PortalNotification.id).where(PortalNotification.event_key == key).exists()
        rows = list(db.scalars(select(MonthlyPass).join(PortalAccountLink, PortalAccountLink.customer_id == MonthlyPass.customer_id)
            .where(MonthlyPass.is_active.is_(True), MonthlyPass.end_date == now.date() + timedelta(days=days), ~already_notified)
            .order_by(MonthlyPass.id).limit(remaining)))
        for period in rows:
            # Filter before LIMIT so later passes are reached on the next run.
            # The account lock and second lookup handle concurrent schedulers.
            from services.payment_service import lock_cash_operator
            user_id = db.scalar(select(PortalAccountLink.user_id).where(PortalAccountLink.customer_id == period.customer_id))
            if user_id is None:
                continue
            lock_cash_operator(db, user_id)
            db.refresh(period)
            event_key = f"pass:{period.id}:expires:{days}"
            if (period.is_active and period.end_date == now.date() + timedelta(days=days)
                    and not db.scalar(select(PortalNotification.id).where(PortalNotification.event_key == event_key))):
                _notify(db, period.customer_id, event_key,
                    f"Kỳ vé #{period.id} còn {days} ngày hiệu lực. Bạn có thể tạo đơn gia hạn trong cổng khách hàng.")
                result["reminders"] += 1
            db.commit()
    return result


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Recover accepted DEMO results and create in-app reminders; no payment network calls.")
    parser.add_argument("--once", action="store_true", required=True)
    parser.parse_args()
    from database import SessionLocal
    import models  # noqa: F401 — register all source and expansion mappings
    with SessionLocal() as session:
        print(json.dumps(run_portal_maintenance(session), ensure_ascii=False))
