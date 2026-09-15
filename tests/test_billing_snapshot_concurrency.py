"""An admission racing a tariff edit retains one complete committed price."""
from datetime import timedelta

from sqlalchemy import select

from crud.price_config import update_price_config
from models.parking_session import ParkingSession
from models.price_config import PriceConfig
from schemas.price_config import PriceConfigUpdate
from services.parking_service import ParkingService
from test_check_in_concurrency import env  # noqa: F401


def test_price_edit_and_admission_commit_a_coherent_snapshot(env):
    env.ensure_vehicle("SNAP-RACE-001")

    def worker(context, action):
        with context.Session() as db:
            if action == "price":
                price = db.scalar(select(PriceConfig))
                update_price_config(db, price, PriceConfigUpdate(price=45000, ticket_type="DAILY"))
                return ("price", 200)
            ParkingService(db).check_in("SNAP-RACE-001", context.vt_id, context.user_id, parking_slot_id=context.slot_a)
            return ("admitted", 201)

    admitted, updated = env.run_pair(worker, ("admit",), ("price",),
                                     sync_on=("UPDATE VEHICLE_TYPES", "UPDATE PRICE_CONFIGS"))
    assert admitted == ("admitted", 201) and updated == ("price", 200), (admitted, updated)
    with env.Session() as db:
        row = db.scalar(select(ParkingSession))
        assert (row.rate_unit_price, row.rate_ticket_type) in ((25000, "HOURLY"), (45000, "DAILY"))
        # The complete pair, not a mixed price/type read, is frozen forever.
        fee = ParkingService(db).calculate_fee(row.vehicle_id, env.vt_id, row.check_in_time,
                    row.check_in_time + timedelta(hours=25), billing_session=row)
        assert fee == (625000 if row.rate_ticket_type == "HOURLY" else 90000)
        assert row.billing_policy_version == "entry-v1"
    assert env.audit()["active_total"] == 1
