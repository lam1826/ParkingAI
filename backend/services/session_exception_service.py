"""Manager-approved parking exceptions; no mutation of receipts or admission identity."""
from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from core.clock import BUSINESS_TZ
from crud import parking_session as session_crud
from expansion.portal_models import PortalSessionGrant, PortalVehicleOwnership
from expansion.reservations import lock_slot
from expansion.site_models import FleetVehicle, GuaranteedAllocation, ParkingReservation
from expansion.site_scope import require_site_access
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.parking_session_event import ParkingSessionEvent
from models.payment import Payment
from models.vehicle import Vehicle
from models.parking_slot import ParkingSlot
from models.zone import Zone
from services.auth_service import check_permission
from services.payment_service import lock_cash_operator


BILLING_FIELDS = ("billing_policy_version", "rate_config_id", "rate_ticket_type", "rate_unit_price", "rate_effective_date")


def _time(value):
    return value.replace(tzinfo=BUSINESS_TZ).isoformat() if value is not None else None


def _snapshot(session, vehicle):
    return {"session_id": session.id, "status": session.status, "vehicle_id": session.vehicle_id,
            "license_plate": vehicle.license_plate, "parking_slot_id": session.parking_slot_id,
            "check_in_time": _time(session.check_in_time), "check_out_time": _time(session.check_out_time),
            "parking_fee": session.parking_fee}


def _event(row):
    return {"id": row.id, "session_id": row.session_id, "action": row.action, "reason": row.reason,
            "actor_id": row.actor_id, "actor_username": row.actor_username, "created_at": _time(row.created_at),
            "before_state": row.before_state, "after_state": row.after_state,
            "replacement_session_id": row.replacement_session_id}


