"""Explicit local payment simulator. This module never performs network I/O."""
import hmac
import secrets
from pathlib import Path

from fastapi import HTTPException
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from reportlab.graphics import renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing


class PortalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore", case_sensitive=True,
    )
    DEMO_PAYMENTS_ENABLED: bool = False
    PORTAL_ORDER_TTL_MINUTES: int = Field(default=15, ge=1, le=60)


class DemoGateway:
    def __init__(self, settings: PortalSettings | None = None):
        self.settings = settings or PortalSettings()

    def require_enabled(self):
        if not self.settings.DEMO_PAYMENTS_ENABLED:
            raise HTTPException(503, "Thanh toán DEMO đang tắt; chưa có giao dịch tiền thật nào được tạo.")

    def issue(self, order_id: str) -> tuple[str, str]:
        self.require_enabled()
        token = secrets.token_urlsafe(32)
        return token, self.payload(order_id, token)

    @staticmethod
    def payload(order_id: str, token: str) -> str:
        return f"PARKINGAI-DEMO:{order_id}:{token}"

    @staticmethod
    def verify(expected: str, supplied: str) -> bool:
        return bool(expected and supplied and hmac.compare_digest(expected.encode(), supplied.encode()))

    @staticmethod
    def qr_svg(payload: str) -> str:
        qr = QrCodeWidget(payload)
        x0, y0, x1, y1 = qr.getBounds()
        drawing = Drawing(240, 240, transform=[240 / (x1 - x0), 0, 0, 240 / (y1 - y0), 0, 0])
        drawing.add(qr)
        return renderSVG.drawToString(drawing)
