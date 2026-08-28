"""Đợt 10A — Timezone hardening: regression test cho semantics thời gian.

Nguyên tắc:
- Expected result luôn tính ĐỘC LẬP với implementation (không copy công thức).
- Test host-timezone-independence patch clock seam bằng datetime giả lập một
  UTC instant CỤ THỂ, KHÔNG dựa vào khả năng đổi timezone thật của Windows.
- Boundary test dùng fixture datetime chính xác tới microsecond, gọi thẳng
  ReportService/ParkingService hiện có — không cần module clock mới để chứng
  minh RED.

## Patch point clock được HỖ TRỢ (chuẩn hóa — đọc trước khi thêm test mới)

Toàn bộ business_now()/business_today() (và mọi hàm gọi chúng — server_now(),
get_revenue_report(), get_parking_statistics(), v.v. — bất kể ở module nào
import lại tên đó) đều đọc đồng hồ tại ĐÚNG MỘT chỗ: biến `datetime` bên
trong module `core.clock`. Vì vậy patch point CHUẨN và DUY NHẤT nên dùng cho
test timezone mới là:

    monkeypatch.setattr(clock_module, "datetime", HostClockAtFixedInstant)
    HostClockAtFixedInstant.FIXED_UTC = <một UTC instant cụ thể, có tzinfo>

KHÔNG patch `business_now`/`datetime` riêng lẻ trên từng module gọi
(`report_service_module.business_now`, `crud_session_module.datetime`, …) —
patch rải rác dễ trở thành stale target mỗi khi implementation refactor nơi
gọi thực tế của business_now(), như đã từng xảy ra ở Đợt 10A (xem lịch sử:
report_service.py từng gọi datetime.now() trực tiếp, patch tại
report_service_module.datetime; sau khi refactor sang gọi business_now() từ
core.clock, patch đó lặng lẽ hết tác dụng, khiến 2/4 test "pass" chỉ vì
trùng hợp năm hệ thống thật). Patch tại `core.clock.datetime` luôn đúng vì
đó là nơi DUY NHẤT `datetime.now(tz)` thực sự được gọi trong toàn bộ luồng
business-time.

`server_now()` (crud/parking_session.py) vẫn giữ lại CHỈ để tương thích
caller/test cũ đã có từ trước Đợt 10A — bản thân nó nay chỉ delegate thẳng
sang business_now(), nên patch `core.clock.datetime` cũng cascade đúng qua
server_now() mà không cần patch riêng.
"""
import datetime as dt
from datetime import date, datetime, time, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import core.clock as clock_module
import crud.parking_session as crud_session_module
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.price_config import PriceConfig
from services.auth_service import AuthService
from services.parking_service import ParkingService
from services.report_service import ReportService

VN_TZ_OFFSET = timedelta(hours=7)  # Asia/Ho_Chi_Minh, không DST


def make_headers(user) -> dict:
    token = AuthService().create_access_token(
        user_id=user.id, username=user.username, role=str(user.role)
    )
    return {"Authorization": f"Bearer {token}"}


class HostClockAtFixedInstant(dt.datetime):
    """Giả lập MỘT thời điểm UTC cụ thể mà OS host báo cáo, KHÔNG phụ thuộc
    khả năng đổi timezone thật của Windows.

    - `now()` không tham số mô phỏng "OS local clock" của một host chạy ở
      UTC (kịch bản cloud/container phổ biến nhất) — trả về đúng instant đó
      dưới dạng NAIVE (như os naive local time trên host UTC).
    - `now(tz)` mô phỏng đường đi ĐÚNG (aware, quy đổi theo IANA tz) — luôn
      tính từ CÙNG một instant UTC thật, bất kể tham số trước đó.

    Nhờ neo cả hai nhánh vào cùng FIXED_UTC, test chứng minh được: code cũ
    (dùng datetime.now() không tham số) cho kết quả SAI lệch đúng 7 giờ so
    với giờ Việt Nam thật, trong khi datetime.now(tz=Asia/Ho_Chi_Minh) luôn
    đúng — không phụ thuộc host OS đang set giờ gì.
    """
    FIXED_UTC: dt.datetime = None  # set bởi từng test

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.FIXED_UTC.replace(tzinfo=None)
        return cls.FIXED_UTC.astimezone(tz)


