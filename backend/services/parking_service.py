import math
from datetime import datetime, timedelta
from typing import Optional, Any, Dict

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func, extract, desc, asc
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from core.clock import business_today, day_bounds
from crud import parking_session as crud_parking_session
from crud.parking_session import claim_parking_slot, map_check_in_integrity_error

from models.vehicle import Vehicle
from models.vehicle_type import VehicleType
from models.parking_slot import ParkingSlot
from models.parking_session import ParkingSession
from models.price_config import PriceConfig
from models.monthly_pass import MonthlyPass
from models.zone import Zone
from models.user import User


class ParkingService:
    """
    ParkingService chịu trách nhiệm xử lý toàn bộ nghiệp vụ:
    - Tìm chỗ đỗ
    - Check-in
    - Check-out
    - Tính phí
    - Thống kê
    """

    def __init__(self, db: Session):
        self.db = db

    # ==========================================================
    # TÌM CHỖ ĐỖ
    # ==========================================================
    def find_available_slot(
        self,
        vehicle_type_id: int,
        zone_id: Optional[int] = None
    ) -> Optional[ParkingSlot]:

        try:
            stmt = select(ParkingSlot).where(
                ParkingSlot.vehicle_type_id == vehicle_type_id,
                ParkingSlot.is_occupied == False,
                ParkingSlot.is_active == True
            )

            if zone_id:
                stmt = stmt.where(ParkingSlot.zone_id == zone_id)

            return self.db.execute(stmt.limit(1)).scalar_one_or_none()

        except SQLAlchemyError as db_err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi cơ sở dữ liệu khi tìm chỗ đỗ: {db_err}"
            )

    # ==========================================================
    # TÍNH PHÍ
    # ==========================================================
    def calculate_fee(
        self,
        vehicle_id: int,
        vehicle_type_id: int,
        time_in: datetime,
        time_out: datetime
    ) -> float:

        try:
            seconds = (time_out - time_in).total_seconds()

            if seconds < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Thời gian không hợp lệ."
                )

            # Kiểm tra vé tháng (dùng first() để không crash nếu dữ liệu cũ
            # lỡ có 2 vé active chồng lấn)
            stmt = select(MonthlyPass).where(
                MonthlyPass.vehicle_id == vehicle_id,
                MonthlyPass.is_active == True,
                MonthlyPass.start_date <= time_out.date(),
                MonthlyPass.end_date >= time_out.date()
            )

            monthly_pass = self.db.execute(stmt).scalars().first()

            if monthly_pass:
                return 0.0

            # Lấy cấu hình giá
            stmt = select(PriceConfig).where(
                PriceConfig.vehicle_type_id == vehicle_type_id,
                PriceConfig.is_active == True,
                PriceConfig.effective_date <= time_out.date(),
            ).order_by(PriceConfig.effective_date.desc(), PriceConfig.id.desc()).limit(1)

            price = self.db.execute(stmt).scalar_one_or_none()

            if not price:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chưa cấu hình bảng giá."
                )

            if price.ticket_type.upper() == "HOURLY":
                return math.ceil(seconds / 3600) * float(price.price)

            elif price.ticket_type.upper() == "DAILY":
                return math.ceil(seconds / 86400) * float(price.price)

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Billing mode không được hỗ trợ."
            )

        except HTTPException:
            raise

        except SQLAlchemyError as db_err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi truy vấn bảng giá: {db_err}"
            )

    # ==========================================================
    # CHECK IN
    # ==========================================================
    def check_in(
        self,
        license_plate: str,
        vehicle_type_id: int,
        staff_id: int,
        zone_id: Optional[int] = None,
        parking_slot_id: Optional[int] = None
    ) -> Dict[str, Any]:

        try:
            license_plate = license_plate.strip().upper()
            vehicle_type = self.db.execute(
                select(VehicleType).where(
                    VehicleType.id == vehicle_type_id
                )
            ).scalar_one_or_none()

            if not vehicle_type:
                raise HTTPException(
                    status_code=400,
                    detail="Loại xe không hợp lệ."
                )

            vehicle = self.db.execute(
                select(Vehicle).where(
                    Vehicle.license_plate == license_plate
                )
            ).scalar_one_or_none()

            if vehicle is None:
                vehicle = Vehicle(
                    license_plate=license_plate,
                    vehicle_type_id=vehicle_type_id
                )
                self.db.add(vehicle)
                try:
                    self.db.flush()
                except IntegrityError:
                    # Race tạo xe mới: request khác vừa INSERT cùng biển số.
                    # Chưa có write nào khác trong transaction nên rollback an
                    # toàn, rồi dùng lại bản ghi đã tồn tại thay vì trả 500.
                    self.db.rollback()
                    vehicle = self.db.execute(
                        select(Vehicle).where(
                            Vehicle.license_plate == license_plate
                        )
                    ).scalar_one_or_none()
                    if vehicle is None:
                        raise HTTPException(
                            status_code=500,
                            detail="Lỗi hệ thống khi đăng ký phương tiện."
                        )
                    self._validate_existing_vehicle(vehicle, vehicle_type_id)
                    self._ensure_vehicle_not_parked(vehicle.id)
            else:
                self._validate_existing_vehicle(vehicle, vehicle_type_id)
                self._ensure_vehicle_not_parked(vehicle.id)

            if parking_slot_id is not None:
                # Nhân viên chọn đích danh một vị trí đỗ -> kiểm tra đầy đủ
                # để trả đúng mã lỗi; claim nguyên tử phía dưới mới là lớp
                # chống race thật sự.
                slot = self.db.execute(
                    select(ParkingSlot).where(ParkingSlot.id == parking_slot_id)
                ).scalar_one_or_none()

                if slot is None or not slot.is_active:
                    raise HTTPException(
                        status_code=404,
                        detail="Vị trí đỗ không tồn tại hoặc đang bảo trì."
                    )

                if slot.is_occupied:
                    raise HTTPException(
                        status_code=409,
                        detail="Vị trí đỗ đã có xe."
                    )

                if slot.vehicle_type_id != vehicle_type_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Vị trí đỗ không hỗ trợ loại xe này."
                    )

                if zone_id is not None and slot.zone_id != zone_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Vị trí đỗ không thuộc khu vực đã chọn."
                    )

                if not claim_parking_slot(self.db, slot.id):
                    # Thua race: slot vừa bị request khác chiếm giữa lúc đọc
                    # và lúc UPDATE. Transaction chưa ghi gì khác nên trả 409.
                    self.db.rollback()
                    raise HTTPException(
                        status_code=409,
                        detail="Vị trí đỗ vừa được xe khác sử dụng. "
                               "Vui lòng chọn vị trí khác."
                    )
            else:
                # Tự động cấp chỗ: candidate có thể bị request khác chiếm ngay
                # trước khi mình claim -> thử lại có giới hạn với candidate
                # kế tiếp; hết lượt thì báo hết chỗ thay vì retry vô hạn.
                slot = None
                for _ in range(3):
                    candidate = self.find_available_slot(vehicle_type_id, zone_id)
                    if candidate is None:
                        raise HTTPException(
                            status_code=404,
                            detail="Không còn chỗ trống."
                        )
                    if claim_parking_slot(self.db, candidate.id):
                        slot = candidate
                        break
                    # Candidate vừa bị chiếm: làm mới trạng thái ORM để vòng
                    # lặp sau không chọn lại bản ghi cũ trong identity map.
                    self.db.expire(candidate)

                if slot is None:
                    raise HTTPException(
                        status_code=409,
                        detail="Các vị trí trống đang được cấp phát đồng thời. "
                               "Vui lòng thử lại."
                    )

            # Đồng hồ server lấy ĐÚNG MỘT LẦN: cùng timestamp dùng cho
            # check_in_time, ngày tra vé tháng và response — không thể lệch
            # ngày giữa session và vé tháng khi check-in sát nửa đêm.
            check_in_time = crud_parking_session.server_now()
            check_in_date = check_in_time.date()

            # Gắn vé tháng còn hiệu lực (nếu có) vào phiên gửi để truy vết
            monthly_pass = self.db.execute(
                select(MonthlyPass).where(
                    MonthlyPass.vehicle_id == vehicle.id,
                    MonthlyPass.is_active == True,
                    MonthlyPass.start_date <= check_in_date,
                    MonthlyPass.end_date >= check_in_date
                )
            ).scalars().first()

            session = ParkingSession(
                vehicle_id=vehicle.id,
                parking_slot_id=slot.id,
                monthly_pass_id=monthly_pass.id if monthly_pass else None,
                check_in_time=check_in_time,
                status="active",
                staff_in_id=staff_id
            )

            self.db.add(session)

            # Claim slot + INSERT session cùng một transaction: commit ở đây
            # là điểm cùng-thành-công; mọi nhánh lỗi phía dưới rollback cả hai.
            self.db.commit()
            self.db.refresh(session)

            return {
                "session_id": session.id,
                "license_plate": vehicle.license_plate,
                "slot_id": slot.id,
                "slot_name": slot.slot_name,
                "monthly_pass_id": session.monthly_pass_id,
                "check_in_time": session.check_in_time,
                "status": session.status
            }

        except HTTPException:
            raise

        except IntegrityError as db_err:
            # Rollback trả lại slot vừa claim (cùng transaction với INSERT).
            self.db.rollback()
            conflict_message = map_check_in_integrity_error(db_err)
            if conflict_message is not None:
                raise HTTPException(status_code=409, detail=conflict_message)
            # IntegrityError không thuộc hai xung đột nghiệp vụ đã biết:
            # không che thành 409, cũng không lộ raw SQL cho client.
            raise HTTPException(
                status_code=500,
                detail="Lỗi hệ thống khi ghi phiên gửi xe."
            )

        except SQLAlchemyError:
            self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Lỗi hệ thống khi xử lý check-in."
            )

    @staticmethod
    def _validate_existing_vehicle(vehicle: Vehicle, vehicle_type_id: int) -> None:
        if vehicle.vehicle_type_id != vehicle_type_id:
            raise HTTPException(
                status_code=400,
                detail="Loại xe không khớp với phương tiện đã đăng ký.",
            )

    def _ensure_vehicle_not_parked(self, vehicle_id: int) -> None:
        active = self.db.execute(
            select(ParkingSession).where(
                ParkingSession.vehicle_id == vehicle_id,
                ParkingSession.status == "active"
            )
        ).scalars().first()
        if active:
            raise HTTPException(
                status_code=400,
                detail="Xe đang ở trong bãi."
            )

    # ==========================================================
    # CHECK OUT
    # ==========================================================
    def check_out(self, license_plate: str, staff_id: int) -> Dict[str, Any]:
        """
        Thực hiện quy trình check-out:
        1. Tìm ParkingSession đang ACTIVE.
        2. Nếu không có thì trả lỗi.
        3. Ghi time_out.
        4. Kiểm tra vé tháng/tính phí.
        5. Cập nhật ParkingSession.
        6. Giải phóng ParkingSlot.
        7. Trả hóa đơn.
        """

        try:
            license_plate = license_plate.strip().upper()
            stmt = (
                select(ParkingSession, Vehicle)
                .join(
                    Vehicle,
                    ParkingSession.vehicle_id == Vehicle.id
                )
                .where(
                    Vehicle.license_plate == license_plate,
                    ParkingSession.status == "active"
                )
            )

            result = self.db.execute(stmt).first()

            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Không tìm thấy phiên đỗ xe hoạt động nào cho biển số: {license_plate}"
                )

            session, vehicle = result

            # Claim NGUYÊN TỬ active -> completed TRƯỚC khi tính phí: hai
            # request cùng thấy session active thì chỉ một UPDATE có điều kiện
            # thành công; request thua không được tính phí lần hai hay ghi đè
            # thời gian/nhân viên của winner. Claim + phí + slot cùng một
            # transaction — lỗi ở bất kỳ bước nào rollback về active.
            if not crud_parking_session.claim_session_for_checkout(self.db, session.id):
                self.db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Xe vừa được check-out bởi một yêu cầu khác. "
                           "Vui lòng tải lại để xem kết quả."
                )

            # parking_slot_id là cột optional -> lấy slot riêng (nếu có) thay vì
            # bắt buộc INNER JOIN, tránh loại bỏ nhầm các phiên hợp lệ không gắn slot.
            slot = None
            if session.parking_slot_id is not None:
                slot = self.db.execute(
                    select(ParkingSlot).where(ParkingSlot.id == session.parking_slot_id)
                ).scalar_one_or_none()

            # Đồng hồ server, lấy ĐÚNG MỘT LẦN: response, tính phí và DB dùng
            # cùng một giá trị.
            check_out_time = crud_parking_session.server_now()
            session.check_out_time = check_out_time

            fee = self.calculate_fee(
                vehicle_id=vehicle.id,
                vehicle_type_id=vehicle.vehicle_type_id,
                time_in=session.check_in_time,
                time_out=check_out_time
            )

            session.parking_fee = fee
            session.status = "completed"  # đồng bộ ORM với UPDATE claim ở trên
            session.staff_out_id = staff_id

            if slot is not None:
                slot.is_occupied = False

            self.db.commit()
            self.db.refresh(session)

            duration_minutes = int(
                (check_out_time - session.check_in_time).total_seconds() / 60
            )

            return {
                "session_id": session.id,
                "license_plate": vehicle.license_plate,
                "check_in_time": session.check_in_time,
                "check_out_time": session.check_out_time,
                "duration_minutes": duration_minutes,
                "parking_fee": fee,
                "status": session.status
            }

        except HTTPException:
            # calculate_fee ném HTTPException (thiếu bảng giá...) SAU khi đã
            # claim -> phải rollback để session trở lại active và slot giữ
            # nguyên, cho phép retry sau khi nguyên nhân được xử lý.
            self.db.rollback()
            raise

        except SQLAlchemyError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Lỗi hệ thống trong quá trình check-out."
            )

    # ==========================================================
    # THỐNG KÊ
    # ==========================================================
    def get_parking_statistics(self, target_date=None) -> Dict[str, Any]:
        """Thống kê hoạt động trong 1 ngày (mặc định: hôm nay)."""
        try:
            today = target_date or business_today()

            start_day, end_day = day_bounds(today)

            total_vehicles = self.db.execute(
                select(func.count(ParkingSession.id)).where(
                    ParkingSession.check_in_time >= start_day,
                    ParkingSession.check_in_time < end_day
                )
            ).scalar() or 0

            total_revenue = self.db.execute(
                select(func.sum(ParkingSession.parking_fee)).where(
                    ParkingSession.check_out_time >= start_day,
                    ParkingSession.check_out_time < end_day,
                    ParkingSession.status == "completed"
                )
            ).scalar() or 0.0

            slot_stats = self.db.execute(
                select(
                    ParkingSlot.is_occupied,
                    func.count(ParkingSlot.id)
                )
                .where(ParkingSlot.is_active == True)
                .group_by(ParkingSlot.is_occupied)
            ).all()

            available = 0
            occupied = 0

            for is_occupied, count in slot_stats:
                if is_occupied:
                    occupied = count
                else:
                    available = count

            peak_stmt = (
                select(
                    extract("hour", ParkingSession.check_in_time).label("hour"),
                    func.count(ParkingSession.id).label("count")
                )
                .where(
                    ParkingSession.check_in_time >= start_day,
                    ParkingSession.check_in_time < end_day
                )
                .group_by("hour")
                .order_by(desc("count"))
                .limit(1)
            )

            peak = self.db.execute(peak_stmt).first()

            if peak:
                peak_hour = f"{int(peak.hour):02d}:00 - {int(peak.hour)+1:02d}:00"
            else:
                peak_hour = "Chưa có dữ liệu"

            return {
                "date": str(today),
                "total_vehicles_today": total_vehicles,
                "total_revenue_today": float(total_revenue),
                "available_slots": available,
                "occupied_slots": occupied,
                "peak_hour": peak_hour
            }

        except SQLAlchemyError as db_err:
            raise HTTPException(
                status_code=500,
                detail=f"Lỗi thống kê: {db_err}"
            )

    # ==========================================================
    # TỔNG HỢP THEO TỪNG NGÀY (phục vụ báo cáo tuần của AI)
    # ==========================================================
    def get_daily_summaries(self, start_date, end_date) -> list:
        """
        Tổng hợp lượt xe vào, lượt xe ra và doanh thu theo từng ngày
        trong khoảng [start_date, end_date] — backend tổng hợp từ database
        trước khi gửi cho AI (AI không tự truy vấn dữ liệu).
        """
        try:
            range_start, _ = day_bounds(start_date)
            _, range_end = day_bounds(end_date)

            entries_stmt = (
                select(
                    func.strftime("%Y-%m-%d", ParkingSession.check_in_time).label("day"),
                    func.count(ParkingSession.id).label("entries"),
                )
                .where(
                    ParkingSession.check_in_time >= range_start,
                    ParkingSession.check_in_time < range_end,
                )
                .group_by("day")
            )
            entries = {r.day: r.entries for r in self.db.execute(entries_stmt).all()}

            exits_stmt = (
                select(
                    func.strftime("%Y-%m-%d", ParkingSession.check_out_time).label("day"),
                    func.count(ParkingSession.id).label("exits"),
                    func.coalesce(func.sum(ParkingSession.parking_fee), 0.0).label("revenue"),
                )
                .where(
                    ParkingSession.status == "completed",
                    ParkingSession.check_out_time >= range_start,
                    ParkingSession.check_out_time < range_end,
                )
                .group_by("day")
            )
            exits = {
                r.day: {"exits": r.exits, "revenue": float(r.revenue)}
                for r in self.db.execute(exits_stmt).all()
            }

            summaries = []
            current = start_date
            while current <= end_date:
                key = current.strftime("%Y-%m-%d")
                summaries.append({
                    "date": key,
                    "total_entries": entries.get(key, 0),
                    "total_exits": exits.get(key, {}).get("exits", 0),
                    "revenue": exits.get(key, {}).get("revenue", 0.0),
                })
                current += timedelta(days=1)

            return summaries

        except SQLAlchemyError as db_err:
            raise HTTPException(
                status_code=500,
                detail=f"Lỗi tổng hợp dữ liệu theo ngày: {db_err}"
            )

    # ==========================================================
    # THỐNG KÊ CHỖ ĐỖ TRỐNG THEO KHU VỰC
    # ==========================================================
    def get_available_slots_summary(self) -> Dict[str, Any]:
        """
        Thống kê tổng quan chỗ đỗ và danh sách vị trí trống theo từng khu vực.
        """

        try:
            # Lấy tất cả slot đang hoạt động
            stmt_slots = select(ParkingSlot).where(
                ParkingSlot.is_active == True
            )
            slots = self.db.execute(stmt_slots).scalars().all()

            # Lấy danh sách khu vực
            stmt_zones = select(Zone)
            zones = self.db.execute(stmt_zones).scalars().all()

            zone_map = {z.id: z.name for z in zones}

            total_slots = len(slots)
            total_occupied = sum(1 for s in slots if s.is_occupied)
            total_available = total_slots - total_occupied

            zone_data: Dict[Any, dict] = {}

            # Khởi tạo dữ liệu cho các Zone
            for z in zones:
                zone_data[z.id] = {
                    "zone_id": z.id,
                    "zone_name": z.name,
                    "total_slots": 0,
                    "occupied_slots": 0,
                    "available_slots": 0,
                    "available_slots_list": []
                }

            # Khu vực chung (slot không có zone)
            zone_data[None] = {
                "zone_id": None,
                "zone_name": "Khu vực chung",
                "total_slots": 0,
                "occupied_slots": 0,
                "available_slots": 0,
                "available_slots_list": []
            }

            for slot in slots:

                zone_id = getattr(slot, "zone_id", None)

                if zone_id not in zone_data:
                    zone_data[zone_id] = {
                        "zone_id": zone_id,
                        "zone_name": zone_map.get(zone_id, f"Khu vực {zone_id}"),
                        "total_slots": 0,
                        "occupied_slots": 0,
                        "available_slots": 0,
                        "available_slots_list": []
                    }

                zone_data[zone_id]["total_slots"] += 1

                if slot.is_occupied:
                    zone_data[zone_id]["occupied_slots"] += 1
                else:
                    zone_data[zone_id]["available_slots"] += 1
                    zone_data[zone_id]["available_slots_list"].append({
                        "id": slot.id,
                        "name": getattr(slot, "slot_name", f"Slot-{slot.id}"),
                        "vehicle_type_id": getattr(slot, "vehicle_type_id", None)
                    })

            active_zones = [
                z for z in zone_data.values()
                if z["total_slots"] > 0
            ]

            return {
                "total_slots": total_slots,
                "total_occupied": total_occupied,
                "total_available": total_available,
                "zones": active_zones
            }

        except SQLAlchemyError as db_err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi cơ sở dữ liệu khi truy vấn trạng thái chỗ đỗ: {db_err}"
            )

    # ==========================================================
    # TÌM KIẾM LỊCH SỬ GỬI XE
    # ==========================================================
    def search_sessions(
        self,
        license_plate: Optional[str] = None,
        parking_status: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        zone_id: Optional[int] = None,
        vehicle_type_id: Optional[int] = None,
        page: int = 1,
        size: int = 10,
        sort_by: str = "check_in_time",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """
        Tìm kiếm, lọc, sắp xếp và phân trang lịch sử gửi xe.
        """
        try:
            stmt = (
                select(ParkingSession)
                .join(Vehicle, ParkingSession.vehicle_id == Vehicle.id)
            )

            # Filter
            if license_plate:
                stmt = stmt.where(
                    Vehicle.license_plate.ilike(f"%{license_plate.strip()}%")
                )

            if vehicle_type_id:
                stmt = stmt.where(
                    Vehicle.vehicle_type_id == vehicle_type_id
                )

            if zone_id:
                stmt = stmt.join(
                    ParkingSlot,
                    ParkingSession.parking_slot_id == ParkingSlot.id
                ).where(ParkingSlot.zone_id == zone_id)

            if parking_status:
                stmt = stmt.where(
                    ParkingSession.status == parking_status.lower()
                )

            if date_from:
                stmt = stmt.where(
                    ParkingSession.check_in_time >= date_from
                )

            if date_to:
                stmt = stmt.where(
                    ParkingSession.check_in_time <= date_to
                )

            # Đếm tổng số bản ghi
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total_records = self.db.execute(count_stmt).scalar() or 0

            # Sắp xếp
            sort_column_map = {
                "check_in_time": ParkingSession.check_in_time,
                "check_out_time": ParkingSession.check_out_time,
                "parking_fee": ParkingSession.parking_fee
            }

            target_column = sort_column_map.get(
                sort_by,
                ParkingSession.check_in_time
            )

            if sort_order.lower() == "asc":
                stmt = stmt.order_by(asc(target_column))
            else:
                stmt = stmt.order_by(desc(target_column))

            # Phân trang
            offset = (page - 1) * size
            stmt = stmt.offset(offset).limit(size)

            sessions = self.db.execute(stmt).scalars().all()

            items = []

            for session in sessions:

                vehicle_info = self.db.get(
                    Vehicle,
                    session.vehicle_id
                )

                staff_info = None

                staff_id = session.staff_in_id

                if staff_id:
                    staff_info = self.db.get(
                        User,
                        staff_id
                    )

                slot_name = None
                zone_name = None
                if session.parking_slot_id:
                    slot_info = self.db.get(ParkingSlot, session.parking_slot_id)
                    if slot_info:
                        slot_name = slot_info.slot_name
                        zone_info = self.db.get(Zone, slot_info.zone_id)
                        if zone_info:
                            zone_name = zone_info.name

                items.append({
                    "session_id": session.id,
                    "vehicle": vehicle_info,
                    "slot_id": session.parking_slot_id,
                    "slot_name": slot_name,
                    "zone_name": zone_name,
                    "check_in_time": session.check_in_time,
                    "check_out_time": session.check_out_time,
                    "parking_fee": session.parking_fee or 0.0,
                    "status": session.status,
                    "handled_by_staff": staff_info
                })

            return {
                "total": total_records,
                "page": page,
                "size": size,
                "items": items
            }

        except SQLAlchemyError as db_err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi cơ sở dữ liệu khi tìm kiếm lịch sử: {db_err}"
            )

    # ==========================================================
    # DASHBOARD
    # ==========================================================
    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Thống kê tổng quan dữ liệu phục vụ Dashboard trong ngày.
        """
        today = business_today()
        start_of_day, end_of_day = day_bounds(today)

        # 1. Tổng số xe vào bãi hôm nay
        total_vehicles_today = self.db.execute(
            select(func.count(ParkingSession.id)).where(
                ParkingSession.check_in_time >= start_of_day,
                ParkingSession.check_in_time < end_of_day
            )
        ).scalar() or 0

        # 2. Tổng doanh thu hôm nay
        total_revenue_today = self.db.execute(
            select(func.sum(ParkingSession.parking_fee)).where(
                ParkingSession.check_out_time >= start_of_day,
                ParkingSession.check_out_time < end_of_day,
                ParkingSession.status == "completed"
            )
        ).scalar() or 0.0

        # 3. Xe đang trong bãi
        vehicles_currently_inside = self.db.execute(
            select(func.count(ParkingSession.id)).where(
                ParkingSession.status == "active"
            )
        ).scalar() or 0

        # 4. Xe đã ra hôm nay
        vehicles_checked_out_today = self.db.execute(
            select(func.count(ParkingSession.id)).where(
                ParkingSession.check_out_time >= start_of_day,
                ParkingSession.check_out_time < end_of_day,
                ParkingSession.status == "completed"
            )
        ).scalar() or 0

        # 5. Tỷ lệ lấp đầy
        total_slots = self.db.execute(
            select(func.count(ParkingSlot.id)).where(
                ParkingSlot.is_active == True
            )
        ).scalar() or 0

        occupied_slots = self.db.execute(
            select(func.count(ParkingSlot.id)).where(
                ParkingSlot.is_active == True,
                ParkingSlot.is_occupied == True
            )
        ).scalar() or 0

        occupancy_rate = (
            occupied_slots / total_slots * 100
            if total_slots > 0 else 0.0
        )

        # 6. Top 5 giờ cao điểm
        stmt_peak = (
            select(
                extract("hour", ParkingSession.check_in_time).label("hour_val"),
                func.count(ParkingSession.id).label("count_val")
            )
            .where(
                ParkingSession.check_in_time >= start_of_day,
                ParkingSession.check_in_time < end_of_day
            )
            .group_by("hour_val")
            .order_by(desc("count_val"))
            .limit(5)
        )

        peak_results = self.db.execute(stmt_peak).all()

        top_peak_hours = []

        for row in peak_results:
            if row.hour_val is not None:
                h = int(row.hour_val)
                top_peak_hours.append({
                    "hour": f"{h:02d}:00 - {h + 1:02d}:00",
                    "count": row.count_val
                })

        return {
            "total_vehicles_today": total_vehicles_today,
            "total_revenue_today": float(total_revenue_today),
            "vehicles_currently_inside": vehicles_currently_inside,
            "vehicles_checked_out_today": vehicles_checked_out_today,
            "occupancy_rate_percentage": round(occupancy_rate, 2),
            "top_peak_hours": top_peak_hours
        }

    def get_ai_insight_data(self) -> Dict[str, Any]:
        """
        Phân tích và đưa ra gợi ý thông minh dựa trên dữ liệu bãi đỗ xe hiện tại.
        """
        try:
            # Bạn có thể tích hợp gọi Gemini API trực tiếp tại đây,
            # hoặc trả về một phân tích tổng hợp thông minh dựa trên số liệu thực tế từ DB.
            # Lấy số xe đang trong bãi hiện tại
            current_inside = self.db.execute(
                select(func.count(ParkingSession.id)).where(ParkingSession.status == "active")
            ).scalar() or 0

            # Lấy tổng số slot
            total_slots = self.db.execute(
                select(func.count(ParkingSlot.id)).where(ParkingSlot.is_active == True)
            ).scalar() or 1

            occupancy = (current_inside / total_slots) * 100

            insight_message = (
                f"Hệ thống đang hoạt động ổn định. Tỷ lệ lấp đầy hiện tại là {occupancy:.1f}%. "
                f"Hiện có {current_inside} phương tiện đang gửi trong bãi. "
            )

            if occupancy > 80:
                insight_message += "⚠️ Cảnh báo: Bãi đỗ gần đầy, nhân viên nên chú ý điều phối xe ở các khu vực trống."
            else:
                insight_message += "✅ Bãi đỗ còn nhiều không gian trống, đáp ứng tốt nhu cầu gửi xe."

            return {
                "insight": insight_message
            }

        except SQLAlchemyError as db_err:
            raise HTTPException(
                status_code=500,
                detail=f"Lỗi khi tổng hợp AI Insight: {db_err}"
            )

    def get_recent_sessions(self, limit: int = 10) -> list:
        """
        Lấy danh sách các phiên gửi xe gần đây nhất (kèm biển số & loại xe)
        để hiển thị ở bảng "Phiên gửi xe gần đây" trên Dashboard.
        """
        try:
            stmt = (
                select(
                    ParkingSession.id,
                    ParkingSession.check_in_time,
                    ParkingSession.status,
                    Vehicle.license_plate,
                    VehicleType.name.label("vehicle_type_name"),
                )
                .join(Vehicle, ParkingSession.vehicle_id == Vehicle.id)
                .join(VehicleType, Vehicle.vehicle_type_id == VehicleType.id)
                .order_by(desc(ParkingSession.check_in_time))
                .limit(limit)
            )
            rows = self.db.execute(stmt).all()

            return [
                {
                    "id": r.id,
                    "plate": r.license_plate,
                    "vehicleType": r.vehicle_type_name,
                    "timeIn": r.check_in_time.isoformat() if r.check_in_time else None,
                    "status": "Đang đỗ" if r.status == "active" else "Đã rời bãi",
                }
                for r in rows
            ]
        except SQLAlchemyError as db_err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi cơ sở dữ liệu khi lấy phiên gửi xe gần đây: {db_err}"
            )

    def get_revenue_last_7_days(self) -> list:
        """
        Doanh thu theo từng ngày trong 7 ngày gần nhất (kể cả hôm nay),
        phục vụ biểu đồ doanh thu trên Dashboard.
        """
        try:
            today = business_today()
            start_date, _ = day_bounds(today - timedelta(days=6))

            stmt = (
                select(
                    func.strftime("%Y-%m-%d", ParkingSession.check_out_time).label("day"),
                    func.coalesce(func.sum(ParkingSession.parking_fee), 0.0).label("revenue"),
                )
                .where(
                    ParkingSession.status == "completed",
                    ParkingSession.check_out_time >= start_date,
                )
                .group_by("day")
            )
            rows = {r.day: float(r.revenue) for r in self.db.execute(stmt).all()}

            result = []
            for i in range(7):
                d = today - timedelta(days=6 - i)
                key = d.strftime("%Y-%m-%d")
                result.append({"day": d.strftime("%d/%m"), "revenue": rows.get(key, 0.0)})
            return result
        except SQLAlchemyError as db_err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi cơ sở dữ liệu khi lấy doanh thu 7 ngày: {db_err}"
            )
