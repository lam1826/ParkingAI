from datetime import timedelta
from threading import Event

from fastapi.testclient import TestClient
from sqlalchemy import select

import main
from core.clock import business_now
from expansion.portal_models import PortalAccountLink, PortalNotification
from expansion.portal_worker import run_portal_maintenance
from models.monthly_pass import MonthlyPass
from models.vehicle import Vehicle


def test_production_lifespan_runs_portal_maintenance_when_enabled(monkeypatch):
    ran = Event()
    monkeypatch.setattr(main.settings, "PORTAL_MAINTENANCE_INTERVAL_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(main, "_run_maintenance_cycle", ran.set, raising=False)

    with TestClient(main.app):
        assert ran.wait(timeout=1)


def test_bounded_reminder_batches_progress_past_already_notified_passes(db_session, test_user, customer, vehicle_type):
    db = db_session
    db.add(PortalAccountLink(user_id=test_user.id, customer_id=customer.id, verification="test"))
    today = business_now().date()
    for index in range(10):
        vehicle = Vehicle(license_plate=f"WORKER-{index:03}", vehicle_type_id=vehicle_type.id, customer_id=customer.id)
        db.add(vehicle); db.flush()
        db.add(MonthlyPass(customer_id=customer.id, vehicle_id=vehicle.id, price=0,
            start_date=today - timedelta(days=20), end_date=today + timedelta(days=7 if index % 2 else 1), is_active=True))
    db.commit()
    assert [run_portal_maintenance(db, limit=3)["reminders"] for _ in range(5)] == [3, 3, 3, 1, 0]
    notifications = list(db.scalars(select(PortalNotification)))
    assert len(notifications) == 10
    assert len({row.event_key for row in notifications}) == 10