def _completed_session(db, vehicle, staff_id, check_in, check_out, fee, slot_id=None):
    s = ParkingSession(
        vehicle_id=vehicle.id, parking_slot_id=slot_id,
        check_in_time=check_in, check_out_time=check_out,
        parking_fee=fee, status="completed",
        staff_in_id=staff_id, staff_out_id=staff_id,
    )
    db.add(s)
    db.commit()
    return s


# ===========================================================================
# 8. Yearly report — bug đã biết (RED trước sửa, dùng ReportService hiện có)
# ===========================================================================


def test_yearly_report_includes_last_microsecond_of_year(
    monkeypatch, db_session: Session, vehicle, test_user,
):
    """Giao dịch persist tại đúng 31/12 23:59:59.999999 phải nằm trong báo
    cáo năm đó. Expected tính độc lập: tổng fee của các session có
    check_out_time trong [1/1 00:00:00.000000, năm-sau 1/1 00:00:00.000000).
    Trên code cũ, end_date năm = datetime(year,12,31,23,59,59) THIẾU
    .999999 -> giao dịch tại 23:59:59.999999 bị loại -> test FAIL."""
    year = 2026
    last_moment = datetime(year, 12, 31, 23, 59, 59, 999999)
    s1 = _completed_session(db_session, vehicle, test_user.id,
                            last_moment - timedelta(hours=1), last_moment, 77777.0)
    # Ép "now" của ReportService rơi vào đúng năm 2026 (không phụ thuộc ngày
    # chạy test thật). Patch point CHUẨN: core.clock.datetime (xem docstring
    # module ở đầu file) — report_service.py gọi business_now() (import từ
    # core.clock), nên patch tại đúng nơi business_now() thực sự đọc đồng hồ
    # sẽ cascade đúng, bất kể module nào import lại tên business_now.
    fixed_utc = datetime(year, 6, 15, 5, 0, 0, tzinfo=timezone.utc)  # VN 12:00 cùng ngày
    HostClockAtFixedInstant.FIXED_UTC = fixed_utc
    monkeypatch.setattr(clock_module, "datetime", HostClockAtFixedInstant)

    result = ReportService(db_session).get_revenue_report("year")

    assert result["total_revenue"] == 77777.0, (
        f"Giao dịch tại 23:59:59.999999 ngày 31/12 phải được tính vào báo cáo "
        f"năm; total_revenue thực tế={result['total_revenue']} (kỳ vọng 77777.0). "
        f"end_date trả về={result['end_date']!r}"
    )
    # Khóa cứng CONTRACT response: end_date trả về phải đúng bằng
    # microsecond cuối cùng của năm — không chỉ "loại đúng bản ghi" (có thể
    # đúng do trùng hợp) mà giá trị trả về phải chính xác tuyệt đối, để một
    # refactor sau này không thể âm thầm đổi giá trị end_date mà vẫn qua
    # test nếu tình cờ tổng tiền vẫn khớp.
    assert result["end_date"] == datetime(year, 12, 31, 23, 59, 59, 999999), (
        f"end_date của báo cáo năm phải đúng bằng 31/12 23:59:59.999999, "
        f"thực tế={result['end_date']!r}"
    )


def test_yearly_report_excludes_next_year_start(monkeypatch, db_session: Session, vehicle, test_user):
    """Giao dịch đúng 1/1 00:00:00.000000 năm SAU phải bị loại khỏi báo cáo
    năm hiện tại."""
    year = 2026
    next_year_start = datetime(year + 1, 1, 1, 0, 0, 0, 0)
    _completed_session(db_session, vehicle, test_user.id,
                       next_year_start - timedelta(hours=1), next_year_start, 55555.0)

    fixed_utc = datetime(year, 6, 15, 5, 0, 0, tzinfo=timezone.utc)  # VN 12:00 cùng ngày
    HostClockAtFixedInstant.FIXED_UTC = fixed_utc
    monkeypatch.setattr(clock_module, "datetime", HostClockAtFixedInstant)

    result = ReportService(db_session).get_revenue_report("year")

    assert result["total_revenue"] == 0.0, (
        f"Giao dịch 1/1 00:00:00 năm sau KHÔNG được tính vào báo cáo năm nay; "
        f"total_revenue thực tế={result['total_revenue']}"
    )


