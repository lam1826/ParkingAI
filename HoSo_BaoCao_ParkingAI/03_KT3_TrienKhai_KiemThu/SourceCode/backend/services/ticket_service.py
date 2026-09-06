"""Local signed QR tickets. A scan identifies a session; staff still confirms exit."""
import hashlib
import hmac
import uuid

from fastapi import HTTPException
from reportlab.graphics import renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing

from core.config import settings
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.vehicle import Vehicle


def ticket_token(session_id: str) -> str:
    body = "PA1." + str(uuid.UUID(session_id))
    signature = hmac.new(settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return body + "." + signature


def resolve_ticket(token: str) -> str:
    try:
        prefix, session_id, signature = token.strip().split(".")
        normalized_id = str(uuid.UUID(session_id))
        expected = ticket_token(normalized_id)
        if prefix != "PA1" or not hmac.compare_digest(token.strip(), expected):
            raise ValueError("invalid signature")
        return normalized_id
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(400, "Mã vé không hợp lệ hoặc chữ ký không khớp.") from exc


def get_ticket(db, session_id):
    session = db.get(ParkingSession, session_id)
    if session is None:
        raise HTTPException(404, "Không tìm thấy lượt gửi xe.")
    vehicle = db.get(Vehicle, session.vehicle_id)
    slot = db.get(ParkingSlot, session.parking_slot_id) if session.parking_slot_id else None
    token = ticket_token(session.id)
    widget = QrCodeWidget(token, barLevel="M", barBorder=4)
    bounds = widget.getBounds()
    size = 240
    drawing = Drawing(size, size, transform=[size / (bounds[2] - bounds[0]), 0, 0,
                                            size / (bounds[3] - bounds[1]), 0, 0])
    drawing.add(widget)
    return {"session_id": session.id, "license_plate": vehicle.license_plate,
            "slot": slot.slot_name if slot else None, "check_in_time": session.check_in_time,
            "check_out_time": session.check_out_time, "status": session.status,
            "parking_fee": session.parking_fee, "qr_payload": token,
            "qr_svg": renderSVG.drawToString(drawing)}
