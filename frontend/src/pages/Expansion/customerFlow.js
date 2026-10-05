import { bookingTimestamp } from "./siteForms.js";
import { validSessionBalance } from "./sessionFeeState.js";

const positive = (value) => Number.isSafeInteger(Number(value)) && Number(value) > 0;
export function feeLookupBody(form, siteId) {
  const plate = String(form.license_plate || "").trim().toUpperCase();
  if (!positive(siteId) || !positive(form.vehicle_type_id) || !plate || plate.length > 20) throw new Error("Nhập biển số hoặc mã xe và chọn loại xe phù hợp.");
  const proof = String(form.ticket_proof || "").trim();
  if (proof.length > 160) throw new Error("Mã thanh toán riêng không hợp lệ.");
  return { site_id: Number(siteId), license_plate: plate, vehicle_type_id: Number(form.vehicle_type_id), ...(proof ? { ticket_proof: proof } : {}) };
}

// A car parked at this site is in one of its active slots (slots and zones cannot
// be stopped while occupied), so the fee lookup offers only the active catalog types
// the site's inventory serves (review 05/10 #78). `availability` is the useRemote
// result of /sites/{id}/availability: while it loads nothing is offered; if it
// failed, every active type stays selectable and the server validates the choice.
export function feeLookupTypes(types, availability) {
  const active = (types || []).filter((row) => row.is_active !== false);
  const slots = availability?.data?.slots;
  if (Array.isArray(slots)) {
    const served = new Set(slots.map((slot) => Number(slot.vehicle_type_id)));
    return active.filter((row) => served.has(Number(row.id)));
  }
  return availability?.error ? active : [];
}

export function validFeeLookup(data) {
  return typeof data?.session?.id === "string" && data.session.status === "active"
    && typeof data.session.license_plate === "string" && Number.isFinite(Date.parse(data.session.check_in_time))
    && ["owned", "ticket"].includes(data?.access?.kind)
    && validSessionBalance(data.payment_status, data.session.id);
}

export function refreshFeeLookup(result, paymentStatus) {
  const session = result?.session;
  if (!session || !["active", "completed", "cancelled"].includes(paymentStatus?.session_status)
      || !validSessionBalance(paymentStatus, session.id)) return null;
  // A finished stay is immutable. A late or inconsistent response must not
  // reopen payment actions after a completed/cancelled result was observed.
  if (session.status !== "active" && session.status !== paymentStatus.session_status) return null;
  return { ...result, session: { ...session, status: paymentStatus.session_status }, payment_status: paymentStatus };
}

export function advanceBookingBody(form, siteId, types, requestId) {
  const type = types.find((item) => Number(item.id) === Number(form.vehicle_type_id));
  const plate = String(form.license_plate || "").trim().toUpperCase();
  if (!positive(siteId) || !type || type.is_active === false) throw new Error("Chọn loại xe được phục vụ tại bãi.");
  if ((type.requires_plate !== false && !plate) || plate.length > 20) throw new Error("Hãy nhập biển số hợp lệ, tối đa 20 ký tự.");
  const start = bookingTimestamp(form.start_at), end = bookingTimestamp(form.end_at);
  if (Date.parse(end) <= Date.parse(start)) throw new Error("Giờ đi phải sau giờ đến.");
  return { site_id: Number(siteId), license_plate: plate, vehicle_type_id: Number(type.id), start_at: start, end_at: end, request_id: requestId };
}

export function uncertainMutation(error) {
  const status = error?.response?.status;
  return !(status >= 400 && status < 500 && ![408, 429].includes(status));
}

export function portalTab(params) {
  if (params.get("order") || params.get("tab") === "purchase") return 2;
  if (params.get("tab") === "support") return 5;
  if (["vehicles", "profile"].includes(params.get("tab"))) return 0;
  if (params.get("tab") === "notifications") return 4;
  return { profile: 0, passes: 1, purchase: 2, history: 3, notifications: 4 }[params.get("view")] ?? 1;
}

// Online payment is offered only when the server says payOS is enabled for this lot
// and the stay is billed on an immutable tariff; otherwise show the server's
// pay-at-the-counter guidance instead of a dead-end online button.
export function feePaymentChoice(balance) {
  const online = balance?.enabled === true && balance.supported !== false;
  return { online, message: online ? "" : (balance?.message || "Thanh toán online chưa khả dụng; vui lòng thanh toán tại bãi khi lấy xe.") };
}
