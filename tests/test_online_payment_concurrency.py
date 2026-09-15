"""Independent file-backed connections exercise real money idempotency races."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from expansion import online_payment_service as service
from expansion.online_payment_models import OnlinePaymentInbox, OnlinePaymentLink
from expansion.payos_gateway import PayOSGateway
from models.monthly_pass import MonthlyPass
from models.payment import Payment
from models.user import User

from test_online_payments import online, no_external_payment_configuration, order_and_link, webhook_bytes, accept  # noqa: F401
from test_portal_api import portal  # noqa: F401
from test_payos_gateway import signed, created_data, link_data, transaction


def clone(ctx, tmp_path):
    ctx.db.commit()
    engine = create_engine("sqlite:///" + (tmp_path / "online-concurrency.sqlite").as_posix(),
        connect_args={"timeout": 15, "check_same_thread": False})
    source, target = ctx.db.get_bind().raw_connection(), engine.raw_connection()
    try:
        source.driver_connection.backup(target.driver_connection)
    finally:
        source.close()
        target.close()
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_concurrent_duplicate_webhooks_ack_same_durable_inbox(online, tmp_path):
    order_and_link(online)
    raw = webhook_bytes(online)
    engine, factory = clone(online, tmp_path)
    barrier = Barrier(2)

    def receive():
        with factory() as db:
            barrier.wait(timeout=10)
            return service.accept_webhook(db, raw, online.config, online.gateway)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(receive) for _ in range(2)]
            result = [future.result(timeout=25) for future in futures]
        assert result[0] == result[1]
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(OnlinePaymentInbox)) == 1
            assert db.scalar(select(func.count()).select_from(Payment)) == 0
    finally:
        engine.dispose()


def test_concurrent_workers_allocate_one_receipt_and_entitlement(online, tmp_path):
    order_and_link(online)
    identity = accept(online).id
    engine, factory = clone(online, tmp_path)
    barrier = Barrier(2)

    def process():
        with factory() as db:
            def get_provider(request):
                assert request.method == "GET" and not db.in_transaction()
                barrier.wait(timeout=10)
                return httpx.Response(200, json=signed(link_data(orderCode=online.state["code"],
                    amount=300000, amountPaid=300000, transactions=[transaction(amount=300000,
                        reference=online.state["reference"])])))
            with httpx.Client(transport=httpx.MockTransport(get_provider), trust_env=False) as client:
                gateway = PayOSGateway(online.config.adapter_settings(), client)
                service.process_inbox(db, identity, online.config, gateway)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(process) for _ in range(2)]
            [future.result(timeout=25) for future in futures]
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(Payment)) == 1
            assert db.scalar(select(func.count()).select_from(MonthlyPass)) == 1
            assert db.scalar(select(OnlinePaymentLink)).state == "paid"
    finally:
        engine.dispose()


def test_concurrent_create_while_provider_waits_reuses_committed_identity(online, tmp_path):
    response = online.client.post("/api/v2/me/orders", json={**online.body, "payment_mode": "payos"})
    assert response.status_code == 200, response.text
    identity, actor_id = response.json()["id"], online.users[1].id
    engine, factory = clone(online, tmp_path)
    started, release = Event(), Event()
    posts = []

    def create():
        with factory() as db:
            def provider(request):
                import json
                assert not db.in_transaction()
                body = json.loads(request.content)
                posts.append(body["orderCode"])
                started.set()
                assert release.wait(timeout=10)
                return httpx.Response(200, json=signed(created_data(orderCode=body["orderCode"],
                    amount=body["amount"], description=body["description"], expiredAt=body["expiredAt"])))
            with httpx.Client(transport=httpx.MockTransport(provider), trust_env=False) as client:
                return service.create_payment_link(db, db.get(User, actor_id), identity, online.config,
                    PayOSGateway(online.config.adapter_settings(), client)).state

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(create)
            assert started.wait(timeout=10)
            second = pool.submit(create)
            assert second.result(timeout=10) == "creating"
            release.set()
            assert first.result(timeout=10) == "ready"
        assert len(posts) == 1
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(OnlinePaymentLink)) == 1
    finally:
        release.set()
        engine.dispose()
