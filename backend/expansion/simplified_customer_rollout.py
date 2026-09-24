"""Add fields/tables on a disposable SQLite rollout candidate, preserving old rows."""
from sqlalchemy import inspect


def migrate_simplified_customer(target_engine):
    if target_engine.dialect.name != 'sqlite':
        return
    from expansion.simplified_customer_models import DeclaredParkingReservation, SessionPaymentAccess, SessionTicketCredential
    from expansion.vision_passage_models import CameraAutomationPolicy, VisionPassageEvent
    from expansion.simplified_customer_guards import SIMPLIFIED_SQLITE_GUARDS
    from models.vehicle_type import VehicleType
    with target_engine.begin() as conn:
        names = set(inspect(conn).get_table_names())
        if 'vision_observations' in names:
            fields = {row[1] for row in conn.exec_driver_sql('PRAGMA table_info(vision_observations)')}
            if 'capture_source' not in fields:
                conn.exec_driver_sql("ALTER TABLE vision_observations ADD COLUMN capture_source VARCHAR(16) NOT NULL DEFAULT 'manual_upload'")
        if 'vehicle_types' in names:
            columns = {row[1] for row in conn.exec_driver_sql('PRAGMA table_info(vehicle_types)')}
            if 'requires_plate' not in columns:
                conn.exec_driver_sql('ALTER TABLE vehicle_types ADD COLUMN requires_plate BOOLEAN NOT NULL DEFAULT true')
            if 'code_prefix' not in columns:
                conn.exec_driver_sql('ALTER TABLE vehicle_types ADD COLUMN code_prefix VARCHAR(8)')
            for index in VehicleType.__table__.indexes:
                if index.name == 'uq_vehicle_types_code_prefix':
                    index.create(bind=conn, checkfirst=True)
        parents = {'parking_sessions','parking_sites','parking_slots','users','vehicle_types','vehicles','zones'}
        if parents <= names:
            for model in (SessionTicketCredential, SessionPaymentAccess, DeclaredParkingReservation):
                model.__table__.create(bind=conn, checkfirst=True)
            if {'vision_cameras','vision_observations'} <= names:
                for model in (CameraAutomationPolicy, VisionPassageEvent):
                    model.__table__.create(bind=conn, checkfirst=True)
            if {'parking_reservations','guaranteed_allocations','parking_capacity_holds','roles'} <= names:
                for statement in SIMPLIFIED_SQLITE_GUARDS.values():
                    conn.exec_driver_sql(statement)
