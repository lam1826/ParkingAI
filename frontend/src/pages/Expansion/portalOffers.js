import { bookingTimestamp } from "./siteForms.js";

const kinds = new Set(["monthly", "hourly", "daily"]);
export const productKind = (row) => row?.product_kind || "monthly";
export const productLabel = (row) => ({ monthly: "Vé tháng", hourly: "Vé giờ", daily: "Vé ngày" })[productKind(row)] || "Gói vé";
export function productDuration(row) {
  const kind = productKind(row);
  if (kind === "monthly") return `${row.duration_days} ngày`;
  if (kind === "daily") return "24 giờ";
  const minutes = Number(row.duration_minutes);
  return Number.isSafeInteger(minutes) && minutes > 0 ? (minutes % 60 === 0 ? `${minutes / 60} giờ` : `${minutes} phút`) : "Chưa có thời lượng";
}
export function matchingPlans(plans, vehicle, kind) {
  return plans.filter((plan) => kinds.has(productKind(plan)) && plan.is_active !== false
    && (!kind || productKind(plan) === kind) && vehicle && Number(plan.vehicle_type_id) === Number(vehicle.vehicle_type_id));
}
const positiveId = (value) => Number.isSafeInteger(Number(value)) && Number(value) > 0;

// The server chooses the amount, end time, reservation and entitlement. The
// browser submits only a catalog selection and the requested arrival window.
export function portalOrderBody(form, plans, vehicles, paymentMode, key) {
  const vehicle = vehicles.find((row) => String(row.id) === String(form.vehicle_id));
  const plan = matchingPlans(plans, vehicle).find((row) => String(row.id) === String(form.plan_id));
  if (!vehicle || !plan || !positiveId(vehicle.id) || !positiveId(plan.id)) throw new Error("Chọn xe đã xác minh và gói vé phù hợp với loại xe.");
  if (!["demo", "manual", "payos"].includes(paymentMode) || (paymentMode === "payos" && !plan.payment_modes?.includes("payos"))) throw new Error("Chưa có hình thức thanh toán phù hợp.");
  const body = { plan_id: Number(plan.id), vehicle_id: Number(vehicle.id), idempotency_key: key, payment_mode: paymentMode };
  if (productKind(plan) !== "monthly") {
    if (!plan.eligible_zones?.length) throw new Error("Gói này chưa có khu vực đang phục vụ. Chọn gói khác hoặc làm mới danh sách.");
    body.start_at = bookingTimestamp(form.start_at);
    if (form.zone_id) {
      if (!positiveId(form.zone_id) || !plan.eligible_zones.some((zone) => String(zone.id) === String(form.zone_id))) throw new Error("Khu vực đã chọn không còn phù hợp với gói vé.");
      body.zone_id = Number(form.zone_id);
    }
  }
  return body;
}

export function portalPlanBody(form, { editing = false, siteId } = {}) {
  const kind = productKind(form);
  if (!kinds.has(kind)) throw new Error("Chọn loại gói vé hợp lệ.");
  const body = { name: form.name.trim(), price: Number(form.price) };
  if (!body.name || !Number.isSafeInteger(body.price) || body.price <= 0) throw new Error("Nhập tên và giá gói là số đồng nguyên lớn hơn 0.");
  if (kind === "monthly") {
    body.duration_days = Number(form.duration_days);
    if (!Number.isSafeInteger(body.duration_days) || body.duration_days < 1 || body.duration_days > 366) throw new Error("Vé tháng cần từ 1 đến 366 ngày hiệu lực.");
  } else if (kind === "hourly") {
    body.duration_minutes = Number(form.duration_minutes);
    if (!Number.isSafeInteger(body.duration_minutes) || body.duration_minutes < 60 || body.duration_minutes > 1440 || body.duration_minutes % 60 !== 0) throw new Error("Vé giờ cần từ 60 đến 1.440 phút, theo bước 60 phút.");
  }
  if (!editing) {
    if (!positiveId(siteId) || !positiveId(form.vehicle_type_id)) throw new Error("Chọn bãi và loại xe áp dụng.");
    Object.assign(body, { product_kind: kind, site_id: Number(siteId), vehicle_type_id: Number(form.vehicle_type_id) });
    if (kind === "daily") body.duration_minutes = 1440;
  }
  return body;
}

export function ownerCan(order, action) {
  return Array.isArray(order?.allowed_actions) && order.allowed_actions.includes(action);
}

export const entitlementLabel = (status) => ({ ready: "Sẵn sàng trong khung giờ", active: "Chưa sử dụng", pending: "Chờ cấp quyền", used: "Đã sử dụng", arrived: "Xe đã vào bãi", consumed: "Đã sử dụng", expired: "Hết hiệu lực", no_show: "Không đến trong hạn", revoked: "Đã thu hồi", cancelled: "Đã hủy", refunded: "Đã hoàn", upcoming: "Chưa đến giờ", completed: "Đã kết thúc" })[status] || status || "Chưa cấp quyền";
export const orderStatusLabel = (status) => ({ paid: "Đã nhận thanh toán", refunded: "Đã ghi nhận hoàn" })[status];

// server_now anchors the display; reaching zero asks for a fresh server state,
// never marks a payment or reservation expired in the browser.
export function holdRemaining(order, elapsedMilliseconds = 0) {
  const end = Date.parse(order?.hold_expires_at), now = Date.parse(order?.server_now);
  if (!Number.isFinite(end) || !Number.isFinite(now)) return null;
  return Math.max(0, Math.ceil((end - now - Math.max(0, elapsedMilliseconds)) / 1000));
}
