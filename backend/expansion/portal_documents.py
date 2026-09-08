"""Downloadable customer receipts. DEMO is visible on the document itself."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from services.report_export_service import ReportExportService


def build_receipt_pdf(receipt, customer):
    font = ReportExportService._register_unicode_font()
    style = ParagraphStyle("receipt", fontName=font, fontSize=11, leading=17)
    heading = ParagraphStyle("receipt-heading", parent=style, fontSize=17, leading=23)
    output = BytesIO()
    story = [Paragraph("ParkingAI — Chứng từ " + ("hoàn" if receipt.kind == "refund" else "thu"), heading), Spacer(1, 14)]
    if receipt.method == "demo":
        story += [Paragraph("DEMO — MÔ PHỎNG ĐỒ ÁN; KHÔNG CÓ TIỀN THẬT ĐƯỢC CHUYỂN", heading), Spacer(1, 14)]
    values = [("Mã chứng từ", receipt.id), ("Khách hàng", customer.full_name),
        ("Thời gian", str(receipt.created_at)), ("Nguồn", f"{receipt.source_type} / {receipt.source_id}"),
        ("Số tiền", f"{receipt.amount:,} VND"), ("Phương thức", receipt.method),
        ("Phiếu thu gốc", receipt.original_payment_id or "—")]
    rows = [[Paragraph(escape(str(key)), style), Paragraph(escape(str(value)), style)] for key, value in values]
    table = Table(rows, colWidths=[120, 360], hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2f7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story += [table, Spacer(1, 18), Paragraph("Chứng từ nội bộ ParkingAI; không thay thế hóa đơn tài chính.", style)]
    SimpleDocTemplate(output, pagesize=A4, title="ParkingAI DEMO receipt" if receipt.method == "demo" else "ParkingAI receipt").build(story)
    return output.getvalue()
