from sqlalchemy.orm import Session
from sqlalchemy import select, and_, update
from sqlalchemy.exc import IntegrityError
from datetime import datetime
from core.clock import business_now
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.zone import Zone
from schemas import parking_session as session_schema


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
    """Chuyển session active -> completed NGUYÊN TỬ bằng conditional UPDATE.

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
        .values(status="completed")
    )
    return result.rowcount == 1


def claim_parking_slot(db: Session, slot_id: int) -> bool:
    """Chiếm vị trí đỗ NGUYÊN TỬ bằng conditional UPDATE.

    Chỉ thành công khi slot vẫn đang active và chưa occupied tại thời điểm
    UPDATE thực thi (SQLite tuần tự hóa các write). rowcount == 0 nghĩa là
    một request khác vừa chiếm slot hoặc slot vừa bị tắt — caller phải trả
    409/404 thay vì ghi đè. KHÔNG commit tại đây: claim phải nằm cùng
    transaction với INSERT session để cùng commit hoặc cùng rollback.
    """
    result = db.execute(
        update(ParkingSlot)
        .where(
            ParkingSlot.id == slot_id,
            ParkingSlot.is_occupied == False,  # noqa: E712
            ParkingSlot.is_active == True,  # noqa: E712
            ParkingSlot.zone_id.in_(
                select(Zone.id).where(Zone.is_active == True)  # noqa: E712
            ),
        )
        .values(is_occupied=True)
    )
    return result.rowcount == 1


def map_check_in_integrity_error(exc: IntegrityError) -> str | None:
    """Dịch IntegrityError của hai unique index check-in thành thông báo 409.

    Chỉ map ĐÚNG hai xung đột nghiệp vụ đã biết (tên index/cột nằm trong
    message của SQLite); mọi IntegrityError khác trả None để caller xử lý
    như lỗi hệ thống thay vì che mù quáng thành 409.
    """
    message = str(exc.orig) if exc.orig is not None else str(exc)
    # SQLite báo vi phạm partial unique index bằng TÊN CỘT (đã xác minh:
    # "UNIQUE constraint failed: parking_sessions.vehicle_id"), không phải tên
    # index. Hai cột này chỉ có đúng hai unique index của bất biến check-in
    # nên mapping không nhầm với ràng buộc khác.
    if "parking_sessions.vehicle_id" in message:
        return "Xe vừa được check-in ở một phiên khác. Vui lòng kiểm tra lại."
    if "parking_sessions.parking_slot_id" in message:
        return "Vị trí đỗ vừa được xe khác sử dụng. Vui lòng chọn vị trí khác."
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

def create_parking_session(db: Session, session_in: session_schema.ParkingSessionCreate, staff_in_id: int) -> ParkingSession:
    # check_in_time do SERVER quyết định — lấy đúng MỘT lần từ server_now()
    # (gọi qua global của module nên test monkeypatch được); schema không còn
    # nhận thời gian từ client.
    db_session = ParkingSession(
        vehicle_id=session_in.vehicle_id,
        parking_slot_id=session_in.parking_slot_id,
        check_in_time=server_now(),
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
