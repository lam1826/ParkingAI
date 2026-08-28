"""Đồng hồ nghiệp vụ dùng chung (Đợt 10A — timezone hardening).

Business timezone bắt buộc: Asia/Ho_Chi_Minh (không DST). Việt Nam luôn
UTC+7 nên không cần xử lý DST, nhưng server có thể chạy trên host/container
đặt hệ điều hành ở UTC hoặc bất kỳ timezone nào khác — `datetime.now()`
KHÔNG tham số phụ thuộc trực tiếp vào cấu hình đó nên không đáng tin cho
quyết định nghiệp vụ (ngày check-in, hiệu lực vé tháng, boundary báo cáo).

Thiết kế: trả về NAIVE datetime mang giờ Asia/Ho_Chi_Minh — đúng quy ước cột
`DateTime` (không timezone-aware) mà các timestamp NGHIỆP VỤ đang dùng và
dữ liệu lịch sử đã có (được tạo bằng `datetime.now()` trên máy chủ Việt
Nam). Không đổi kiểu cột, không migrate dữ liệu cũ — chỉ đổi CÁCH lấy giờ
hiện tại để không còn phụ thuộc timezone hệ điều hành.

## Phạm vi: chỉ timestamp NGHIỆP VỤ, KHÔNG phải mọi cột datetime

Quy ước "naive business-local" ở trên CHỈ áp dụng cho các timestamp do code
Python ghi qua module này:

- `parking_sessions.check_in_time` / `check_out_time`
- ngày quyết định hiệu lực vé tháng (`business_today()`)
- boundary báo cáo/thống kê (`day_bounds`/`week_bounds`/`month_bounds`/
  `year_bounds` và mặc định "hôm nay" của report)

NGƯỢC LẠI, các cột metadata `created_at`/`updated_at` trên hầu hết model
(audit_logs, users, ai_reports, roles, price_configs, vehicle_types,
parking_sessions, monthly_passes, customers, vehicles, parking_slots,
zones) dùng `server_default=func.now()` / `onupdate=func.now()` — giá trị do
CHÍNH SQLite sinh qua `CURRENT_TIMESTAMP`, và SQLite luôn trả **UTC**. Vì
vậy các cột đó là **UTC-naive**, KHÔNG phải business-local, và module này
không hề can thiệp vào chúng. Bất kỳ chỗ nào đọc/hiển thị các cột metadata
đó phải tự diễn giải chuỗi là UTC rồi mới quy đổi sang giờ Việt Nam (phía
frontend: xem `utils/formatMetadataTimestamp.js`). Đợt 10A cố ý KHÔNG đổi
schema/API/serialization của nhóm metadata này.

`datetime.now(tz)` (CÓ tham số tz) luôn tính từ đồng hồ UTC thật của hệ
thống rồi quy đổi theo `tz`, không phụ thuộc cấu hình timezone hệ điều hành
— đây là lý do hàm dưới đây an toàn trên mọi host bất kể `TZ` được set gì.

## Patch point được HỖ TRỢ cho test

Mọi quyết định thời gian nghiệp vụ (check-in/check-out, hiệu lực vé tháng,
boundary report) cuối cùng đều đi qua `business_now()` bên dưới — kể cả khi
gọi gián tiếp qua `server_now()` (crud/parking_session.py, giữ lại chỉ để
tương thích caller/test cũ) hay qua alias `business_now`/`business_today`
được import vào các module khác (parking_service.py, report_service.py,
routers/report.py). Vì hàm này đọc đồng hồ tại đúng MỘT chỗ — biến
`datetime` trong namespace của CHÍNH module `core.clock` — nên patch point
chuẩn, duy nhất nên dùng trong test là:

    import core.clock as clock_module
    monkeypatch.setattr(clock_module, "datetime", <lớp con dt.datetime giả lập>)

Patch tại đây cascade đúng tới mọi caller bất kể caller import lại tên hàm
nào, vì việc gọi `datetime.now(tz)` luôn thực thi bên trong module này.
KHÔNG patch `business_now`/`datetime` riêng lẻ trên từng module gọi — dễ trở
thành stale target khi implementation refactor nơi business_now() thực sự
được gọi (xem test_timezone_hardening.py để biết ví dụ minh họa cụ thể).
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BUSINESS_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def business_now() -> datetime:
    """Thời điểm hiện tại theo giờ nghiệp vụ Asia/Ho_Chi_Minh, dạng NAIVE
    (đã bỏ tzinfo) — đúng kiểu `datetime` mà các cột DB hiện tại lưu.
    Độc lập với timezone của hệ điều hành host."""
    return datetime.now(BUSINESS_TZ).replace(tzinfo=None)


def business_today() -> date:
    """Ngày hiện tại theo lịch Asia/Ho_Chi_Minh — dùng cho hiệu lực vé
    tháng, mặc định báo cáo và các quyết định "hôm nay" khác. KHÔNG dùng
    ngày UTC của host để quyết định nghiệp vụ."""
    return business_now().date()


def day_bounds(d: date) -> tuple[datetime, datetime]:
    """(start_inclusive, end_exclusive) cho một ngày — interval nửa mở
    `start <= t < end`, bao phủ đến đúng microsecond cuối cùng của ngày
    (23:59:59.999999) mà không cần cộng `.999999` thủ công hay trừ
    1 microsecond để tìm cuối kỳ."""
    start = datetime(d.year, d.month, d.day)
    return start, start + timedelta(days=1)


def week_bounds(d: date) -> tuple[datetime, datetime]:
    """(start_inclusive, end_exclusive) cho tuần chứa `d`. Giữ đúng quy ước
    hiện hành của `report_service.py`: tuần bắt đầu Thứ Hai
    (`d.weekday() == 0`)."""
    monday = d - timedelta(days=d.weekday())
    start = datetime(monday.year, monday.month, monday.day)
    return start, start + timedelta(days=7)


def month_bounds(d: date) -> tuple[datetime, datetime]:
    """(start_inclusive, end_exclusive) cho tháng chứa `d`."""
    start = datetime(d.year, d.month, 1)
    if d.month == 12:
        end = datetime(d.year + 1, 1, 1)
    else:
        end = datetime(d.year, d.month + 1, 1)
    return start, end


def year_bounds(d: date) -> tuple[datetime, datetime]:
    """(start_inclusive, end_exclusive) cho năm chứa `d`.

    Đây chính là điểm sửa bug đã biết: trước đây `end_date` của báo cáo năm
    được gán cứng `datetime(year, 12, 31, 23, 59, 59)` — THIẾU `.999999` so
    với day/week/month — khiến giao dịch trong giây cuối cùng của năm
    (23:59:59.000001–23:59:59.999999 ngày 31/12) bị loại khỏi báo cáo."""
    start = datetime(d.year, 1, 1)
    end = datetime(d.year + 1, 1, 1)
    return start, end