# ===========================================================================
# 5. Daily report half-open boundary
# ===========================================================================


def test_daily_report_half_open_boundary(db_session: Session, vehicle, test_user):
    target_day = date(2026, 3, 10)
    start_of_day = datetime.combine(target_day, time.min)
    just_before_next = datetime.combine(target_day, time(23, 59, 59, 999999))
    next_day_start = datetime.combine(target_day + timedelta(days=1), time.min)

    _completed_session(db_session, vehicle, test_user.id, start_of_day, start_of_day, 1000.0)
    _completed_session(db_session, vehicle, test_user.id,
                       just_before_next - timedelta(minutes=1), just_before_next, 2000.0)
    _completed_session(db_session, vehicle, test_user.id,
                       next_day_start, next_day_start, 4000.0)  # phải bị loại

    result = ParkingService(db_session).get_parking_statistics(target_date=target_day)
    assert result["total_revenue_today"] == 3000.0, (
        f"Kỳ vọng chỉ 2 giao dịch trong ngày (1000+2000=3000), thực tế="
        f"{result['total_revenue_today']} — có thể đã tính nhầm giao dịch "
        f"00:00:00 ngày kế tiếp, hoặc bỏ sót 23:59:59.999999"
    )


# ===========================================================================
# 6. Weekly report — xác nhận quy ước Thứ Hai đầu tuần
# ===========================================================================


def test_weekly_report_monday_boundary(monkeypatch, db_session: Session, vehicle, test_user):
    # Thứ Hai 2026-03-09; Chủ Nhật trước đó 2026-03-08 (KHÔNG thuộc tuần này)
    monday = date(2026, 3, 9)
    assert monday.weekday() == 0, "Cần chọn đúng một Thứ Hai để test có nghĩa"
    sunday_before = datetime.combine(monday - timedelta(days=1), time(23, 59, 59, 999999))
    monday_start = datetime.combine(monday, time.min)

    _completed_session(db_session, vehicle, test_user.id, sunday_before, sunday_before, 9999.0)
    _completed_session(db_session, vehicle, test_user.id, monday_start, monday_start, 1111.0)

    # Thứ Hai 10:00 VN = 03:00 UTC cùng ngày
    fixed_utc = datetime.combine(monday, time(3, 0)).replace(tzinfo=timezone.utc)
    HostClockAtFixedInstant.FIXED_UTC = fixed_utc
    monkeypatch.setattr(clock_module, "datetime", HostClockAtFixedInstant)

    result = ReportService(db_session).get_revenue_report("week")

    assert result["total_revenue"] == 1111.0, (
        f"Chủ Nhật trước Thứ Hai không được tính vào tuần hiện tại; "
        f"total_revenue={result['total_revenue']} (kỳ vọng 1111.0)"
    )


# ===========================================================================
# 7. Monthly report — 28/29/30/31 ngày + năm nhuận
# ===========================================================================


@pytest.mark.parametrize("year,month,days_in_month", [
    (2026, 2, 28),   # Feb thường
    (2028, 2, 29),   # Feb năm nhuận
    (2026, 4, 30),
    (2026, 1, 31),
])
def test_monthly_report_last_day_included_first_day_next_month_excluded(
    monkeypatch, db_session: Session, vehicle, test_user, year, month, days_in_month,
):
    last_moment = datetime(year, month, days_in_month, 23, 59, 59, 999999)
    if month == 12:
        next_month_start = datetime(year + 1, 1, 1)
    else:
        next_month_start = datetime(year, month + 1, 1)

    _completed_session(db_session, vehicle, test_user.id,
                       last_moment - timedelta(hours=1), last_moment, 3000.0)
    _completed_session(db_session, vehicle, test_user.id,
                       next_month_start, next_month_start, 6000.0)  # phải bị loại

    fixed_utc = datetime(year, month, 15, 3, 0, 0, tzinfo=timezone.utc)  # VN 10:00 cùng ngày
    HostClockAtFixedInstant.FIXED_UTC = fixed_utc
    monkeypatch.setattr(clock_module, "datetime", HostClockAtFixedInstant)

    result = ReportService(db_session).get_revenue_report("month")

    assert result["total_revenue"] == 3000.0, (
        f"Tháng {month}/{year} ({days_in_month} ngày): kỳ vọng chỉ giao dịch "
        f"cuối tháng (3000), thực tế={result['total_revenue']}"
    )


