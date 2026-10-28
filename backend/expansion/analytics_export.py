"""CSV and Excel representations of the same authorized summary used by UI and AI.

Review 28/10/2026 R1-EXCEL/R2-11: both formats carry exactly the same rows
(``summary_rows``), including the stated date range, so the CSV and the
.xlsx of one query always agree.
"""
import csv
from io import BytesIO, StringIO

HEADER = ("Nhóm", "Mục / mốc thời gian", "Lượt vào", "Lượt ra", "Tổng vào + ra", "Giá trị", "Đơn vị / ghi chú")


def summary_rows(data):
    rows = []

    def row(*values):
        # Values controlled by a user (e.g. site/zone names) remain text when
        # opened in spreadsheets. Numeric negative net revenue stays numeric.
        safe = ["'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
                else value for value in values]
        rows.append(safe)

    row(*HEADER)
    for key, label in (("site_name", "Bãi"), ("start_date", "Từ ngày"), ("end_date", "Đến ngày"),
                       ("timezone", "Múi giờ"), ("source", "Nguồn"), ("data_scope", "Phạm vi dữ liệu")):
        row("Thông tin", label, "", "", "", data[key], "")
    row("Thông tin", "Dữ liệu mẫu", "", "", "", "Có" if data["demo_mode"] else "Không", "")
    row("Tổng kỳ", "Lưu lượng", data["total_arrivals"], data["total_departures"], data["total_movements"], "", "lượt, không phải số xe duy nhất")
    for section, collection, bucket in (("Theo ngày", "daily_traffic", "date"), ("Theo giờ", "hourly_traffic", "hour")):
        for item in data[collection]:
            row(section, item[bucket], item["arrivals"], item["departures"], item["movements"], "", "cộng dồn trong kỳ")
    for key, label in (("peak_hours", "Cao điểm vào"), ("peak_departure_hours", "Cao điểm ra"), ("peak_movement_hours", "Cao điểm tổng vào + ra")):
        row("Cao điểm", label, "", "", "", "; ".join(data[key]), "Chưa có lượt" if not data[key] else "cộng dồn trong kỳ")
    current = data["current_availability"]
    row("Hiện tại", "Thời điểm", "", "", "", current["as_of"], "không phải số đo kỳ lịch sử")
    for key, label in (("capacity_total", "Tổng vị trí"), ("total", "Vị trí đang phục vụ"),
                       ("inactive_slots", "Vị trí tạm ngừng"), ("occupied", "Vị trí có xe"),
                       ("available_now", "Vị trí còn nhận xe")):
        if key in current:
            row("Hiện tại", label, "", "", "", current[key], "vị trí")
    for zone in current["zones"]:
        for key, label in (("total", "Vị trí hoạt động"), ("occupied", "Có xe"), ("available_now", "Còn nhận xe"), ("reserved_slots", "Đã giữ")):
            row("Chỗ đỗ", zone["name"], "", "", "", zone[key], label)
    if data["revenue"] is not None:
        for key, label in (("parking_revenue", "Thu lượt gửi"), ("monthly_pass_revenue", "Thu vé tháng"),
                           ("prepaid_revenue", "Thu vé giờ/ngày"),
                           ("refunds", "Hoàn tiền"), ("total_revenue", "Thu ròng"),
                           ("demo_receipts", "Thu QR mô phỏng"), ("demo_refunds", "Hoàn QR mô phỏng")):
            row("Tài chính", label, "", "", "", data["revenue"][key], "VND")
    for note in data["notes"]:
        row("Ghi chú", note, "", "", "", "", "")
    return rows


def summary_csv(data):
    output = StringIO(newline="")
    csv.writer(output).writerows(summary_rows(data))
    return output.getvalue().encode("utf-8-sig")


def summary_xlsx(data):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from services.report_export_service import ReportExportService
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Bao cao"
    for values in summary_rows(data):
        # The legacy Excel export's text rule: no formula, no XML control character.
        sheet.append([ReportExportService._excel_safe_text(value) for value in values])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for column, width in zip("ABCDEFG", (14, 34, 10, 10, 14, 24, 30)):
        sheet.column_dimensions[column].width = width
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
