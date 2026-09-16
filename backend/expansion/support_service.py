"""Customer support threads: ownership-checked links, site-scoped manager replies.

Public write functions own commit/rollback. A customer may only attach their
own order/session/receipt/refund request; managers only see requests of
sites they manage. Status: ``open`` (customer waits), ``answered`` (manager
replied), ``closed``. Notifications reuse the portal notification table.
"""
from fastapi import HTTPException
from sqlalchemy import select

from core.clock import BUSINESS_TZ, business_now
from expansion import customer_ownership as ownership
from expansion.portal_service import _locked, _notify, get_linked_customer
from expansion.site_models import ParkingSite
from expansion.site_scope import allowed_site_ids, require_site_access
from expansion.support_models import CustomerSupportMessage, CustomerSupportRequest, PaymentRefundRequest
from models.customer import Customer
from models.parking_slot import ParkingSlot
from models.user import User
from models.zone import Zone


def _aware(value):
    return value.replace(tzinfo=BUSINESS_TZ) if value is not None and value.tzinfo is None else value


def _resolve_link(db, user, customer, linked_type, linked_id):
    """Return the site owning the linked resource; 404 when it is not the customer's."""
    if linked_type == "order":
        order = ownership.owned_order(db, user, customer, linked_id)
        if order is None:
            raise HTTPException(404, "Không tìm thấy đơn vé của bạn để liên kết.")
        return order.site_id
    if linked_type == "session":
        session = ownership.owned_session(db, customer, linked_id)
        if session is None:
            raise HTTPException(404, "Không tìm thấy lượt gửi của bạn để liên kết.")
        if session.parking_slot_id is None:
            return None
        return db.scalar(select(Zone.site_id).join(ParkingSlot, ParkingSlot.zone_id == Zone.id)
            .where(ParkingSlot.id == session.parking_slot_id))
    if linked_type == "receipt":
        receipt = ownership.owned_receipt(db, user, customer, linked_id)
        if receipt is None:
            raise HTTPException(404, "Không tìm thấy chứng từ của bạn để liên kết.")
        return receipt.site_id
    if linked_type == "refund_request":
        item = db.scalar(select(PaymentRefundRequest).where(PaymentRefundRequest.id == linked_id,
            PaymentRefundRequest.customer_id == customer.id))
        if item is None:
            raise HTTPException(404, "Không tìm thấy yêu cầu hoàn của bạn để liên kết.")
        return item.site_id
    raise HTTPException(422, "Loại tài nguyên liên kết không hợp lệ.")


def _choose_site(db, requested_site_id, linked_site_id):
    if requested_site_id is not None:
        site = db.get(ParkingSite, requested_site_id)
        if site is None or not site.is_active:
            raise HTTPException(404, "Không tìm thấy bãi đang hoạt động.")
        if linked_site_id is not None and linked_site_id != site.id:
            raise HTTPException(409, "Tài nguyên liên kết thuộc bãi khác với bãi đã chọn.")
        return site.id
    if linked_site_id is not None:
        return linked_site_id
    sites = list(db.scalars(select(ParkingSite.id).where(ParkingSite.is_active.is_(True)).limit(2)))
    if len(sites) != 1:
        raise HTTPException(422, "Hãy chọn bãi xe cần hỗ trợ.")
    return sites[0]


def create_request(db, user, data):
    customer = get_linked_customer(db, user)
    linked_site = _resolve_link(db, user, customer, data.linked_type, data.linked_id) if data.linked_type else None
    site_id = _choose_site(db, data.site_id, linked_site)
    now = business_now()
    item = CustomerSupportRequest(site_id=site_id, customer_id=customer.id, user_id=user.id, subject=data.subject,
        category=data.category, linked_type=data.linked_type, linked_id=data.linked_id,
        created_at=now, updated_at=now, last_message_at=now)
    db.add(item)
    db.flush()
    db.add(CustomerSupportMessage(request_id=item.id, author_id=user.id, author_role="customer", body=data.message, created_at=now))
    db.commit()
    return item


def _owned_request(db, user, identity):
    customer = get_linked_customer(db, user)
    item = db.scalar(select(CustomerSupportRequest).where(CustomerSupportRequest.id == identity,
        CustomerSupportRequest.customer_id == customer.id))
    if item is None:
        raise HTTPException(404, "Không tìm thấy yêu cầu hỗ trợ của bạn.")
    return item


def customer_reply(db, user, identity, body):
    _owned_request(db, user, identity)
    item = _locked(db, CustomerSupportRequest, identity)
    if item.status == "closed":
        raise HTTPException(409, "Yêu cầu đã đóng; hãy tạo yêu cầu mới nếu cần hỗ trợ tiếp.")
    now = business_now()
    db.add(CustomerSupportMessage(request_id=item.id, author_id=user.id, author_role="customer", body=body, created_at=now))
    item.status, item.updated_at, item.last_message_at = "open", now, now
    db.commit()
    return item


def customer_close(db, user, identity):
    _owned_request(db, user, identity)
    item = _locked(db, CustomerSupportRequest, identity)
    if item.status != "closed":
        now = business_now()
        item.status, item.closed_at, item.closed_by_id, item.updated_at = "closed", now, user.id, now
    db.commit()
    return item


