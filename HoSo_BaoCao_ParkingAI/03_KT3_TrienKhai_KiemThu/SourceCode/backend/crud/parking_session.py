from sqlalchemy.orm import Session
from sqlalchemy import select, and_, update
from sqlalchemy.exc import DBAPIError
from datetime import datetime
from core.clock import business_now
from crud import price_config as crud_price_config
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.monthly_pass import MonthlyPass
from models.zone import Zone
from schemas import parking_session as session_schema


class MissingEffectiveCheckInPriceError(Exception):
    """A vehicle has no active fallback rate effective at check-in."""


def server_now() -> datetime:
    """Đồng hồ server dùng chung cho check-in VÀ check-out — điểm lấy
    thời gian DUY NHẤT của mỗi giao dịch.

    Trả về giờ nghiệp vụ Asia/Ho_Chi_Minh dạng naive (Đợt 10A — độc lập với
    timezone hệ điều hành host, xem backend/core/clock.py). Tách thành hàm
    để test freeze được thời gian bằng monkeypatch mà không sửa đồng hồ hệ
    thống; service/router phải gọi qua module (crud_session.server_now())
    để monkeypatch có hiệu lực."""
    return business_now()


def claim_session_for_checkout(db: Session, session_id: str) -> bool:
    """Claim active -> checking_out NGUYÊN TỬ bằng conditional UPDATE.

    Chỉ transaction đầu tiên thắng (rowcount == 1); request thua nhận False
    và KHÔNG được tính phí hay ghi đè dữ liệu. Không commit tại đây — claim,
    tính phí, cập nhật session và giải phóng slot phải cùng một transaction
    để cùng commit hoặc cùng rollback (rollback trả session về active)."""
    result = db.execute(
        update(ParkingSession)
        .where(
            ParkingSession.id == session_id,
            ParkingSession.status == "active",
        )
        .values(status="checking_out")
    )
    return result.rowcount == 1


def claim_parking_slot(
    db: Session,
    slot_id: int,
    *,
    expected_zone_id: int | None = None,
    expected_vehicle_type_id: int | None = None,
) -> bool:
    """Chiếm vị trí đỗ NGUYÊN TỬ bằng conditional UPDATE.

    Chỉ thành công khi slot vẫn đang active và chưa occupied tại thời điểm
    UPDATE thực thi (SQLite tuần tự hóa các write). rowcount == 0 nghĩa là
    một request khác vừa chiếm slot hoặc slot vừa bị tắt — caller phải trả
    409/404 thay vì ghi đè. KHÔNG commit tại đây: claim phải nằm cùng
    transaction với INSERT session để cùng commit hoặc cùng rollback.
    """
    conditions = [
            ParkingSlot.id == slot_id,
            ParkingSlot.is_occupied == False,  # noqa: E712
            ParkingSlot.is_active == True,  # noqa: E712
            ParkingSlot.zone_id.in_(
                select(Zone.id).where(Zone.is_active == True)  # noqa: E712
            ),
    ]
    # Snapshot assignment đã validate trước claim. Nếu admin chuyển
    # khu/đổi loại xe và commit trước conditional UPDATE này, rowcount
    # phải bằng 0 thay vì request cũ chiếm slot theo assignment đã stale.
    if expected_zone_id is not None:
        conditions.append(ParkingSlot.zone_id == expected_zone_id)
    if expected_vehicle_type_id is not None:
        conditions.append(
            ParkingSlot.vehicle_type_id == expected_vehicle_type_id
        )

    result = db.execute(
        update(ParkingSlot)
        .where(*conditions)
        .values(is_occupied=True)
    )
    return result.rowcount == 1


