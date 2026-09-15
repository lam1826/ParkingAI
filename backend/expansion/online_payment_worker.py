"""Explicit bounded payOS inbox recovery; no demo simulator or automatic refunds."""
import logging
from datetime import timedelta

from sqlalchemy import select

from core.clock import business_now
from expansion.online_payment_models import OnlinePaymentLink, OnlinePaymentProcessing
from expansion.online_payment_service import process_inbox, reconcile_link_for_worker

logger = logging.getLogger(__name__)


def run_online_payment_maintenance(db, config, gateway, *, limit=50):
    if not config.PAYOS_ENABLED:
        return {"disabled": True, "handled": 0, "retry": 0, "reconciled": 0}
    limit = max(1, min(int(limit), 100))
    now = business_now()
    identities = list(db.scalars(select(OnlinePaymentProcessing.id).where(
        OnlinePaymentProcessing.status == "received",
        (OnlinePaymentProcessing.next_attempt_at.is_(None)) | (OnlinePaymentProcessing.next_attempt_at <= now),
    ).order_by(OnlinePaymentProcessing.next_attempt_at, OnlinePaymentProcessing.id).limit(limit)))
    db.commit()
    result = {"disabled": False, "handled": 0, "retry": 0, "reconciled": 0}
    for identity in identities:
        try:
            process_inbox(db, identity, config, gateway)
            result["handled"] += 1
        except Exception:
            db.rollback()
            # No exception prose/SQL parameters/provider content in logs.
            logger.warning("online_payment_retry inbox_id=%s", identity)
            row = db.get(OnlinePaymentProcessing, identity)
            if row is not None and row.status == "received":
                row.attempts += 1
                row.next_attempt_at = business_now() + timedelta(seconds=min(300, 2 ** min(row.attempts, 8)))
                row.reason = "fulfillment_retry"
                db.commit()
            result["retry"] += 1
    # Lost webhook/create response recovery never depends on a customer refresh.
    # The finite seven-day reconciliation window bounds provider traffic; signed
    # late webhooks remain accepted afterward and become review evidence.
    links = list(db.scalars(select(OnlinePaymentLink.id).where(
        OnlinePaymentLink.channel == config.channel, OnlinePaymentLink.site_id == config.PAYOS_SITE_ID,
        OnlinePaymentLink.state.in_(["creating", "unknown", "ready", "expired", "cancelled"]),
        OnlinePaymentLink.expires_at >= now - timedelta(days=7),
        (OnlinePaymentLink.operation_until.is_(None)) | (OnlinePaymentLink.operation_until <= now),
        (OnlinePaymentLink.last_checked_at.is_(None)) | (OnlinePaymentLink.last_checked_at <= now - timedelta(seconds=30)),
    ).order_by(OnlinePaymentLink.last_checked_at, OnlinePaymentLink.id).limit(limit)))
    db.commit()
    for link_id in links:
        try:
            reconcile_link_for_worker(db, link_id, config, gateway)
            db.commit()
            result["reconciled"] += 1
        except Exception:
            db.rollback()
            logger.warning("online_payment_reconcile_retry link_id=%s", link_id)
            result["retry"] += 1
    return result


if __name__ == "__main__":
    import argparse
    import json
    import httpx
    from database import SessionLocal
    import models  # noqa: F401
    from expansion.online_payment_schemas import get_online_payment_config
    from expansion.payos_gateway import PayOSGateway

    parser = argparse.ArgumentParser(description="Process already accepted payOS evidence; default disabled.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--run", action="store_true", help="Run the explicitly configured one-lot payment worker")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--limit", type=int, default=50)
    arguments = parser.parse_args()
    settings = get_online_payment_config()
    if not settings.PAYOS_ENABLED:
        print(json.dumps({"disabled": True, "handled": 0, "retry": 0, "reconciled": 0}))
        raise SystemExit(0)
    import time
    with httpx.Client(trust_env=False, follow_redirects=False) as transport, SessionLocal() as session:
        adapter = PayOSGateway(settings.adapter_settings(), transport)
        while True:
            print(json.dumps(run_online_payment_maintenance(session, settings, adapter, limit=arguments.limit)), flush=True)
            if arguments.once:
                break
            time.sleep(max(10, min(arguments.poll_seconds, 300)))
