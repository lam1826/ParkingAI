"""Independent SQLite connections contend before their first business write."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from test_timed_parking import timed
from test_portal_api import portal
from expansion.portal_schemas import OrderCreate, Simulation
from expansion.portal_service import create_order, simulate, cancel_order
from expansion.portal_models import PortalOrder
from expansion.timed_parking_models import ParkingCapacityHold, TimedParkingPass
from models.payment import Payment
from models.parking_session import ParkingSession
from models.user import User
from services.parking_service import ParkingService


def cloned(source_db, path):
    source_db.commit()
    engine = create_engine("sqlite:///"+path.as_posix(), connect_args={"timeout":15,"check_same_thread":False})
    source, target = source_db.get_bind().raw_connection(), engine.raw_connection()
    try:
        source.driver_connection.backup(target.driver_connection)
    finally:
        source.close(); target.close()
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def race(factory, *operations):
    ready = Barrier(len(operations))
    def run(operation):
        with factory() as db:
            # Establish a read transaction before the write race, like HTTP auth.
            db.scalar(select(func.count()).select_from(User))
            ready.wait(timeout=10)
            try:
                value = operation(db)
                db.commit()
                return "ok", value
            except HTTPException as exc:
                db.rollback()
                return "http", exc.status_code
    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(run, op) for op in operations]
        return [future.result(timeout=25) for future in futures]


def test_live_hold_and_walkin_compete_for_last_slot(timed, tmp_path):
    portal, body, slot, rate = timed
    client, current, users, site, kind, source_db = portal
    owner_id, operator_id, slot_id, kind_id = users[1].id, users[0].id, slot.id, kind.id
    engine, factory = cloned(source_db,tmp_path/"hold-walkin.db")
    try:
        results = race(factory,
            lambda db:create_order(db,db.get(User,owner_id),OrderCreate(**body)).id,
            lambda db:ParkingService(db).check_in("30A-88888",kind_id,operator_id,parking_slot_id=slot_id)["session_id"])
        assert [item[0] for item in results].count("ok") == 1
        assert ("http",409) in results
        with factory() as db:
            held=db.scalar(select(func.count()).select_from(ParkingCapacityHold).where(ParkingCapacityHold.status=="held"))
            parked=db.scalar(select(func.count()).select_from(ParkingSession).where(ParkingSession.status=="active"))
            assert held+parked==1
    finally:
        engine.dispose()


def test_two_payment_confirmations_create_one_prepaid_right(timed,tmp_path):
    portal,body,slot,rate=timed
    client,current,users,site,kind,source_db=portal
    order=client.post("/api/v2/me/orders",json=body).json()
    owner=users[1].id
    engine,factory=cloned(source_db,tmp_path/"paid-replay.db")
    def confirm(db):
        item=simulate(db,db.get(User,owner),order["id"],Simulation(token=order["demo_token"],outcome="success"))
        return item.timed_pass_id,item.receipt_id
    try:
        results=race(factory,confirm,confirm)
        assert results[0]==results[1] and results[0][0]=="ok"
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(TimedParkingPass))==1
            assert db.scalar(select(func.count()).select_from(Payment).where(Payment.source_type=="portal_order"))==1
    finally:
        engine.dispose()


def test_cancellation_and_payment_do_not_split_capacity_from_right(timed,tmp_path):
    portal,body,slot,rate=timed
    client,current,users,site,kind,source_db=portal
    order=client.post("/api/v2/me/orders",json=body).json()
    owner=users[1].id
    engine,factory=cloned(source_db,tmp_path/"cancel-paid.db")
    try:
        race(factory,
            lambda db:simulate(db,db.get(User,owner),order["id"],Simulation(token=order["demo_token"],outcome="success")).status,
            lambda db:cancel_order(db,db.get(User,owner),order["id"]).status)
        with factory() as db:
            row=db.get(PortalOrder,order["id"])
            hold=db.scalar(select(ParkingCapacityHold))
            count=db.scalar(select(func.count()).select_from(TimedParkingPass))
            assert (row.status,hold.status,count) in {("fulfilled","converted",1),("cancelled","released",0)}
    finally:
        engine.dispose()
