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

export function validFeeLookup(data) {
  return typeof data?.session?.id === "string" && data.session.status === "active"
    && typeof data.session.license_plate === "string" && Number.isFinite(Date.parse(data.session.check_in_time))
    && ["owned", "ticket"].includes(data?.access?.kind)
    && validSessionBalance(data.payment_status, data.session.id);
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
