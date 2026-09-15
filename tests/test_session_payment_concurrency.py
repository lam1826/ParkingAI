"""Separate SQLite connections exercise credit, checkout and authority races."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select, update

from expansion import online_payment_service as service
from expansion.online_payment_models import OnlinePaymentLink, OnlinePaymentProcessing
from expansion.payos_gateway import PayOSGateway
from expansion.portal_models import PortalAccountLink, PortalSessionGrant
from expansion.session_payment_models import SessionFeeCredit, SessionFeeQuote
from expansion.session_payment_schemas import SessionFeeQuoteCreate
from expansion.session_payment_service import create_quote
from expansion.site_models import ParkingSite, SiteMembership
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.payment import Payment
from models.role import Role
from models.user import User
from schemas.checkout import CheckoutConfirmation
from services.checkout_service import CheckoutService

from test_online_payment_concurrency import clone
from test_online_payments import online, no_external_payment_configuration  # noqa: F401
from test_portal_api import portal  # noqa: F401
from test_session_online_payments import parking_online, quote, link, receive  # noqa: F401
from test_payos_gateway import created_data, link_data, signed, transaction


def paid_response(ctx, code):
    saved = ctx.provider["links"][code]
    return httpx.Response(200, json=signed(link_data(id=saved["id"], orderCode=code,
        amount=saved["amount"], amountPaid=saved["amount"], amountRemaining=0, status="PAID",
        transactions=[transaction(amount=saved["amount"], reference=saved["reference"])])))


def test_two_workers_credit_one_session_once(parking_online, tmp_path):
    ctx = parking_online
    code = link(ctx, quote(ctx))
    identity = receive(ctx, code)
    engine, factory = clone(ctx, tmp_path)
    together = Barrier(2)

    def process():
        with factory() as db:
            def provider(request):
                assert request.method == "GET" and not db.in_transaction()
                together.wait(timeout=10)
                return paid_response(ctx, code)
            with httpx.Client(transport=httpx.MockTransport(provider), trust_env=False) as transport:
                service.process_inbox(db, identity, ctx.config, PayOSGateway(ctx.config.adapter_settings(), transport))

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(process) for _ in range(2)]
            for future in futures:
                future.result(timeout=25)
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(SessionFeeCredit)) == 1
            assert list(db.scalars(select(Payment.amount))) == [10000]
            assert db.get(ParkingSession, ctx.session_id).status == "active"
            assert db.get(ParkingSlot, ctx.slot.id).is_occupied
            assert db.get(OnlinePaymentProcessing, identity).status == "processed"
    finally:
        engine.dispose()


def test_cash_departure_during_provider_get_keeps_incoming_money_for_review(parking_online, tmp_path):
    ctx = parking_online
    code = link(ctx, quote(ctx))
    identity = receive(ctx, code)
    engine, factory = clone(ctx, tmp_path)
    started, release = Event(), Event()

    def process():
        with factory() as db:
            def provider(request):
                assert request.method == "GET" and not db.in_transaction()
                started.set()
                assert release.wait(timeout=10)
                return paid_response(ctx, code)
            with httpx.Client(transport=httpx.MockTransport(provider), trust_env=False) as transport:
                service.process_inbox(db, identity, ctx.config, PayOSGateway(ctx.config.adapter_settings(), transport))

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(process)
            assert started.wait(timeout=10)
            with factory() as cashier:
                proposal = CheckoutService(cashier).quote(ctx.session_id, ctx.users[0].id)
                CheckoutService(cashier).confirm(CheckoutConfirmation(quote_token=proposal["quote_token"],
                    payment_confirmed=True, payment_method="cash"), ctx.users[0].id, session_id=ctx.session_id)
            release.set()
            future.result(timeout=15)
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(SessionFeeCredit)) == 0
            assert list(db.scalars(select(Payment.amount))) == [10000]
            assert db.get(ParkingSession, ctx.session_id).status == "completed"
            assert not db.get(ParkingSlot, ctx.slot.id).is_occupied
            assert db.get(OnlinePaymentProcessing, identity).reason == "session_no_longer_active"
    finally:
        release.set()
        engine.dispose()


def test_concurrent_distinct_requests_create_only_one_pending_quote(parking_online, tmp_path):
    ctx = parking_online
    actor_id = ctx.users[1].id
    engine, factory = clone(ctx, tmp_path)
    together = Barrier(2)

    def create(request_id):
        with factory() as db:
            actor = db.get(User, actor_id)
            together.wait(timeout=10)
            try:
                return create_quote(db, actor, ctx.session_id,
                    SessionFeeQuoteCreate(request_id=request_id), ctx.config).id
            except HTTPException as error:
                db.rollback()
                return error.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(create, "concurrent-quote-" + str(i)) for i in range(2)]
            results = [future.result(timeout=25) for future in futures]
        assert sum(isinstance(value, str) for value in results) == 1 and 409 in results
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(SessionFeeQuote)) == 1
            assert db.scalar(select(func.count()).select_from(OnlinePaymentLink)) == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize("change", ["account", "grant", "inactive", "staff_membership", "staff_role", "staff_site"])
def test_authority_removed_on_another_connection_during_create_never_exposes_qr(parking_online, tmp_path, change):
    ctx = parking_online
    proposal = quote(ctx)
    actor_id = ctx.users[1].id
    if change.startswith("staff_"):
        role = Role(name="staff")
        ctx.db.add(role)
        ctx.db.flush()
        actor = User(username="fee-race-staff", full_name="Fee race staff", password_hash="unused", role_id=role.id, is_active=True)
        ctx.db.add(actor)
        ctx.db.flush()
        actor_id = actor.id
        ctx.db.add(SiteMembership(site_id=ctx.site.id, user_id=actor.id, role="staff"))
        ctx.db.commit()
    engine, factory = clone(ctx, tmp_path)

    try:
        with factory() as db:
            def provider(request):
                assert request.method == "POST" and not db.in_transaction()
                body = json.loads(request.content)
                with factory() as revoker:
                    if change == "account":
                        revoker.execute(delete(PortalAccountLink).where(PortalAccountLink.user_id == actor_id))
                    elif change == "grant":
                        revoker.execute(delete(PortalSessionGrant).where(PortalSessionGrant.parking_session_id == ctx.session_id))
                    elif change == "inactive":
                        revoker.execute(update(User).where(User.id == actor_id).values(is_active=False))
                    elif change == "staff_membership":
                        revoker.execute(delete(SiteMembership).where(SiteMembership.user_id == actor_id))
                    elif change == "staff_role":
                        revoker.execute(update(User).where(User.id == actor_id).values(role_id=ctx.users[1].role_id))
                    else:
                        revoker.execute(update(ParkingSite).where(ParkingSite.id == ctx.site.id).values(is_active=False))
                    revoker.commit()
                return httpx.Response(200, json=signed(created_data(orderCode=body["orderCode"],
                    amount=body["amount"], description=body["description"], expiredAt=body["expiredAt"])))
            with httpx.Client(transport=httpx.MockTransport(provider), trust_env=False) as transport:
                with pytest.raises(HTTPException) as failure:
                    service.create_session_payment_link(db, db.get(User, actor_id), proposal["id"],
                        ctx.config, PayOSGateway(ctx.config.adapter_settings(), transport))
                assert failure.value.status_code in {403, 404}
            db.rollback()
        with factory() as check:
            assert check.scalar(select(func.count()).select_from(OnlinePaymentLink)) == 1
            assert check.scalar(select(OnlinePaymentLink)).state == "ready"
            assert check.scalar(select(func.count()).select_from(Payment)) == 0
    finally:
        engine.dispose()
