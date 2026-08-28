import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, Literal
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc
from sqlalchemy.exc import SQLAlchemyError

from core.clock import business_now, day_bounds, week_bounds, month_bounds, year_bounds
from core.errors import internal_server_error
from core.money import sum_exact_vnd
from core.sql_time import day_bucket, hour_bucket, month_bucket, week_bucket
from models.parking_session import ParkingSession
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType


logger = logging.getLogger(__name__)


ReportPeriod = Literal["day", "week", "month", "year"]

class ReportService:
    """
    ReportService gộp toàn bộ logic thống kê, báo cáo doanh thu và lưu lượng xe ra vào bãi.
    """
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _period_bounds(
        filter_type: ReportPeriod,
        anchor_date: date | None = None,
    ):
        """Một nguồn duy nhất cho boundary của revenue, traffic và export."""
        today = anchor_date or business_now().date()
        try:
            if filter_type == "day":
                return day_bounds(today)
            if filter_type == "week":
                return week_bounds(today)
            if filter_type == "month":
                return month_bounds(today)
            if filter_type == "year":
                return year_bounds(today)
        except (OverflowError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail="Ngày neo nằm ngoài phạm vi báo cáo được hỗ trợ.",
            ) from exc
        raise HTTPException(
            status_code=400,
            detail="Bộ lọc không hợp lệ (day, week, month, year).",
        )

    def get_revenue_report(
        self,
        filter_type: ReportPeriod,
        anchor_date: date | None = None,
    ) -> Dict[str, Any]:
        """Thống kê doanh thu theo ngày, tuần, tháng hoặc năm."""
        try:
            # Interval nửa mở [start, end_exclusive) — không dùng 23:59:59,
            # cộng .999999 thủ công hay BETWEEN inclusive cả hai đầu. Đây
            # cũng là điểm sửa bug đã biết: "year" trước đây dùng mốc cứng
            # datetime(year,12,31,23,59,59) THIẾU .999999 nên bỏ sót giao
            # dịch trong giây cuối năm; half-open loại bỏ hoàn toàn lớp bug
            # này cho cả 4 kỳ thay vì vá riêng lẻ từng kỳ.
            start_date, end_exclusive = self._period_bounds(
                filter_type, anchor_date
            )

            # Giữ nguyên CONTRACT response hiện tại: "end_date" là thời điểm
            # cuối cùng THUỘC kỳ báo cáo (không phải mốc loại trừ) — với
            # day/week/month giá trị này giống hệt trước khi sửa (time.max /
            # trừ 1 microsecond đều cho đúng 23:59:59.999999); với year giá
            # trị nay ĐÚNG (có .999999), khác giá trị cũ THIẾU microsecond —
            # đây chính là bản sửa bug được yêu cầu tường minh.
            end_date = end_exclusive - timedelta(microseconds=1)

            # Không dùng SQLite SUM cho tiền: tổng nhiều số nguyên hợp lệ có
            # thể vượt int64 và SQLite sẽ ném OperationalError trước khi lớp
            # domain kịp trả lỗi VND ổn định. Tổng bằng Python integer để giữ
            # độ chính xác không giới hạn, sau đó áp dụng exact-VND gate.
            fee_values = self.db.execute(select(
                ParkingSession.parking_fee
            ).where(
                ParkingSession.status == "completed",
                ParkingSession.check_out_time >= start_date,
                ParkingSession.check_out_time < end_exclusive
            )).scalars().all()
            total_trips = len(fee_values)
            exact_fees = [fee for fee in fee_values if fee is not None]
            total_revenue = sum_exact_vnd(
                exact_fees,
                label="Tổng doanh thu",
            )
            average_fee = (
                round(total_revenue / len(exact_fees), 2)
                if exact_fees
                else 0.0
            )

            # Tìm loại xe phổ biến nhất
            stmt_vtype = select(
                VehicleType.name,
                func.count(ParkingSession.id).label("count")
            ).join(Vehicle, ParkingSession.vehicle_id == Vehicle.id)\
             .join(VehicleType, Vehicle.vehicle_type_id == VehicleType.id)\
             .where(
                ParkingSession.status == "completed",
                ParkingSession.check_out_time >= start_date,
                ParkingSession.check_out_time < end_exclusive
            ).group_by(VehicleType.name).order_by(desc("count")).limit(1)

            vtype_res = self.db.execute(stmt_vtype).first()

            return {
                "filter_type": filter_type,
                "start_date": start_date,
                "end_date": end_date,
                "total_trips": total_trips,
                "total_revenue": total_revenue,
                "average_fee": average_fee,
                "most_frequent_vehicle_type": vtype_res.name if vtype_res else "Chưa có dữ liệu"
            }
        except SQLAlchemyError as db_err:
            raise internal_server_error(
                logger,
                event="Revenue report database failure",
                public_detail="Không thể tạo báo cáo doanh thu do lỗi hệ thống.",
                error=db_err,
            ) from db_err

    def get_traffic_report(
        self,
        filter_type: ReportPeriod,
        anchor_date: date | None = None,
    ) -> Dict[str, Any]:
        """Thống kê lưu lượng trong đúng kỳ day/week/month/year được chọn."""
        try:
            start_date, end_exclusive = self._period_bounds(
                filter_type, anchor_date
            )
            period_conditions = (
                ParkingSession.check_in_time >= start_date,
                ParkingSession.check_in_time < end_exclusive,
            )

            # Theo giờ
            hour_expression = hour_bucket(ParkingSession.check_in_time)
            hours_res = self.db.execute(
                select(hour_expression.label('h'), func.count(ParkingSession.id).label('c'))
                .where(*period_conditions)
                .group_by(hour_expression).order_by(hour_expression)
            ).all()
            traffic_by_hour = [{"time_label": f"{r.h}:00" if r.h else "00:00", "total_vehicles": r.c} for r in hours_res]

            # Theo ngày
            day_expression = day_bucket(ParkingSession.check_in_time)
            days_res = self.db.execute(
                select(day_expression.label('d'), func.count(ParkingSession.id).label('c'))
                .where(*period_conditions)
                .group_by(day_expression).order_by(day_expression)
            ).all()
            traffic_by_day = [{"time_label": r.d, "total_vehicles": r.c} for r in days_res if r.d]

            # Theo tuần
            week_expression = week_bucket(ParkingSession.check_in_time)
            weeks_res = self.db.execute(
                select(week_expression.label('w'), func.count(ParkingSession.id).label('c'))
                .where(*period_conditions)
                .group_by(week_expression).order_by(week_expression)
            ).all()
            traffic_by_week = [{"time_label": f"Tuần {r.w}", "total_vehicles": r.c} for r in weeks_res if r.w]

            # Theo tháng
            month_expression = month_bucket(ParkingSession.check_in_time)
            months_res = self.db.execute(
                select(month_expression.label('m'), func.count(ParkingSession.id).label('c'))
                .where(*period_conditions)
                .group_by(month_expression).order_by(month_expression)
            ).all()
            traffic_by_month = [{"time_label": r.m, "total_vehicles": r.c} for r in months_res if r.m]

            return {
                "traffic_by_hour": traffic_by_hour,
                "traffic_by_day": traffic_by_day,
                "traffic_by_week": traffic_by_week,
                "traffic_by_month": traffic_by_month
            }
        except SQLAlchemyError as db_err:
            raise internal_server_error(
                logger,
                event="Traffic report database failure",
                public_detail="Không thể tạo báo cáo lưu lượng do lỗi hệ thống.",
                error=db_err,
            ) from db_err


class TrafficService(ReportService):
    """Alias chuyên biệt cho thống kê lưu lượng, dùng bởi routers/report.py."""
    pass


class RevenueService(ReportService):
    """Alias chuyên biệt cho thống kê doanh thu, dùng bởi routers/report.py."""
    pass
