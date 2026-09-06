"""Real separate SQLite connections exercise cash collection/close races."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from database import Base
from models.cash_shift import CashShift
from models.payment import Payment
from models.role import Role
from models.user import User
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType
from datetime import date
from services.cash_shift_service import CashShiftService
from services.payment_service import PaymentService


@pytest.fixture
def finance_store(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'finance-race.db').as_posix()}", connect_args={"check_same_thread": False, "timeout": 20})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        role = Role(name="manager")
        db.add(role)
        db.flush()
        db.add_all([User(id=index, role_id=role.id, username=f"cashier-{index}", full_name=f"Cashier {index}", password_hash="unused", is_active=True) for index in (1, 2)])
        customer = Customer(full_name="Fixture", phone_number="0901112222")
        vehicle_type = VehicleType(name="Fixture car")
        db.add_all([customer, vehicle_type])
        db.flush()
        vehicle = Vehicle(license_plate="51A-100.01", vehicle_type_id=vehicle_type.id)
        db.add(vehicle)
        db.flush()
        db.add(MonthlyPass(id=1, customer_id=customer.id, vehicle_id=vehicle.id, price=500_000,
                           pass_code="CONCURRENCY-001", start_date=date(2026, 1, 1), end_date=date(2026, 1, 31), is_active=False))
        db.commit()
    yield engine, factory
    engine.dispose()


def race_operator_locks(engine, functions):
    """Hold both workers just before their first cash serialization write."""
    barrier = threading.Barrier(len(functions), timeout=10)
    visited = threading.local()

    def before_execute(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE users SET id = id") and not getattr(visited, "waited", False):
            visited.waited = True
            barrier.wait()

    event.listen(engine, "before_cursor_execute", before_execute)
    try:
        with ThreadPoolExecutor(max_workers=len(functions)) as workers:
            futures = [workers.submit(function) for function in functions]
            return [future.result(timeout=25) for future in futures]
    finally:
        event.remove(engine, "before_cursor_execute", before_execute)


def test_parallel_retry_creates_exactly_one_receipt(finance_store):
    engine, factory = finance_store

    def collect():
        with factory() as db:
            payment = PaymentService.record_receipt(db, "monthly_pass", 1, 500_000, 1)
            db.commit()
            return payment.id

    ids = race_operator_locks(engine, [collect, collect])
    assert ids[0] == ids[1]
    with factory() as db:
        assert len(db.scalars(select(Payment)).all()) == 1


def test_two_managers_cannot_refund_more_than_original(finance_store):
    engine, factory = finance_store
    with factory() as db:
        original = PaymentService.record_receipt(db, "monthly_pass", 1, 500_000, 1)
        db.commit()
        original_id = original.id

    def refund(staff_id):
        with factory() as db:
            actor = db.get(User, staff_id)
            try:
                PaymentService.refund(db, original_id, actor, amount=300_000, method="cash", reason="Hủy kỳ", idempotency_key=f"parallel-refund-{staff_id}")
                db.commit()
                return 200
            except HTTPException as error:
                db.rollback()
                return error.status_code

    results = race_operator_locks(engine, [lambda: refund(1), lambda: refund(2)])
    assert sorted(results) == [200, 409]
    with factory() as db:
        amounts = db.scalars(select(Payment.amount).where(Payment.kind == "refund")).all()
        assert amounts == [300_000]


def test_payment_racing_close_is_either_in_frozen_total_or_outside(finance_store):
    engine, factory = finance_store
    with factory() as db:
        db.get(MonthlyPass, 1).price = 100_000
        shift = CashShiftService.open_shift(db, db.get(User, 1))
        db.commit()
        shift_id = shift.id

    def collect():
        with factory() as db:
            payment = PaymentService.record_receipt(db, "monthly_pass", 1, 100_000, 1)
            db.commit()
            return payment.id

    def close():
        with factory() as db:
            CashShiftService.close_shift(db, shift_id, db.get(User, 1), counted_cash=100_000)
            db.commit()
            return shift_id

    payment_id, _ = race_operator_locks(engine, [collect, close])
    with factory() as db:
        payment = db.get(Payment, payment_id)
        shift = db.get(CashShift, shift_id)
        assert shift.status == "closed"
        assert shift.expected_cash == (100_000 if payment.shift_id == shift_id else 0)
        assert shift.difference == 100_000 - shift.expected_cash
