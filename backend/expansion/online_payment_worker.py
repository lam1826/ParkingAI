"""Explicit bounded payOS inbox recovery; no demo simulator or automatic refunds."""
import json
import logging
import time
from datetime import timedelta

from sqlalchemy import case, select

from core.clock import business_now
from expansion.online_payment_models import OnlinePaymentLink, OnlinePaymentProcessing
from expansion.online_payment_service import process_inbox, reconcile_link_for_worker

logger = logging.getLogger(__name__)

_UNRESOLVED_LINK_STATES = ("creating", "unknown", "ready")


def due_inbox_query(now, limit):
    # New evidence (NULL next_attempt_at) first on every database: PostgreSQL sorts
    # NULLs last by default, SQLite first.
    return select(OnlinePaymentProcessing.id).where(
        OnlinePaymentProcessing.status == "received",
        (OnlinePaymentProcessing.next_attempt_at.is_(None)) | (OnlinePaymentProcessing.next_attempt_at <= now),
    ).order_by(OnlinePaymentProcessing.next_attempt_at.asc().nulls_first(), OnlinePaymentProcessing.id).limit(limit)


def due_links_query(config, now, limit):
    # Unresolved links (create failed/crashed, waiting payer) and never-checked links
    # come first; terminal links are only re-polled for late money with what is left.
    # A link closed locally because payOS never created it (expired with no provider
    # id) has nothing to reconcile and is not polled again.
    return select(OnlinePaymentLink.id).where(
        OnlinePaymentLink.channel == config.channel, OnlinePaymentLink.site_id == config.PAYOS_SITE_ID,
        OnlinePaymentLink.state.in_(["creating", "unknown", "ready", "expired", "cancelled"]),
        ~((OnlinePaymentLink.state == "expired") & OnlinePaymentLink.payment_link_id.is_(None)),
        OnlinePaymentLink.expires_at >= now - timedelta(days=7),
        (OnlinePaymentLink.operation_until.is_(None)) | (OnlinePaymentLink.operation_until <= now),
        (OnlinePaymentLink.last_checked_at.is_(None)) | (OnlinePaymentLink.last_checked_at <= now - timedelta(seconds=30)),
    ).order_by(case((OnlinePaymentLink.state.in_(_UNRESOLVED_LINK_STATES), 0), else_=1),
        OnlinePaymentLink.last_checked_at.asc().nulls_first(), OnlinePaymentLink.id).limit(limit)


def _record_retry(db, identity):
    """Best effort: a database outage here must not end the cycle or the process."""
    try:
        row = db.get(OnlinePaymentProcessing, identity)
        if row is not None and row.status == "received":
            row.attempts += 1
            row.next_attempt_at = business_now() + timedelta(seconds=min(300, 2 ** min(row.attempts, 8)))
            row.reason = "fulfillment_retry"
            db.commit()
    except Exception:
        _safe_rollback(db)
        logger.warning("online_payment_retry_not_recorded inbox_id=%s", identity)


def _safe_rollback(db):
    try:
        db.rollback()
    except Exception:
        logger.warning("online_payment_rollback_failed")


def run_online_payment_maintenance(db, config, gateway, *, limit=50):
    if not config.PAYOS_ENABLED:
        return {"disabled": True, "handled": 0, "retry": 0, "reconciled": 0}
    limit = max(1, min(int(limit), 100))
    now = business_now()
    identities = list(db.scalars(due_inbox_query(now, limit)))
    db.commit()
    result = {"disabled": False, "handled": 0, "retry": 0, "reconciled": 0}
    for identity in identities:
        try:
            process_inbox(db, identity, config, gateway)
            result["handled"] += 1
        except Exception:
            _safe_rollback(db)
            # No exception prose/SQL parameters/provider content in logs.
            logger.warning("online_payment_retry inbox_id=%s", identity)
            _record_retry(db, identity)
            result["retry"] += 1
    # Lost webhook/create response recovery never depends on a customer refresh.
    # The finite seven-day reconciliation window bounds provider traffic; signed
    # late webhooks remain accepted afterward and become review evidence.
    links = list(db.scalars(due_links_query(config, now, limit)))
    db.commit()
    for link_id in links:
        try:
            reconcile_link_for_worker(db, link_id, config, gateway)
            db.commit()
            result["reconciled"] += 1
        except Exception:
            _safe_rollback(db)
            logger.warning("online_payment_reconcile_retry link_id=%s", link_id)
            result["retry"] += 1
    return result


def run_worker_loop(session_factory, config, gateway, *, limit=50, poll_seconds=30, once=False,
        sleep=time.sleep, emit=None, max_cycles=None):
    """Run cycles until stopped. A failed cycle (for example the database is briefly
    unreachable) is logged and retried on the next poll instead of ending the process.
    Each cycle uses a fresh session so a broken connection is never reused.

    Returns True when the last cycle failed, so a one-shot (--once) caller can exit
    non-zero; the --run loop itself keeps going."""
    emit = emit or (lambda line: print(line, flush=True))
    cycles = 0
    while True:
        cycles += 1
        session = None
        failed = False
        try:
            session = session_factory()
            emit(json.dumps(run_online_payment_maintenance(session, config, gateway, limit=limit)))
        except Exception:
            failed = True
            if session is not None:
                _safe_rollback(session)
            # Stable marker only; exception text may contain SQL parameters.
            logger.warning("online_payment_cycle_failed")
            emit(json.dumps({"disabled": False, "error": "cycle_failed"}))
        finally:
            try:
                if session is not None:
                    session.close()
            except Exception:
                logger.warning("online_payment_session_close_failed")
        if once or (max_cycles is not None and cycles >= max_cycles):
            return failed
        sleep(max(10, min(poll_seconds, 300)))


def main(argv=None):
    """CLI entry point. Exit status: 0 = success or disabled; 1 = the --once cycle failed.
    The --run loop logs failed cycles and keeps running."""
    import argparse
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
    arguments = parser.parse_args(argv)
    settings = get_online_payment_config()
    if not settings.PAYOS_ENABLED:
        print(json.dumps({"disabled": True, "handled": 0, "retry": 0, "reconciled": 0}))
        return 0
    with httpx.Client(trust_env=False, follow_redirects=False) as transport:
        adapter = PayOSGateway(settings.adapter_settings(), transport)
        last_cycle_failed = run_worker_loop(SessionLocal, settings, adapter, limit=arguments.limit,
            poll_seconds=arguments.poll_seconds, once=arguments.once)
    # A failed one-shot cycle must be visible to the operator/script by exit status.
    return 1 if arguments.once and last_cycle_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
