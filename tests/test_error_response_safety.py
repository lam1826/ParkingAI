from datetime import date

from fastapi import HTTPException
import pytest
from sqlalchemy.exc import SQLAlchemyError

from services.ai_service import AIService
from services.parking_service import ParkingService
from services.report_service import ReportService


INTERNAL_MARKER = "sqlite:///private/path?token=do-not-expose"


class FailingQuerySession:
    def execute(self, *_args, **_kwargs):
        raise SQLAlchemyError(INTERNAL_MARKER)


@pytest.mark.parametrize(
    ("call", "expected_detail"),
    [
        (
            lambda: ReportService(FailingQuerySession()).get_revenue_report("day"),
            "Không thể tạo báo cáo doanh thu do lỗi hệ thống.",
        ),
        (
            lambda: ReportService(FailingQuerySession()).get_traffic_report("day"),
            "Không thể tạo báo cáo lưu lượng do lỗi hệ thống.",
        ),
        (
            lambda: ParkingService(FailingQuerySession()).find_available_slot(1),
            "Không thể truy vấn vị trí đỗ do lỗi hệ thống.",
        ),
    ],
)
def test_database_failures_do_not_expose_internal_details(call, expected_detail):
    with pytest.raises(HTTPException) as captured:
        call()

    assert captured.value.status_code == 500
    assert captured.value.detail == expected_detail
    assert INTERNAL_MARKER not in captured.value.detail


def test_ai_persistence_failure_returns_generic_message(db_session, monkeypatch):
    service = AIService.__new__(AIService)
    service.db = db_session

    def fail_commit():
        raise SQLAlchemyError(INTERNAL_MARKER)

    monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(HTTPException) as captured:
        service.save_ai_report(
            report_type="DAILY_REPORT",
            prompt_used="prompt",
            content="content",
            generated_by_id=1,
        )

    assert captured.value.detail == "Không thể lưu lịch sử AI do lỗi hệ thống."
    assert INTERNAL_MARKER not in captured.value.detail


def test_ai_outer_failure_does_not_echo_exception(db_session, monkeypatch):
    service = AIService.__new__(AIService)
    service.db = db_session
    monkeypatch.setattr(service, "_generate_text", lambda _prompt: "Báo cáo")

    def fail_save(**_kwargs):
        raise RuntimeError(INTERNAL_MARKER)

    monkeypatch.setattr(service, "save_ai_report", fail_save)

    with pytest.raises(HTTPException) as captured:
        service.generate_daily_report(
            target_date=date(2026, 8, 25),
            parking_stats={"total": 0},
            user_id=1,
        )

    assert captured.value.detail == "Không thể tạo báo cáo ngày bằng AI do lỗi hệ thống."
    assert INTERNAL_MARKER not in captured.value.detail