# ===========================================================================
# 9. AI/statistics input — daily summaries dùng đúng boundary business-local
# ===========================================================================


def test_daily_summaries_half_open_boundary_for_ai_weekly_report(
    db_session: Session, vehicle, test_user,
):
    d1 = date(2026, 5, 1)
    d2 = date(2026, 5, 2)
    just_before_d2 = datetime.combine(d1, time(23, 59, 59, 999999))
    d2_start = datetime.combine(d2, time.min)

    _completed_session(db_session, vehicle, test_user.id, just_before_d2, just_before_d2, 1500.0)
    _completed_session(db_session, vehicle, test_user.id, d2_start, d2_start, 2500.0)

    summaries = ParkingService(db_session).get_daily_summaries(d1, d2)
    by_date = {s["date"]: s for s in summaries}
    assert by_date[d1.isoformat()]["revenue"] == 1500.0, (
        f"23:59:59.999999 ngày {d1} phải thuộc về chính ngày {d1}, "
        f"thực tế={by_date[d1.isoformat()]}"
    )
    assert by_date[d2.isoformat()]["revenue"] == 2500.0


# ===========================================================================
# 1. Host timezone independence — patch tại core.clock.datetime, đúng nơi
#    business_now() thực sự gọi datetime.now(tz) sau khi server_now() được
#    refactor để delegate sang core.clock (Giai đoạn C).
# ===========================================================================


def test_server_now_is_host_timezone_independent(monkeypatch):
    """Một UTC instant cụ thể (2026-01-01 17:00:00 UTC) PHẢI cho cùng một
    business datetime Việt Nam (2026-01-02 00:00:00, UTC+7) bất kể host OS
    đang ở timezone nào. Trên code cũ, server_now() = datetime.now() không
    tham số -> nếu host là UTC, trả thẳng 17:00:00 (giờ UTC bị hiểu nhầm là
    giờ VN) -> lệch đúng 7 giờ -> test FAIL."""
    fixed_utc = datetime(2026, 1, 1, 17, 0, 0, tzinfo=timezone.utc)
    expected_vn = datetime(2026, 1, 2, 0, 0, 0)  # 17:00 UTC + 7h = 00:00 hôm sau

    HostClockAtFixedInstant.FIXED_UTC = fixed_utc
    monkeypatch.setattr(clock_module, "datetime", HostClockAtFixedInstant)

    result = crud_session_module.server_now()

    assert result == expected_vn, (
        f"server_now() phải độc lập với timezone host. UTC instant giả lập="
        f"{fixed_utc.isoformat()} -> kỳ vọng giờ VN={expected_vn}, "
        f"thực tế={result}. Lệch {(result - expected_vn)} — nếu đúng 7:00:00 "
        f"nghĩa là server_now() đang coi giờ UTC của host như giờ VN."
    )


# ===========================================================================
# 2+3. Check-in sát nửa đêm VN (UTC vẫn ngày D-1) + check-out qua ngày
# ===========================================================================


