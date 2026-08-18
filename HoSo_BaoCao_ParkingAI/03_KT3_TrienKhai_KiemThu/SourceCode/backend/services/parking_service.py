import math
from datetime import datetime, time, timedelta
from typing import Optional, Any, Dict

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func, extract, desc, asc
from sqlalchemy.exc import SQLAlchemyError

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
                self.db.flush()

            else:
                if vehicle.vehicle_type_id != vehicle_type_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Loại xe không khớp với phương tiện đã đăng ký.",
                    )
                active = self.db.execute(
                    select(ParkingSession).where(
                        ParkingSession.vehicle_id == vehicle.id,
                        ParkingSession.status == "active"
                    )
                ).scalar_one_or_none()

                if active:
                    raise HTTPException(
                        status_code=400,
                        detail="Xe đang ở trong bãi."
                    )

            if parking_slot_id is not None:
                # Nhân viên chọn đích danh một vị trí đỗ -> kiểm tra đầy đủ
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
            else:
                slot = self.find_available_slot(
                    vehicle_type_id,
                    zone_id
                )

                if slot is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Không còn chỗ trống."
                    )

            slot.is_occupied = True

            # Gắn vé tháng còn hiệu lực (nếu có) vào phiên gửi để truy vết
            today = datetime.now().date()
            monthly_pass = self.db.execute(
                select(MonthlyPass).where(
                    MonthlyPass.vehicle_id == vehicle.id,
                    MonthlyPass.is_active == True,
                    MonthlyPass.start_date <= today,
                    MonthlyPass.end_date >= today
                )
            ).scalars().first()

            session = ParkingSession(
                vehicle_id=vehicle.id,
                parking_slot_id=slot.id,
                monthly_pass_id=monthly_pass.id if monthly_pass else None,
                check_in_time=datetime.now(),
                status="active",
                staff_in_id=staff_id
            )

            self.db.add(session)

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

        except SQLAlchemyError as db_err:
            self.db.rollback()

            raise HTTPException(
                status_code=500,
                detail=f"Lỗi hệ thống: {db_err}"
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

            # parking_slot_id là cột optional -> lấy slot riêng (nếu có) thay vì
            # bắt buộc INNER JOIN, tránh loại bỏ nhầm các phiên hợp lệ không gắn slot.
            slot = None
            if session.parking_slot_id is not None:
                slot = self.db.execute(
                    select(ParkingSlot).where(ParkingSlot.id == session.parking_slot_id)
                ).scalar_one_or_none()

            check_out_time = datetime.now()
            session.check_out_time = check_out_time

            fee = self.calculate_fee(
                vehicle_id=vehicle.id,
                vehicle_type_id=vehicle.vehicle_type_id,
                time_in=session.check_in_time,
                time_out=check_out_time
            )

            session.parking_fee = fee
            session.status = "completed"
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
            raise

        except SQLAlchemyError as db_err:
            self.db.rollback()

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi cơ sở dữ liệu trong quá trình check-out: {db_err}"
            )

    # ==========================================================
    # THỐNG KÊ
    # ==========================================================
    def get_parking_statistics(self, target_date=None) -> Dict[str, Any]:
        """Thống kê hoạt động trong 1 ngày (mặc định: hôm nay)."""
        try:
            today = target_date or datetime.now().date()

            start_day = datetime.combine(today, time.min)
            end_day = datetime.combine(today, time.max)

            total_vehicles = self.db.execute(
                select(func.count(ParkingSession.id)).where(
                    ParkingSession.check_in_time >= start_day,
                    ParkingSession.check_in_time <= end_day
                )
            ).scalar() or 0

            total_revenue = self.db.execute(
                select(func.sum(ParkingSession.parking_fee)).where(
                    ParkingSession.check_out_time >= start_day,
                    ParkingSession.check_out_time <= end_day,
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
                    ParkingSession.check_in_time <= end_day
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
            range_start = datetime.combine(start_date, time.min)
            range_end = datetime.combine(end_date, time.max)

            entries_stmt = (
                select(
                    func.strftime("%Y-%m-%d", ParkingSession.check_in_time).label("day"),
                    func.count(ParkingSession.id).label("entries"),
                )
                .where(
                    ParkingSession.check_in_time >= range_start,
                    ParkingSession.check_in_time <= range_end,
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
                    ParkingSession.check_out_time <= range_end,
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
        today = datetime.now().date()
        start_of_day = datetime.combine(today, time.min)
        end_of_day = datetime.combine(today, time.max)

        # 1. Tổng số xe vào bãi hôm nay
        total_vehicles_today = self.db.execute(
            select(func.count(ParkingSession.id)).where(
                ParkingSession.check_in_time >= start_of_day,
                ParkingSession.check_in_time <= end_of_day
            )
        ).scalar() or 0

        # 2. Tổng doanh thu hôm nay
        total_revenue_today = self.db.execute(
            select(func.sum(ParkingSession.parking_fee)).where(
                ParkingSession.check_out_time >= start_of_day,
                ParkingSession.check_out_time <= end_of_day,
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
                ParkingSession.check_out_time <= end_of_day,
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
                ParkingSession.check_in_time <= end_of_day
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
            today = datetime.now().date()
            start_of_day = datetime.combine(today, time.min)
            end_of_day = datetime.combine(today, time.max)

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
            today = datetime.now().date()
            start_date = datetime.combine(today - timedelta(days=6), time.min)

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
