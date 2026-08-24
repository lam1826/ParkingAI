from datetime import datetime, timedelta
from typing import Dict, Any, Literal
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc
from sqlalchemy.exc import SQLAlchemyError

from core.clock import business_now, day_bounds, week_bounds, month_bounds, year_bounds
from models.parking_session import ParkingSession
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType

class ReportService:
    """
    ReportService gộp toàn bộ logic thống kê, báo cáo doanh thu và lưu lượng xe ra vào bãi.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_revenue_report(self, filter_type: Literal["day", "week", "month", "year"]) -> Dict[str, Any]:
        """Thống kê doanh thu theo ngày, tuần, tháng hoặc năm."""
        try:
            now = business_now()
            today = now.date()

            # Interval nửa mở [start, end_exclusive) — không dùng 23:59:59,
            # cộng .999999 thủ công hay BETWEEN inclusive cả hai đầu. Đây
            # cũng là điểm sửa bug đã biết: "year" trước đây dùng mốc cứng
            # datetime(year,12,31,23,59,59) THIẾU .999999 nên bỏ sót giao
            # dịch trong giây cuối năm; half-open loại bỏ hoàn toàn lớp bug
            # này cho cả 4 kỳ thay vì vá riêng lẻ từng kỳ.
            if filter_type == "day":
                start_date, end_exclusive = day_bounds(today)
            elif filter_type == "week":
                start_date, end_exclusive = week_bounds(today)
            elif filter_type == "month":
                start_date, end_exclusive = month_bounds(today)
            elif filter_type == "year":
                start_date, end_exclusive = year_bounds(today)
            else:
                raise HTTPException(status_code=400, detail="Bộ lọc không hợp lệ (day, week, month, year).")

            # Giữ nguyên CONTRACT response hiện tại: "end_date" là thời điểm
            # cuối cùng THUỘC kỳ báo cáo (không phải mốc loại trừ) — với
            # day/week/month giá trị này giống hệt trước khi sửa (time.max /
            # trừ 1 microsecond đều cho đúng 23:59:59.999999); với year giá
            # trị nay ĐÚNG (có .999999), khác giá trị cũ THIẾU microsecond —
            # đây chính là bản sửa bug được yêu cầu tường minh.
            end_date = end_exclusive - timedelta(microseconds=1)

            # Thống kê tổng lượt, doanh thu, phí trung bình
            stmt_stats = select(
                func.count(ParkingSession.id).label("total_trips"),
                func.coalesce(func.sum(ParkingSession.parking_fee), 0.0).label("total_revenue"),
                func.coalesce(func.avg(ParkingSession.parking_fee), 0.0).label("average_fee")
            ).where(
                ParkingSession.status == "completed",
                ParkingSession.check_out_time >= start_date,
                ParkingSession.check_out_time < end_exclusive
            )
            stats = self.db.execute(stmt_stats).first()

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
                "total_trips": stats.total_trips if stats else 0,
                "total_revenue": float(stats.total_revenue if stats else 0.0),
                "average_fee": round(float(stats.average_fee if stats else 0.0), 2),
                "most_frequent_vehicle_type": vtype_res.name if vtype_res else "Chưa có dữ liệu"
            }
        except SQLAlchemyError as db_err:
            raise HTTPException(status_code=500, detail=f"Lỗi cơ sở dữ liệu doanh thu: {str(db_err)}")

    def get_traffic_report(self) -> Dict[str, Any]:
        """Thống kê lưu lượng theo giờ, ngày, tuần, tháng (Sử dụng SQLite function)."""
        try:
            # Theo giờ
            hours_res = self.db.execute(
                select(func.strftime('%H', ParkingSession.check_in_time).label('h'), func.count(ParkingSession.id).label('c'))
                .group_by('h').order_by('h')
            ).all()
            traffic_by_hour = [{"time_label": f"{r.h}:00" if r.h else "00:00", "total_vehicles": r.c} for r in hours_res]

            # Theo ngày
            days_res = self.db.execute(
                select(func.strftime('%Y-%m-%d', ParkingSession.check_in_time).label('d'), func.count(ParkingSession.id).label('c'))
                .group_by('d').order_by('d')
            ).all()
            traffic_by_day = [{"time_label": r.d, "total_vehicles": r.c} for r in days_res if r.d]

            # Theo tuần
            weeks_res = self.db.execute(
                select(func.strftime('%Y-%W', ParkingSession.check_in_time).label('w'), func.count(ParkingSession.id).label('c'))
                .group_by('w').order_by('w')
            ).all()
            traffic_by_week = [{"time_label": f"Tuần {r.w}", "total_vehicles": r.c} for r in weeks_res if r.w]

            # Theo tháng
            months_res = self.db.execute(
                select(func.strftime('%Y-%m', ParkingSession.check_in_time).label('m'), func.count(ParkingSession.id).label('c'))
                .group_by('m').order_by('m')
            ).all()
            traffic_by_month = [{"time_label": r.m, "total_vehicles": r.c} for r in months_res if r.m]

            return {
                "traffic_by_hour": traffic_by_hour,
                "traffic_by_day": traffic_by_day,
                "traffic_by_week": traffic_by_week,
                "traffic_by_month": traffic_by_month
            }
        except SQLAlchemyError as db_err:
            raise HTTPException(status_code=500, detail=f"Lỗi cơ sở dữ liệu lưu lượng: {str(db_err)}")


class TrafficService(ReportService):
    """Alias chuyên biệt cho thống kê lưu lượng, dùng bởi routers/report.py."""
    pass


class RevenueService(ReportService):
    """Alias chuyên biệt cho thống kê doanh thu, dùng bởi routers/report.py."""
    pass