def map_check_in_integrity_error(exc: DBAPIError) -> str | None:
    """Dịch đúng các DB backstop check-in đã biết thành thông báo 409.

    Mọi IntegrityError khác trả None để caller xử lý như lỗi hệ thống thay vì
    che mù quáng thành 409.
    """
    message = str(exc.orig) if exc.orig is not None else str(exc)
    # SQLite báo vi phạm partial unique index bằng TÊN CỘT (đã xác minh:
    # "UNIQUE constraint failed: parking_sessions.vehicle_id"), không phải tên
    # index. Hai cột này chỉ có đúng hai unique index của bất biến check-in
    # nên mapping không nhầm với ràng buộc khác.
    if (
        "parking_sessions.vehicle_id" in message
        or "uq_parking_session_one_active_per_vehicle" in message
    ):
        return "Xe vừa được check-in ở một phiên khác. Vui lòng kiểm tra lại."
    if (
        "parking_sessions.parking_slot_id" in message
        or "uq_parking_session_one_active_per_slot" in message
    ):
        return "Vị trí đỗ vừa được xe khác sử dụng. Vui lòng chọn vị trí khác."
    if "active parking session requires effective price config" in message:
        return (
            "Bảng giá áp dụng vừa thay đổi hoặc không còn hiệu lực. "
            "Vui lòng kiểm tra bảng giá rồi thử nhận xe lại."
        )
    if "monthly pass is not eligible at check-in" in message:
        return (
            "Vé tháng vừa thay đổi và không còn hợp lệ tại thời điểm nhận xe. "
            "Vui lòng kiểm tra vé rồi thử lại."
        )
    if "parking slot is not eligible for active session" in message:
        return (
            "Vị trí/khu vực không còn hoạt động hoặc không phù hợp loại xe. "
            "Vui lòng chọn lại vị trí phù hợp."
        )
    return None


def resolve_check_in_monthly_pass_id(
    db: Session,
    *,
    vehicle_id: int,
    vehicle_type_id: int,
    check_in_time: datetime,
) -> int | None:
    """Resolve the entitlement/rate required to admit one check-in.

    Every stay must have the same active/effective fallback rate that
    ``ParkingService.calculate_fee`` may need at checkout. A valid monthly
    pass is then snapshotted independently; if it expires during the stay,
    billing still has a stable rate contract to fall back to.
    """
    check_in_date = check_in_time.date()
    effective_price = crud_price_config.get_effective_active_price_by_vehicle_type(
        db,
        vehicle_type_id=vehicle_type_id,
        effective_on=check_in_date,
    )
    if effective_price is None:
        raise MissingEffectiveCheckInPriceError

    monthly_pass = db.execute(
        select(MonthlyPass).where(
            MonthlyPass.vehicle_id == vehicle_id,
            MonthlyPass.is_active == True,  # noqa: E712
            MonthlyPass.start_date <= check_in_date,
            MonthlyPass.end_date >= check_in_date,
        )
    ).scalars().first()
    if monthly_pass is not None:
        return monthly_pass.id
    return None

def get_parking_session(db: Session, session_id: str) -> ParkingSession | None:
    stmt = select(ParkingSession).where(ParkingSession.id == session_id)
    return db.execute(stmt).scalar_one_or_none()

def get_active_session_by_vehicle(db: Session, vehicle_id: int) -> ParkingSession | None:
    """Kiểm tra xem xe có đang ở trong bãi không (phiên đỗ xe chưa đóng)"""
    stmt = select(ParkingSession).where(
        and_(
            ParkingSession.vehicle_id == vehicle_id,
            ParkingSession.status == "active"
        )
    )
    return db.execute(stmt).scalar_one_or_none()

def get_parking_sessions(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(ParkingSession).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def create_parking_session(
    db: Session,
    session_in: session_schema.ParkingSessionCreate,
    staff_in_id: int,
    *,
    check_in_time: datetime,
    monthly_pass_id: int | None,
) -> ParkingSession:
    """Persist a prepared check-in without sampling a second clock."""
    db_session = ParkingSession(
        vehicle_id=session_in.vehicle_id,
        parking_slot_id=session_in.parking_slot_id,
        monthly_pass_id=monthly_pass_id,
        check_in_time=check_in_time,
        staff_in_id=staff_in_id,
        status="active"
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session

def delete_parking_session(db: Session, db_session: ParkingSession) -> ParkingSession:
    db.delete(db_session)
    db.commit()
    return db_session
