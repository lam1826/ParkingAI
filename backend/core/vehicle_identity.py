"""Server-generated identifiers for unplated types; no invented registration plate."""
import re
import secrets

from fastapi import HTTPException
from sqlalchemy import func, select, text, update


def canonical_identity(value):
    return re.sub(r'[ .\-]', '', str(value or '').upper().strip())


def identity_expression(column):
    return func.replace(func.replace(func.replace(func.upper(column), '-', ''), '.', ''), ' ', '')


def lock_identity(db, vehicle_type_id, plate):
    """Acquire before vehicle rows: serialize formatting variants on admission.

    SQLite has one writer. PostgreSQL uses a transaction-local lock independent
    of type so conflicting declarations cannot race with a differently typed
    admission. No historical plate or uniqueness index is rewritten.
    """
    if db.get_bind().dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:plate, 0))'),
            {'plate': canonical_identity(plate)})
    elif db.get_bind().dialect.name == 'sqlite':
        from models.vehicle_type import VehicleType
        db.execute(update(VehicleType).where(VehicleType.id == vehicle_type_id)
            .values(id=VehicleType.id, updated_at=VehicleType.updated_at))


def resolve_vehicle(db, plate):
    from models.vehicle import Vehicle
    rows = db.scalars(select(Vehicle).where(identity_expression(Vehicle.license_plate) == canonical_identity(plate))
        .order_by(Vehicle.id).limit(2).with_for_update(key_share=True).execution_options(populate_existing=True)).all()
    if len(rows) > 1:
        raise HTTPException(409, 'Biển số/mã xe khớp nhiều hồ sơ cũ; cần quản lý kiểm tra, hệ thống không tự sửa lịch sử.')
    return rows[0] if rows else None


def admission_identity(vehicle_type, supplied):
    value = str(supplied or '').strip().upper()
    if not value:
        if vehicle_type.requires_plate:
            raise HTTPException(422, 'Loại xe này cần biển số khi vào bãi.')
        prefix = vehicle_type.code_prefix or 'XE'
        return f'{prefix}-{secrets.token_hex(5).upper()}'
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9. -]{2,19}', value):
        raise HTTPException(422, 'Biển số hoặc mã xe không hợp lệ.')
    return value
