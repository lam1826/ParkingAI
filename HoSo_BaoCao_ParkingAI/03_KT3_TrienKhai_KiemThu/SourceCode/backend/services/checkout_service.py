"""Short-lived fee quotes and atomic, explicitly confirmed departures."""
import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.clock import BUSINESS_TZ
from core.config import settings
from crud import parking_session as session_crud
from models.parking_session import ParkingSession
from models.monthly_pass import MonthlyPass
from models.parking_slot import ParkingSlot
from models.price_config import PriceConfig
from models.vehicle import Vehicle
from models.zone import Zone
from schemas.checkout import CheckoutConfirmation
from services.payment_service import PaymentService, lock_cash_operator

QUOTE_TTL_SECONDS = 120
QUOTE_PURPOSE = "parkingai.checkout-quote.v1"


def _error(code: str, message: str, status: int = 409) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def _secret() -> bytes:
    secret = settings.SECRET_KEY
    if not isinstance(secret, str) or len(secret.encode()) < 32:
        raise _error("checkout_unavailable", "Chưa cấu hình khóa xác nhận an toàn.", 503)
    return secret.encode()


def validate_checkout_signing_configuration() -> None:
    """Validate the release's signer configuration without exposing key bytes."""
    _secret()


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=BUSINESS_TZ) if value.tzinfo is None else value.astimezone(BUSINESS_TZ)


def _sign(payload: dict) -> str:
    body = _encode(_canonical(payload))
    signature = hmac.new(_secret(), (QUOTE_PURPOSE + "." + body).encode(), hashlib.sha256).digest()
    return "PCQ1." + body + "." + _encode(signature)


def _decode(token: str) -> dict:
    secret = _secret()
    try:
        if not isinstance(token, str) or len(token) > 4096:
            raise ValueError("token length")
        prefix, body, signature = token.split(".")
        expected = _encode(hmac.new(secret, (QUOTE_PURPOSE + "." + body).encode(), hashlib.sha256).digest())
        if prefix != "PCQ1" or not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        raw = base64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw)
        if _encode(raw) != body or set(payload) != {"purpose", "session_id", "actor_id", "state", "fee", "quoted_at", "expires_at", "nonce", "rate"}:
            raise ValueError("claims")
        if payload["purpose"] != QUOTE_PURPOSE or type(payload["fee"]) is not int or payload["fee"] < 0 or type(payload["actor_id"]) is not int:
            raise ValueError("claims")
        quoted = datetime.fromisoformat(payload["quoted_at"])
        expires = datetime.fromisoformat(payload["expires_at"])
        if quoted.tzinfo is None or expires.tzinfo is None or (expires - quoted).total_seconds() != QUOTE_TTL_SECONDS:
            raise ValueError("time claims")
        return payload
    except (ValueError, TypeError, AttributeError, KeyError, UnicodeError) as exc:
        raise _error("checkout_quote_invalid", "Phiếu xem phí không hợp lệ hoặc đã bị sửa.", 400) from exc


def _state(session: ParkingSession, vehicle: Vehicle) -> dict:
    return {
        "vehicle_id": session.vehicle_id, "vehicle_type_id": vehicle.vehicle_type_id,
        "license_plate": vehicle.license_plate, "parking_slot_id": session.parking_slot_id,
        "check_in_time": _aware(session.check_in_time).isoformat(),
        "monthly_pass_id": session.monthly_pass_id,
        "monthly_coverage_end": session.monthly_coverage_end.isoformat() if session.monthly_coverage_end else None,
        "status": "active",
    }