class SessionExceptionService:
    def __init__(self, db):
        self.db = db

    def _authorize(self, actor, site_id, *, manage=False):
        if site_id is None:
            # Only legacy routers may call this branch; their workspace guard
            # prevents unscoped access once more than one lot exists.
            check_permission(actor, "manager" if manage else "staff")
        else:
            require_site_access(self.db, actor, site_id, "manager" if manage else "staff")

    def _load(self, session_id, site_id):
        query = select(ParkingSession).where(ParkingSession.id == session_id)
        if site_id is not None:
            query = query.join(ParkingSlot).join(Zone).where(Zone.site_id == site_id)
        session = self.db.scalar(query.execution_options(populate_existing=True))
        if session is None:
            raise HTTPException(404, "Không tìm thấy lượt gửi tại bãi.")
        return session

    def _actual_site(self, session):
        return self.db.scalar(select(Zone.site_id).join(ParkingSlot).where(ParkingSlot.id == session.parking_slot_id))

    def _cancel_block(self, session):
        if session.status != "active":
            return "Chỉ hủy lượt đang gửi; lượt đã trả xe phải xử lý qua chứng từ hoặc hoàn tiền."
        if self.db.scalar(select(Payment.id).where(Payment.source_type == "parking_session", Payment.source_id == session.id).limit(1)):
            return "Lượt đã có chứng từ. Hãy sử dụng quy trình hoàn tiền, không hủy lượt."
        from expansion.session_payment_models import SessionFeeCredit, SessionFeeQuote
        from expansion.online_payment_models import OnlinePaymentLink, OnlinePaymentInbox, OnlinePaymentProcessing
        if self.db.scalar(select(SessionFeeCredit.id).where(SessionFeeCredit.session_id == session.id).limit(1)):
            return "Lượt đã ghi nhận tiền online; hãy xác nhận trả xe và xử lý hoàn tiền qua chứng từ nếu cần."
        unresolved = select(OnlinePaymentInbox.id).join(OnlinePaymentProcessing,
            OnlinePaymentProcessing.id == OnlinePaymentInbox.id).where(
            OnlinePaymentInbox.link_id == OnlinePaymentLink.id, OnlinePaymentProcessing.status == "received").exists()
        if self.db.scalar(select(OnlinePaymentLink.id).join(SessionFeeQuote,
            SessionFeeQuote.id == OnlinePaymentLink.session_quote_id).where(SessionFeeQuote.session_id == session.id,
            OnlinePaymentLink.state.in_(["creating", "unknown", "ready", "review"]) | unresolved).limit(1)):
            return "Lượt còn thanh toán online chờ xác minh; hãy kiểm tra hoặc hủy liên kết thanh toán trước khi xử lý lượt."
        if session.timed_pass_id is not None or session.monthly_pass_id is not None or self.db.get(PortalSessionGrant, session.id) is not None:
            return "Lượt gắn quyền vé tháng hoặc hồ sơ khách đã xác minh; hãy xử lý qua quy trình trả xe."
        if self.db.scalar(select(ParkingReservation.id).where(ParkingReservation.session_id == session.id).limit(1)):
            return "Lượt đã xác nhận đến theo đặt chỗ; hãy xử lý qua quy trình đặt chỗ hoặc trả xe."
        from expansion.simplified_customer_models import DeclaredParkingReservation
        if self.db.scalar(select(DeclaredParkingReservation.id).where(DeclaredParkingReservation.session_id == session.id).limit(1)):
            return 'Lượt đã nhận theo đặt trước của khách; hãy xử lý qua quy trình trả xe.'
        if self.db.scalar(select(GuaranteedAllocation.id).where(
            GuaranteedAllocation.slot_id == session.parking_slot_id,
            GuaranteedAllocation.status == "active", GuaranteedAllocation.end_at > session.check_in_time,
        ).limit(1)):
            return "Vị trí còn cam kết giữ chỗ; hãy xử lý quyền giữ chỗ trước khi hủy lượt."
        return None

    def _vehicle_bound(self, vehicle):
        if vehicle.customer_id is not None:
            return True
        from expansion.simplified_customer_models import DeclaredParkingReservation
        from core.vehicle_identity import canonical_identity
        if self.db.scalar(select(DeclaredParkingReservation.id).where(
            DeclaredParkingReservation.normalized_plate == canonical_identity(vehicle.license_plate)).limit(1)):
            return True
        return any(self.db.scalar(select(model.id).where(model.vehicle_id == vehicle.id).limit(1)) is not None
                   for model in (MonthlyPass, PortalVehicleOwnership, FleetVehicle, ParkingReservation, GuaranteedAllocation))

    def _correction_block(self, session):
        blocked = self._cancel_block(session)
        if blocked:
            return blocked
        if getattr(session, "billing_policy_version", None) != "entry-v1":
            return "Lượt cũ chưa có căn cứ giá đã chốt; không thể tự tạo lại lịch sử giá để điều chỉnh biển."
        if self._vehicle_bound(self.db.get(Vehicle, session.vehicle_id)):
            return "Điều chỉnh biển chỉ áp dụng xe vãng lai chưa gắn khách, vé tháng, nhóm xe hoặc đặt chỗ."
        return None

    def detail(self, actor, site_id, session_id):
        self._authorize(actor, site_id)
        session = self._load(session_id, site_id)
        try:
            self._authorize(actor, site_id, manage=True)
            can_manage = True
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
            can_manage = False
        manager_reason = "Thao tác ngoại lệ cần quản lý xác nhận."
        cancel_reason = self._cancel_block(session) if can_manage else manager_reason
        lost_reason = (None if session.status == "active" else "Chỉ xác nhận mất vé cho lượt đang gửi.") if can_manage else manager_reason
        correction_reason = self._correction_block(session) if can_manage else manager_reason
        rows = self.db.scalars(select(ParkingSessionEvent).where(or_(
            ParkingSessionEvent.session_id == session.id, ParkingSessionEvent.replacement_session_id == session.id,
        )).order_by(ParkingSessionEvent.created_at.desc(), ParkingSessionEvent.id.desc()).limit(100))
        return {"session_id": session.id, "status": session.status, "events": [_event(row) for row in rows],
                "eligibility": {"cancel": {"allowed": cancel_reason is None, "reason": cancel_reason},
                                "lost_ticket": {"allowed": lost_reason is None, "reason": lost_reason},
                                "correct_plate": {"allowed": correction_reason is None, "reason": correction_reason}}}

    def _response(self, session, event):
        return {"session_id": session.id, "status": session.status, "event": _event(event),
                "next_action": "checkout" if event.action == "lost_ticket" and session.status == "active" else "print_replacement_ticket" if event.action == "plate_corrected" else "none",
                "replacement_session_id": event.replacement_session_id}

    def apply(self, actor, site_id, session_id, body, action):
        if action not in {"cancelled", "lost_ticket", "plate_corrected"}:
            raise ValueError("Unsupported session exception")
        try:
            self._authorize(actor, site_id, manage=True)
            # Same actor-before-session ordering as checkout and cash shifts.
            # All evidence, occupancy changes and replacement writes commit once.
            lock_cash_operator(self.db, actor.id)
            self.db.refresh(actor)
            self.db.refresh(actor, ["role"])
            self._authorize(actor, site_id, manage=True)
            session = self._load(session_id, site_id)
            existing = self.db.scalar(select(ParkingSessionEvent).where(
                ParkingSessionEvent.session_id == session.id, ParkingSessionEvent.request_id == body.request_id))
            if existing is not None:
                if (existing.action != action or existing.reason != body.reason or existing.actor_id != actor.id
                        or (action == "plate_corrected" and existing.after_state.get("license_plate") != body.license_plate)):
                    raise HTTPException(409, "Mã yêu cầu đã dùng cho nội dung hoặc người xác nhận khác.")
                result = self._response(session, existing)
                self.db.commit()
                return result
            vehicle = self.db.get(Vehicle, session.vehicle_id)
            if self.db.get_bind().dialect.name == "sqlite":
                self.db.execute(update(ParkingSession).where(ParkingSession.id == session.id).values(updated_at=ParkingSession.updated_at))
            self.db.scalar(select(ParkingSession.id).where(ParkingSession.id == session.id).with_for_update())
            self.db.refresh(session)
            if session.status != "active":
                raise HTTPException(409, "Lượt không còn đang gửi. Hãy tải lại trước khi xử lý ngoại lệ.")
            replacement_vehicle = self._prepare_corrected_vehicle(vehicle, body.license_plate) if action == "plate_corrected" else None
            self.db.refresh(vehicle)
            before = _snapshot(session, vehicle)
            replacement = None
            if action == 'lost_ticket':
                from expansion.ticket_payment_access import revoke_ticket_payment_access
                revoke_ticket_payment_access(self.db, session.id)
            if action != "lost_ticket":
                slot = lock_slot(self.db, session.parking_slot_id) if session.parking_slot_id is not None else None
                reason = self._correction_block(session) if action == "plate_corrected" else self._cancel_block(session)
                if reason:
                    raise HTTPException(409, reason)
                if slot is not None and not slot.is_occupied:
                    raise HTTPException(409, "Trạng thái vị trí không khớp lượt gửi; cần kiểm tra trước khi hủy.")
                session.status = "cancelled"
                self.db.flush()
                if action == "plate_corrected":
                    replacement = self._replacement(session, replacement_vehicle)
                elif slot is not None:
                    slot.is_occupied = False
                self.db.flush()
            after = _snapshot(replacement, replacement_vehicle) if replacement is not None else _snapshot(session, vehicle)
            record = ParkingSessionEvent(session_id=session.id, site_id=self._actual_site(session), action=action,
                reason=body.reason, request_id=body.request_id, actor_id=actor.id, actor_username=actor.username,
                created_at=session_crud.server_now(), before_state=before, after_state=after,
                replacement_session_id=replacement.id if replacement else None)
            self.db.add(record)
            self.db.flush()
            result = self._response(session, record)
            self.db.commit()
            return result
        except HTTPException:
            self.db.rollback()
            raise
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise HTTPException(409, "Dữ liệu vừa thay đổi hoặc không thể ghi lịch sử. Hãy tải lại và thử lại cùng mã yêu cầu.") from exc

    def _prepare_corrected_vehicle(self, original, plate):
        if plate == original.license_plate:
            raise HTTPException(422, "Biển số mới phải khác biển số đã ghi nhận.")
        # The source session is already owned, as in checkout (whose PostgreSQL
        # UPDATE trigger then locks the vehicle). Lock both vehicle identities
        # in a fixed order before touching the slot. Never rewrite old plates.
        target = self.db.scalar(select(Vehicle).where(Vehicle.license_plate == plate))
        ids = sorted({original.id, target.id} if target else {original.id})
        self.db.execute(select(Vehicle.id).where(Vehicle.id.in_(ids)).order_by(Vehicle.id).with_for_update(key_share=True)).all()
        self.db.refresh(original)
        if self._vehicle_bound(original):
            raise HTTPException(409, "Xe đã có liên kết nghiệp vụ; không thể điều chỉnh bằng lượt thay thế.")
        if target is not None:
            self.db.refresh(target)
            if target.vehicle_type_id != original.vehicle_type_id or self._vehicle_bound(target):
                raise HTTPException(409, "Biển số đích khác loại xe hoặc đã gắn khách, vé tháng, nhóm xe hay đặt chỗ.")
            if self.db.scalar(select(ParkingSession.id).where(ParkingSession.vehicle_id == target.id,
                                                              ParkingSession.status.in_(["active", "checking_out"])).limit(1)):
                raise HTTPException(409, "Biển số đích đang có lượt gửi xe.")
        else:
            target = Vehicle(license_plate=plate, vehicle_type_id=original.vehicle_type_id)
            self.db.add(target)
            self.db.flush()
        return target

    def _replacement(self, original, vehicle):
        replacement = ParkingSession(vehicle_id=vehicle.id, parking_slot_id=original.parking_slot_id,
            monthly_pass_id=None, monthly_coverage_end=None, check_in_time=original.check_in_time,
            image_in_url=original.image_in_url, status="active", staff_in_id=original.staff_in_id,
            **{field: getattr(original, field) for field in BILLING_FIELDS})
        self.db.add(replacement)
        self.db.flush()
        return replacement