def _managed_request(db, actor, site_id, identity):
    require_site_access(db, actor, site_id, "manager")
    item = db.scalar(select(CustomerSupportRequest).where(CustomerSupportRequest.id == identity,
        CustomerSupportRequest.site_id == site_id))
    if item is None:
        raise HTTPException(404, "Không tìm thấy yêu cầu hỗ trợ tại bãi này.")
    return item


def manager_reply(db, actor, site_id, identity, body):
    _managed_request(db, actor, site_id, identity)
    item = _locked(db, CustomerSupportRequest, identity)
    if item.status == "closed":
        raise HTTPException(409, "Yêu cầu đã đóng; mở lại trước khi phản hồi.")
    now = business_now()
    message = CustomerSupportMessage(request_id=item.id, author_id=actor.id, author_role=actor.role.name, body=body, created_at=now)
    db.add(message)
    db.flush()
    item.status, item.updated_at, item.last_message_at = "answered", now, now
    _notify(db, item.customer_id, f"support:{item.id}:reply:{message.id}",
        f"Yêu cầu hỗ trợ \"{item.subject[:60]}\" đã có phản hồi từ quản lý.")
    db.commit()
    return item


def manager_close(db, actor, site_id, identity, note=""):
    _managed_request(db, actor, site_id, identity)
    item = _locked(db, CustomerSupportRequest, identity)
    if item.status == "closed":
        db.commit()
        return item
    now = business_now()
    if note.strip():
        db.add(CustomerSupportMessage(request_id=item.id, author_id=actor.id, author_role=actor.role.name, body=note.strip(), created_at=now))
        item.last_message_at = now
    item.status, item.closed_at, item.closed_by_id, item.updated_at = "closed", now, actor.id, now
    _notify(db, item.customer_id, f"support:{item.id}:closed",
        f"Yêu cầu hỗ trợ \"{item.subject[:60]}\" đã được quản lý đóng.")
    db.commit()
    return item


def manager_reopen(db, actor, site_id, identity):
    _managed_request(db, actor, site_id, identity)
    item = _locked(db, CustomerSupportRequest, identity)
    if item.status == "closed":
        item.status, item.closed_at, item.closed_by_id, item.updated_at = "answered", None, None, business_now()
    db.commit()
    return item


def serialize(item, *, messages=None, customer=None, unread_for_customer=None):
    data = {"id": item.id, "site_id": item.site_id, "customer_id": item.customer_id, "subject": item.subject,
        "category": item.category, "status": item.status, "linked_type": item.linked_type, "linked_id": item.linked_id,
        "created_at": _aware(item.created_at), "updated_at": _aware(item.updated_at),
        "last_message_at": _aware(item.last_message_at), "closed_at": _aware(item.closed_at)}
    if customer is not None:
        data["customer_name"] = customer.full_name
    if messages is not None:
        data["messages"] = [{"id": row.id, "author_role": row.author_role, "body": row.body,
            "created_at": _aware(row.created_at), "mine": row.author_role == "customer"} for row in messages]
    return data


def messages_of(db, item):
    return list(db.scalars(select(CustomerSupportMessage).where(CustomerSupportMessage.request_id == item.id)
        .order_by(CustomerSupportMessage.created_at, CustomerSupportMessage.id)))


def customer_list(db, user, *, status=None, limit=50, offset=0):
    customer = get_linked_customer(db, user)
    query = select(CustomerSupportRequest).where(CustomerSupportRequest.customer_id == customer.id)
    if status:
        query = query.where(CustomerSupportRequest.status == status)
    rows = db.scalars(query.order_by(CustomerSupportRequest.last_message_at.desc(), CustomerSupportRequest.id)
        .offset(offset).limit(limit)).all()
    return [serialize(row) for row in rows]


def customer_detail(db, user, identity):
    item = _owned_request(db, user, identity)
    return serialize(item, messages=messages_of(db, item))


def manager_list(db, actor, site_id, *, status=None, category=None, limit=50, offset=0):
    require_site_access(db, actor, site_id, "manager")
    query = select(CustomerSupportRequest, Customer).join(Customer, Customer.id == CustomerSupportRequest.customer_id).where(
        CustomerSupportRequest.site_id == site_id, CustomerSupportRequest.site_id.in_(allowed_site_ids(db, actor)))
    if status:
        query = query.where(CustomerSupportRequest.status == status)
    if category:
        query = query.where(CustomerSupportRequest.category == category)
    rows = db.execute(query.order_by(CustomerSupportRequest.last_message_at.desc(), CustomerSupportRequest.id)
        .offset(offset).limit(limit)).all()
    return [serialize(item, customer=customer) for item, customer in rows]


def manager_detail(db, actor, site_id, identity):
    item = _managed_request(db, actor, site_id, identity)
    customer = db.get(Customer, item.customer_id)
    requester = db.get(User, item.user_id)
    data = serialize(item, messages=messages_of(db, item), customer=customer)
    data["requester_username"] = requester.username if requester else None
    return data