def test_check_in_near_midnight_uses_vietnam_date_for_session_and_monthly_pass(
    monkeypatch, client: TestClient, auth_headers: dict, db_session: Session,
    vehicle, vehicle_type, customer, parking_slot, price_config,
):
    """17:30 UTC ngày D-1 = 00:30 ngày D tại Việt Nam. Vé tháng CHỈ hiệu lực
    đúng ngày D (tương lai) phải được gắn vào phiên check-in tại thời điểm
    UTC này — chứng minh session VÀ tra cứu vé tháng dùng CÙNG một ngày D
    theo giờ Việt Nam, không phải ngày D-1 theo UTC."""
    pass_day = date(2026, 9, 1)  # ngày D — vé CHỈ hiệu lực đúng ngày này
    db_session.add(MonthlyPass(
        customer_id=customer.id, vehicle_id=vehicle.id,
        start_date=pass_day, end_date=pass_day, is_active=True,
    ))
    db_session.commit()

    # UTC 2026-08-31 17:30:00 = VN 2026-09-01 00:30:00 (đúng ngày D, 30' sau nửa đêm)
    day_before = pass_day - timedelta(days=1)
    fixed_utc = datetime(day_before.year, day_before.month, day_before.day, 17, 30, 0,
                         tzinfo=timezone.utc)
    HostClockAtFixedInstant.FIXED_UTC = fixed_utc
    monkeypatch.setattr(clock_module, "datetime", HostClockAtFixedInstant)

    response = client.post("/parking/check-in", json={
        "license_plate": vehicle.license_plate, "vehicle_type_id": vehicle_type.id,
        "parking_slot_id": parking_slot.id,
    }, headers=auth_headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["monthly_pass_id"] is not None, (
        f"Vé chỉ hiệu lực ngày {pass_day} (giờ VN) phải được gắn khi check-in "
        f"tại UTC {fixed_utc.isoformat()} (= VN {pass_day} 00:30) — nếu None "
        f"nghĩa là hệ thống đang tra cứu vé theo ngày UTC ({pass_day - timedelta(days=1)})"
    )
    persisted_check_in = datetime.fromisoformat(body["check_in_time"])
    assert persisted_check_in.date() == pass_day, (
        f"check_in_time persisted phải là ngày {pass_day} (VN), "
        f"thực tế={persisted_check_in}"
    )


def test_check_out_duration_correct_across_midnight_utc_boundary(
    monkeypatch, client: TestClient, auth_headers: dict, db_session: Session,
    vehicle, vehicle_type, customer, parking_slot, price_config,
):
    """Check-in lúc VN 23:00 ngày D (UTC 16:00 ngày D), check-out lúc VN
    01:00 ngày D+1 (UTC 18:00 ngày D — CÙNG ngày UTC, khác ngày VN). Duration
    thật = 2 giờ. Nếu code dùng datetime.now() không tzinfo trên host UTC,
    hai mốc UTC 16:00 và 18:00 vẫn cách nhau đúng 2 giờ về mặt SỐ HỌC (không
    lệch 7 giờ ở đây vì duration là HIỆU của hai điểm cùng hệ quy chiếu) —
    test này xác nhận duration KHÔNG bị hỏng bởi việc quy đổi timezone khi
    tính phí, bất kể server dùng instant UTC nào làm nền."""
    day = date(2026, 9, 10)
    checkin_utc = datetime(day.year, day.month, day.day, 16, 0, 0, tzinfo=timezone.utc)
    checkout_utc = datetime(day.year, day.month, day.day, 18, 0, 0, tzinfo=timezone.utc)

    HostClockAtFixedInstant.FIXED_UTC = checkin_utc
    monkeypatch.setattr(clock_module, "datetime", HostClockAtFixedInstant)
    ci = client.post("/parking/check-in", json={
        "license_plate": vehicle.license_plate, "vehicle_type_id": vehicle_type.id,
        "parking_slot_id": parking_slot.id,
    }, headers=auth_headers)
    assert ci.status_code == 201, ci.text
    session_id = ci.json()["session_id"]

    HostClockAtFixedInstant.FIXED_UTC = checkout_utc
    co = client.put(f"/api/v1/parking-sessions/{session_id}/check-out", json={},
                     headers=auth_headers)
    assert co.status_code == 200, co.text
    body = co.json()

    persisted_in = datetime.fromisoformat(body["check_in_time"])
    persisted_out = datetime.fromisoformat(body["check_out_time"])
    actual_elapsed = (persisted_out - persisted_in).total_seconds()
    assert actual_elapsed == 2 * 3600, (
        f"Duration thật giữa hai UTC instant cách nhau đúng 2 giờ phải vẫn là "
        f"7200 giây sau khi quy đổi VN ở cả hai đầu, thực tế={actual_elapsed}s "
        f"(check_in={persisted_in}, check_out={persisted_out})"
    )
    import math
    expected_fee = math.ceil(actual_elapsed / 3600) * price_config.price
    assert body["parking_fee"] == expected_fee


# ===========================================================================
# 4. Vé tháng — hiệu lực từ đầu start_date đến hết end_date theo giờ VN
# ===========================================================================


def test_monthly_pass_active_from_start_of_start_date(
    monkeypatch, client: TestClient, auth_headers: dict, db_session: Session,
    vehicle, vehicle_type, customer, parking_slot, price_config,
):
    start_day = date(2026, 10, 5)
    db_session.add(MonthlyPass(
        customer_id=customer.id, vehicle_id=vehicle.id,
        start_date=start_day, end_date=start_day + timedelta(days=10), is_active=True,
    ))
    db_session.commit()

    # VN 00:00:01 đúng ngày bắt đầu = UTC 17:00:01 ngày hôm trước
    day_before = start_day - timedelta(days=1)
    fixed_utc = datetime(day_before.year, day_before.month, day_before.day, 17, 0, 1,
                         tzinfo=timezone.utc)
    HostClockAtFixedInstant.FIXED_UTC = fixed_utc
    monkeypatch.setattr(clock_module, "datetime", HostClockAtFixedInstant)

    r = client.post("/parking/check-in", json={
        "license_plate": vehicle.license_plate, "vehicle_type_id": vehicle_type.id,
        "parking_slot_id": parking_slot.id,
    }, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["monthly_pass_id"] is not None, (
        "Vé phải hiệu lực NGAY từ 00:00 giờ VN của start_date"
    )


def test_monthly_pass_active_until_end_of_end_date_vietnam(
    monkeypatch, client: TestClient, auth_headers: dict, db_session: Session,
    vehicle, vehicle_type, customer, parking_slot, price_config,
):
    end_day = date(2026, 10, 15)
    db_session.add(MonthlyPass(
        customer_id=customer.id, vehicle_id=vehicle.id,
        start_date=end_day - timedelta(days=10), end_date=end_day, is_active=True,
    ))
    db_session.commit()

    # VN 23:59:59 đúng end_date = UTC 16:59:59 CÙNG ngày
    fixed_utc = datetime(end_day.year, end_day.month, end_day.day, 16, 59, 59,
                         tzinfo=timezone.utc)
    HostClockAtFixedInstant.FIXED_UTC = fixed_utc
    monkeypatch.setattr(clock_module, "datetime", HostClockAtFixedInstant)

    r = client.post("/parking/check-in", json={
        "license_plate": vehicle.license_plate, "vehicle_type_id": vehicle_type.id,
        "parking_slot_id": parking_slot.id,
    }, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["monthly_pass_id"] is not None, (
        "Vé phải còn hiệu lực đến HẾT end_date theo giờ VN (23:59:59)"
    )


def test_monthly_pass_expired_after_end_date_vietnam(
    monkeypatch, client: TestClient, auth_headers: dict, db_session: Session,
    vehicle, vehicle_type, customer, parking_slot, price_config,
):
    end_day = date(2026, 10, 15)
    db_session.add(MonthlyPass(
        customer_id=customer.id, vehicle_id=vehicle.id,
        start_date=end_day - timedelta(days=10), end_date=end_day, is_active=True,
    ))
    db_session.commit()

    # VN 00:00:00 ngày KẾ TIẾP = UTC 17:00:00 đúng end_date
    fixed_utc = datetime(end_day.year, end_day.month, end_day.day, 17, 0, 0,
                         tzinfo=timezone.utc)
    HostClockAtFixedInstant.FIXED_UTC = fixed_utc
    monkeypatch.setattr(clock_module, "datetime", HostClockAtFixedInstant)

    r = client.post("/parking/check-in", json={
        "license_plate": vehicle.license_plate, "vehicle_type_id": vehicle_type.id,
        "parking_slot_id": parking_slot.id,
    }, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["monthly_pass_id"] is None, (
        "Vé PHẢI hết hiệu lực khi sang ngày kế tiếp theo giờ VN"
    )


@pytest.fixture
def auth_headers(test_user) -> dict:
    return make_headers(test_user)
