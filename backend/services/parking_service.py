import logging
import math
from datetime import date, datetime, timedelta
from typing import Optional, Any, Dict

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc, extract, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from core.clock import business_today, day_bounds
from core.errors import internal_server_error
from core.money import MAX_EXACT_VND, sum_exact_vnd
from core.sql_time import day_bucket
from crud import parking_session as crud_parking_session
from crud.parking_session import claim_parking_slot, map_check_in_integrity_error

from models.vehicle import Vehicle
from models.vehicle_type import VehicleType
from models.parking_slot import ParkingSlot
from models.parking_session import ParkingSession
from models.monthly_pass import MonthlyPass
from models.price_config import PriceConfig
from models.zone import Zone
from models.user import User


logger = logging.getLogger(__name__)


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
        zone_id: Optional[int] = None,
        vehicle_id: Optional[int] = None,
    ) -> Optional[ParkingSlot]:

        try:
            stmt = select(ParkingSlot).join(
                Zone, ParkingSlot.zone_id == Zone.id
            ).where(
                ParkingSlot.vehicle_type_id == vehicle_type_id,
                ParkingSlot.is_occupied == False,
                ParkingSlot.is_active == True,
                Zone.is_active == True,
            )

            if zone_id:
                stmt = stmt.where(ParkingSlot.zone_id == zone_id)

            from expansion.reservations import admission_allowed
            from core.clock import business_now
            at = business_now()
            for candidate in self.db.scalars(stmt.order_by(ParkingSlot.id)):
                if admission_allowed(self.db, candidate.id, vehicle_id=vehicle_id, at=at, lock=False):
                    return candidate
            return None

        except SQLAlchemyError as db_err:
            raise internal_server_error(
                logger,
                event="Available-slot query failed",
                public_detail="Không thể truy vấn vị trí đỗ do lỗi hệ thống.",
                error=db_err,
            ) from db_err

    # ==========================================================
    # TÍNH PHÍ
    # ==========================================================
    def calculate_fee(
        self,
        vehicle_id: int,
        vehicle_type_id: int,
        time_in: datetime,
        time_out: datetime,
        monthly_pass_id: int | None = None,
        monthly_coverage_end: date | None = None,
    ) -> int:

        try:
            seconds = (time_out - time_in).total_seconds()

            if seconds < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Thời gian không hợp lệ."
                )

            # ID quyền lợi được snapshot vào ParkingSession tại check-in. Các
            # trường định danh/khoảng ngày của vé đã bị DB khóa sau khi có lịch
            # sử, nên có thể xác minh lại mà không trao quyền hồi tố. Việc tắt
            # is_active sau check-in không thu hồi quyền đã ghi nhận. Phiên mới
            # chốt ngày bao phủ liên tục của các kỳ cùng thẻ tại lúc vào; phiên
            # legacy NULL tiếp tục dùng ngày hết hạn của kỳ gốc.
            if monthly_pass_id is not None:
                monthly_pass = self.db.get(MonthlyPass, monthly_pass_id)
                if monthly_pass is None or monthly_pass.vehicle_id != vehicle_id:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=(
                            "Dữ liệu quyền lợi vé tháng của phiên gửi xe "
                            "không hợp lệ."
                        ),
                    )
                if (
                    monthly_pass.start_date
                    <= time_out.date()
                    <= (monthly_coverage_end or monthly_pass.end_date)
                ):
                    return 0

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

            # Tiền VND là số nguyên không âm. Migration chặn dữ liệu legacy
            # không tương thích ngay khi khởi động; guard này bảo đảm một
            # đường ghi ngoài ứng dụng cũng không bị ép int/làm tròn âm thầm.
            try:
                unit_price = int(price.price)
            except (TypeError, ValueError, OverflowError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Bảng giá chứa đơn giá VND không hợp lệ.",
                ) from exc
            if unit_price < 0 or price.price != unit_price:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Bảng giá chứa đơn giá VND không phải số nguyên không âm.",
                )

            if price.ticket_type.upper() == "HOURLY":
                fee = math.ceil(seconds / 3600) * unit_price
            elif price.ticket_type.upper() == "DAILY":
                fee = math.ceil(seconds / 86400) * unit_price
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Billing mode không được hỗ trợ."
                )

            if fee > MAX_EXACT_VND:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Phí gửi xe vượt phạm vi VND được hệ thống hỗ trợ.",
                )
            return fee

        except HTTPException:
            raise

        except SQLAlchemyError as db_err:
            raise internal_server_error(
                logger,
                event="Price lookup failed",
                public_detail="Không thể truy vấn bảng giá do lỗi hệ thống.",
                error=db_err,
            ) from db_err

    # ==========================================================
    # CHECK IN
    # ==========================================================
    def check_in(
        self,
        license_plate: str,
        vehicle_type_id: int,
        staff_id: int,
        zone_id: Optional[int] = None,
        parking_slot_id: Optional[int] = None,
        *,
        _check_in_time: datetime | None = None,
        _expected_site_id: int | None = None,
        _commit: bool = True,
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
                    .execution_options(populate_existing=True)
                ).scalar_one_or_none()

                if slot is None or not slot.is_active or not slot.zone.is_active:
                    raise HTTPException(
                        status_code=404,
                        detail="Vị trí đỗ hoặc khu vực không tồn tại hoặc đang bảo trì."
                    )

                if _expected_site_id is not None and self.db.scalar(select(Zone.id).where(
                    Zone.id == slot.zone_id, Zone.site_id == _expected_site_id,
                )) is None:
                    raise HTTPException(404, "Vị trí không còn thuộc bãi đã chọn. Hãy tải lại vị trí.")

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
                # Preserve the established "lot full" result before checking
                # billing configuration, but do not claim the candidate yet.
                slot = self.find_available_slot(vehicle_type_id, zone_id, vehicle.id)
                if slot is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Không còn chỗ trống."
                    )

            # Sample the business clock exactly once. Before any slot claim,
            # either snapshot a valid monthly-pass entitlement or prove that
            # a non-monthly checkout rate is already active/effective.
            # Reservation arrival supplies the instant already sampled after
            # its slot lock. It must not cross the arrival deadline on a second
            # clock read. These keyword-only values are never API body fields.
            check_in_time = _check_in_time if _check_in_time is not None else crud_parking_session.server_now()
            admission_site_id = _expected_site_id if _expected_site_id is not None else slot.zone.site_id
            monthly_pass_id = (
                crud_parking_session.resolve_check_in_monthly_pass_id(
                    self.db,
                    vehicle_id=vehicle.id,
                    vehicle_type_id=vehicle_type_id,
                    check_in_time=check_in_time,
                    site_id=admission_site_id,
                )
            )
            monthly_coverage_end = crud_parking_session.resolve_check_in_monthly_coverage_end(
                self.db, monthly_pass_id=monthly_pass_id, check_in_time=check_in_time,
                site_id=admission_site_id,
            )

            if parking_slot_id is not None:
                if not claim_parking_slot(
                    self.db,
                    slot.id,
                    expected_zone_id=slot.zone_id,
                    expected_vehicle_type_id=vehicle_type_id,
                    expected_site_id=admission_site_id,
                    vehicle_id=vehicle.id,
                    check_in_time=check_in_time,
                ):
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
                for _ in range(3):
                    if claim_parking_slot(
                        self.db,
                        slot.id,
                        expected_zone_id=slot.zone_id,
                        expected_vehicle_type_id=vehicle_type_id,
                        expected_site_id=admission_site_id,
                        vehicle_id=vehicle.id,
                        check_in_time=check_in_time,
                    ):
                        break
                    # Candidate vừa bị chiếm: làm mới trạng thái ORM để vòng
                    # lặp sau không chọn lại bản ghi cũ trong identity map.
                    self.db.expire(slot)
                    slot = self.find_available_slot(vehicle_type_id, zone_id, vehicle.id)
                    if slot is None:
                        raise HTTPException(
                            status_code=404,
                            detail="Không còn chỗ trống."
                        )

                else:
                    raise HTTPException(
                        status_code=409,
                        detail="Các vị trí trống đang được cấp phát đồng thời. "
                               "Vui lòng thử lại."
                    )

            session = ParkingSession(
                vehicle_id=vehicle.id,
                parking_slot_id=slot.id,
                monthly_pass_id=monthly_pass_id,
                monthly_coverage_end=monthly_coverage_end,
                check_in_time=check_in_time,
                status="active",
                staff_in_id=staff_id
            )

            self.db.add(session)
            self.db.flush()
            from expansion.reservations import record_admission
            from expansion.portal_service import capture_session_ownership
            record_admission(self.db, session)
            capture_session_ownership(self.db, session)

            # Claim slot + INSERT session cùng một transaction: commit ở đây
            # là điểm cùng-thành-công; mọi nhánh lỗi phía dưới rollback cả hai.
            if _commit:
                self.db.commit()
            else:
                # The reservation caller verifies the session binding before
                # committing the whole arrival. A failed verification can then
                # roll back the slot, session and reservation together.
                self.db.flush()
            self.db.refresh(session)

            return {
                "session_id": session.id,
                "license_plate": vehicle.license_plate,
                "slot_id": slot.id,
                "slot_name": slot.slot_name,
                "monthly_pass_id": session.monthly_pass_id,
                "monthly_coverage_end": session.monthly_coverage_end,
                "check_in_time": session.check_in_time,
                "status": session.status
            }

        except crud_parking_session.MissingEffectiveCheckInPriceError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Loại xe chưa có bảng giá đang áp dụng cho ngày check-in. "
                    "Hãy cấu hình bảng giá trước khi nhận xe."
                ),
            )

        except HTTPException:
            # Một HTTP error có thể xảy ra sau khi INSERT/flush xe mới hoặc
            # conditional slot claim. Rollback bảo đảm request bị từ chối
            # không để lại xe/session/slot ở trạng thái dở dang.
            self.db.rollback()
            raise

        except DBAPIError as db_err:
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
    def check_out(self, license_plate: str, staff_id: int, confirmation) -> Dict[str, Any]:
        """Compatibility response for the same signed, session-bound confirmation."""
        from services.checkout_service import CheckoutService
        from schemas.checkout import CheckoutConfirmation
        confirmed = CheckoutConfirmation.model_validate(confirmation)
        session = CheckoutService(self.db).confirm(confirmed, staff_id, license_plate=license_plate)
        vehicle = self.db.get(Vehicle, session.vehicle_id)
        return {
            "session_id": session.id, "license_plate": vehicle.license_plate,
            "check_in_time": session.check_in_time, "check_out_time": session.check_out_time,
            "duration_minutes": int((session.check_out_time - session.check_in_time).total_seconds() / 60),
            "parking_fee": session.parking_fee, "status": session.status,
        }

    # ==========================================================
    # THỐNG KÊ
    # ==========================================================
    def get_parking_statistics(self, target_date=None) -> Dict[str, Any]:
        """Thống kê hoạt động trong 1 ngày (mặc định: hôm nay)."""
        try:
            current_business_date = business_today()
            today = target_date or current_business_date

            start_day, end_day = day_bounds(today)

            total_vehicles = self.db.execute(
                select(func.count(ParkingSession.id)).where(
                    ParkingSession.check_in_time >= start_day,
                    ParkingSession.check_in_time < end_day
                )
            ).scalar() or 0

            from services.payment_service import PaymentService
            total_revenue = PaymentService.revenue_breakdown(self.db, start_day, end_day)["total_revenue"]

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

            result = {
                "date": str(today),
                "total_vehicles_today": total_vehicles,
                "total_revenue_today": total_revenue,
                "peak_hour": peak_hour
            }

            if today == current_business_date:
                slot_stats = self.db.execute(
                    select(
                        ParkingSlot.is_occupied,
                        func.count(ParkingSlot.id)
                    )
                    .join(Zone, ParkingSlot.zone_id == Zone.id)
                    .where(
                        ParkingSlot.is_active == True,
                        Zone.is_active == True,
                    )
                    .group_by(ParkingSlot.is_occupied)
                ).all()
                available = 0
                occupied = 0
                for is_occupied, count in slot_stats:
                    if is_occupied:
                        occupied = count
                    else:
                        available = count
                result.update({
                    "available_slots": available,
                    "occupied_slots": occupied,
                    "slot_state_as_of": str(current_business_date),
                })
            else:
                result["slot_state_note"] = (
                    "Hệ thống không lưu snapshot tình trạng chỗ đỗ lịch sử; "
                    "available_slots và occupied_slots được chủ động bỏ khỏi "
                    "báo cáo để không gán trạng thái hiện tại cho ngày đã chọn."
                )

            return result

        except SQLAlchemyError as db_err:
            raise internal_server_error(
                logger,
                event="Parking statistics query failed",
                public_detail="Không thể tổng hợp thống kê do lỗi hệ thống.",
                error=db_err,
            ) from db_err

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
                    day_bucket(ParkingSession.check_in_time).label("day"),
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
                    day_bucket(ParkingSession.check_out_time).label("day"),
                    ParkingSession.parking_fee,
                )
                .where(
                    ParkingSession.status == "completed",
                    ParkingSession.check_out_time >= range_start,
                    ParkingSession.check_out_time < range_end,
                )
            )
            exit_fees: dict[str, list] = {}
            exit_counts: dict[str, int] = {}
            for row in self.db.execute(exits_stmt):
                exit_counts[row.day] = exit_counts.get(row.day, 0) + 1
                exit_fees.setdefault(row.day, []).append(row.parking_fee)
            exits = {
                day: {
                    "exits": exit_counts[day],
                    "revenue": sum_exact_vnd(
                        fees,
                        label="Tổng doanh thu",
                    ),
                }
                for day, fees in exit_fees.items()
            }

            from services.payment_service import PaymentService
            revenue_by_day = PaymentService.revenue_by_day(self.db, range_start, range_end)
            summaries = []
            current = start_date
            while current <= end_date:
                key = current.strftime("%Y-%m-%d")
                summaries.append({
                    "date": key,
                    "total_entries": entries.get(key, 0),
                    "total_exits": exits.get(key, {}).get("exits", 0),
                    "revenue": revenue_by_day.get(key, 0),
                })
                current += timedelta(days=1)

            return summaries

        except SQLAlchemyError as db_err:
            raise internal_server_error(
                logger,
                event="Daily summary query failed",
                public_detail="Không thể tổng hợp dữ liệu ngày do lỗi hệ thống.",
                error=db_err,
            ) from db_err

    # ==========================================================
    # THỐNG KÊ CHỖ ĐỖ TRỐNG THEO KHU VỰC
    # ==========================================================
    def get_available_slots_summary(self) -> Dict[str, Any]:
        """
        Thống kê tổng quan chỗ đỗ và danh sách vị trí trống theo từng khu vực.
        """

        try:
            # Lấy tất cả slot đang hoạt động
            stmt_slots = select(ParkingSlot).join(
                Zone, ParkingSlot.zone_id == Zone.id
            ).where(
                ParkingSlot.is_active == True,
                Zone.is_active == True,
            )
            slots = self.db.execute(stmt_slots).scalars().all()

            # Lấy danh sách khu vực
            stmt_zones = select(Zone).where(Zone.is_active == True)
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
            raise internal_server_error(
                logger,
                event="Parking availability query failed",
                public_detail="Không thể truy vấn trạng thái chỗ đỗ do lỗi hệ thống.",
                error=db_err,
            ) from db_err

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
                    "duration_minutes": (
                        int(
                            (session.check_out_time - session.check_in_time)
                            .total_seconds()
                            / 60
                        )
                        if session.check_out_time is not None
                        else None
                    ),
                    "parking_fee": session.parking_fee or 0,
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
            raise internal_server_error(
                logger,
                event="Parking history search failed",
                public_detail="Không thể tìm kiếm lịch sử gửi xe do lỗi hệ thống.",
                error=db_err,
            ) from db_err

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
        from services.payment_service import PaymentService
        total_revenue_today = PaymentService.revenue_breakdown(self.db, start_of_day, end_of_day)["total_revenue"]

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
            select(func.count(ParkingSlot.id))
            .join(Zone, Zone.id == ParkingSlot.zone_id)
            .where(
                ParkingSlot.is_active == True,
                Zone.is_active == True,
            )
        ).scalar() or 0

        occupied_slots = self.db.execute(
            select(func.count(ParkingSlot.id))
            .join(Zone, Zone.id == ParkingSlot.zone_id)
            .where(
                ParkingSlot.is_active == True,
                ParkingSlot.is_occupied == True,
                Zone.is_active == True,
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
            "total_revenue_today": total_revenue_today,
            "vehicles_currently_inside": vehicles_currently_inside,
            "vehicles_checked_out_today": vehicles_checked_out_today,
            "occupancy_rate_percentage": round(occupancy_rate, 2),
            "top_peak_hours": top_peak_hours
        }

    def get_ai_insight_data(self) -> Dict[str, Any]:
        """
        Tổng hợp gợi ý vận hành theo quy tắc từ dữ liệu bãi đỗ.

        Luồng này chỉ áp dụng ngưỡng tỷ lệ lấp đầy, không gọi AI provider.
        """
        try:
            # Lấy số xe đang trong bãi hiện tại
            current_inside = self.db.execute(
                select(func.count(ParkingSession.id)).where(ParkingSession.status == "active")
            ).scalar() or 0

            # Lấy tổng số slot
            total_slots = self.db.execute(
                select(func.count(ParkingSlot.id))
                .join(Zone, Zone.id == ParkingSlot.zone_id)
                .where(
                    ParkingSlot.is_active == True,
                    Zone.is_active == True,
                )
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
            raise internal_server_error(
                logger,
                event="Operational insight aggregation failed",
                public_detail="Không thể tổng hợp gợi ý vận hành do lỗi hệ thống.",
                error=db_err,
            ) from db_err

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
            raise internal_server_error(
                logger,
                event="Recent parking sessions query failed",
                public_detail="Không thể lấy phiên gửi xe gần đây do lỗi hệ thống.",
                error=db_err,
            ) from db_err

    def get_revenue_last_7_days(self) -> list:
        """
        Doanh thu theo từng ngày trong 7 ngày gần nhất (kể cả hôm nay),
        phục vụ biểu đồ doanh thu trên Dashboard.
        """
        try:
            today = business_today()
            start_date, _ = day_bounds(today - timedelta(days=6))
            _, end_exclusive = day_bounds(today)

            from services.payment_service import PaymentService
            rows = PaymentService.revenue_by_day(self.db, start_date, end_exclusive)

            result = []
            for i in range(7):
                d = today - timedelta(days=6 - i)
                key = d.strftime("%Y-%m-%d")
                result.append({"day": d.strftime("%d/%m"), "revenue": rows.get(key, 0)})
            return result
        except SQLAlchemyError as db_err:
            raise internal_server_error(
                logger,
                event="Seven-day revenue query failed",
                public_detail="Không thể lấy doanh thu 7 ngày do lỗi hệ thống.",
                error=db_err,
            ) from db_err