class CheckoutService:
    def __init__(self, db: Session):
        self.db = db

    def _load(self, session_id: str):
        result = self.db.execute(select(ParkingSession, Vehicle).join(
            Vehicle, Vehicle.id == ParkingSession.vehicle_id,
        ).where(ParkingSession.id == session_id).execution_options(populate_existing=True)).first()
        if result is None:
            raise _error("checkout_session_not_found", "Không tìm thấy lượt gửi xe.", 404)
        return result

    def _rate(self, vehicle_type_id: int, at: datetime, *, lock: bool = False):
        query = select(PriceConfig).where(
            PriceConfig.vehicle_type_id == vehicle_type_id, PriceConfig.is_active.is_(True),
            PriceConfig.effective_date <= at.date(),
        ).order_by(PriceConfig.effective_date.desc(), PriceConfig.id.desc()).limit(1)
        if lock:
            query = query.with_for_update(read=True)
        rate = self.db.scalar(query.execution_options(populate_existing=True))
        return None if rate is None else {
            "id": rate.id, "price": rate.price, "ticket_type": rate.ticket_type,
            "effective_date": rate.effective_date.isoformat(),
        }

    def _fee(self, session, vehicle, at):
        # Keep one billing implementation for fee tests and both API routes.
        from services.parking_service import ParkingService
        return ParkingService(self.db).calculate_fee(
            vehicle_id=vehicle.id, vehicle_type_id=vehicle.vehicle_type_id,
            time_in=session.check_in_time, time_out=at,
            monthly_pass_id=session.monthly_pass_id,
            monthly_coverage_end=session.monthly_coverage_end,
        )

    def quote(self, session_id: str, actor_id: int) -> dict:
        session, vehicle = self._load(session_id)
        if session.status != "active":
            raise _error("checkout_state_conflict", "Lượt gửi không còn đang hoạt động. Hãy tra lịch sử xe ra.")
        at = session_crud.server_now()
        expires = _aware(at) + timedelta(seconds=QUOTE_TTL_SECONDS)
        rate = self._rate(vehicle.vehicle_type_id, at)
        fee = self._fee(session, vehicle, at)
        token = _sign({
            "purpose": QUOTE_PURPOSE, "session_id": session.id, "actor_id": actor_id,
            "state": _state(session, vehicle), "fee": fee, "rate": rate,
            "quoted_at": _aware(at).isoformat(), "expires_at": expires.isoformat(),
            "nonce": secrets.token_hex(16),
        })
        slot = self.db.get(ParkingSlot, session.parking_slot_id) if session.parking_slot_id else None
        zone = self.db.get(Zone, slot.zone_id) if slot else None
        coverage_end = session.monthly_coverage_end
        if coverage_end is None and session.monthly_pass_id is not None:
            coverage_end = self.db.get(MonthlyPass, session.monthly_pass_id).end_date
        return {
            "quote_token": token, "session_id": session.id, "license_plate": vehicle.license_plate,
            "check_in_time": _aware(session.check_in_time), "quoted_at": _aware(at), "expires_at": expires,
            "duration_minutes": int((at - session.check_in_time).total_seconds() / 60),
            "parking_fee": fee, "monthly_coverage_end": coverage_end,
            "slot_name": slot.slot_name if slot else None, "zone_name": zone.name if zone else None,
        }

    @staticmethod
    def _replay(session, claims, confirmation, actor_id):
        digest = hashlib.sha256(confirmation.quote_token.encode()).hexdigest()
        if (session.checkout_quote_hash is None
                or not hmac.compare_digest(session.checkout_quote_hash, digest)
                or session.staff_out_id != actor_id or session.parking_fee != claims["fee"]
                or session.checkout_payment_method != confirmation.payment_method):
            raise _error("checkout_confirmation_conflict", "Lượt đã kết thúc với xác nhận khác. Hãy tra lịch sử xe ra.")
        return session

    def confirm(self, confirmation: CheckoutConfirmation, actor_id: int, *, session_id: str | None = None,
                license_plate: str | None = None) -> ParkingSession:
        claims = _decode(confirmation.quote_token)
        if claims["actor_id"] != actor_id or (session_id is not None and claims["session_id"] != session_id):
            raise _error("checkout_confirmation_conflict", "Phiếu xem phí không thuộc lượt gửi hoặc nhân viên này.")
        try:
            session, vehicle = self._load(claims["session_id"])
            if license_plate is not None and vehicle.license_plate != license_plate.strip().upper():
                raise _error("checkout_confirmation_conflict", "Biển số không khớp với phiếu xem phí.")
            if session.status == "completed":
                return self._replay(session, claims, confirmation, actor_id)
            if session.status != "active":
                raise _error("checkout_state_conflict", "Lượt gửi không còn đang hoạt động. Hãy tải lại.")
            if _state(session, vehicle) != claims["state"]:
                raise _error("checkout_quote_changed", "Thông tin lượt gửi đã đổi. Hãy xem lại phí trước khi xác nhận.")
            if (claims["fee"] > 0 and confirmation.payment_method is None) or (claims["fee"] == 0 and confirmation.payment_method is not None):
                raise _error("checkout_payment_method_invalid", "Lượt có phí cần phương thức thu; lượt miễn phí phải để trống phương thức.", 422)
            # Serialize the cashier before staff_out_id acquires a foreign-key
            # lock; otherwise different sessions can deadlock on a lock upgrade.
            lock_cash_operator(self.db, actor_id)
            if not session_crud.claim_session_for_checkout(self.db, session.id):
                self.db.rollback()
                winner, _ = self._load(claims["session_id"])
                if winner.status == "completed":
                    return self._replay(winner, claims, confirmation, actor_id)
                raise _error("checkout_state_conflict", "Lượt gửi vừa được xử lý. Hãy tải lại.")
            at = session_crud.server_now()
            if not datetime.fromisoformat(claims["quoted_at"]) <= _aware(at) < datetime.fromisoformat(claims["expires_at"]):
                raise _error("checkout_quote_expired", "Phiếu xem phí đã hết hạn. Hãy xem lại phí trước khi xác nhận.")
            rate = self._rate(vehicle.vehicle_type_id, at, lock=True)
            fee = self._fee(session, vehicle, at)
            if rate != claims["rate"] or fee != claims["fee"]:
                raise _error("checkout_quote_changed", "Phí gửi xe đã đổi. Hãy xem lại phí trước khi xác nhận.")
            session.check_out_time = at
            session.parking_fee = fee
            session.status = "completed"
            session.staff_out_id = actor_id
            session.checkout_quote_hash = hashlib.sha256(confirmation.quote_token.encode()).hexdigest()
            session.checkout_payment_method = confirmation.payment_method
            slot = self.db.get(ParkingSlot, session.parking_slot_id) if session.parking_slot_id else None
            if slot is not None:
                slot.is_occupied = False
            self.db.flush()
            if fee > 0:
                PaymentService.record_receipt(self.db, "parking_session", session.id, fee, actor_id,
                                              method=confirmation.payment_method, created_at=at)
            self.db.commit()
            self.db.refresh(session)
            return session
        except HTTPException:
            self.db.rollback()
            raise
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise _error("checkout_failed", "Lỗi hệ thống khi xác nhận xe ra. Có thể thử lại cùng xác nhận.", 500) from exc
