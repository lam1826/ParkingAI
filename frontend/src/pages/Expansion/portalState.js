export function mergeSelectedOrder(detail, rows = []) {
  if (!detail) return null;
  // A failed list request has null data; the separately fetched detail remains valid.
  const listed = rows?.find((row) => row.id === detail.id);
  // A refreshed list intentionally excludes the private QR; keep it from detail.
  // A response to a mutation can arrive before the list is refreshed.
  const listedTime = Date.parse(listed?.server_now), detailTime = Date.parse(detail.server_now);
  const olderList = Number.isFinite(listedTime) && Number.isFinite(detailTime) && listedTime < detailTime;
  const merged = olderList || (listed?.status === "pending" && detail.status !== "pending")
    ? { ...listed, ...detail } : { ...detail, ...listed };
  if (merged.status !== "pending") {
    delete merged.demo_qr_svg;
    delete merged.demo_payload;
    delete merged.demo_token;
  }
  return merged;
}

export function passStatus(period, today) {
  if (!period.is_active) return "Ngừng áp dụng";
  if (period.end_date < today) return "Hết hạn";
  if (period.start_date > today) return "Chưa tới kỳ";
  return "Đang hiệu lực";
}

export function newOrderDraft(previous, createKey) {
  return { ...previous, idempotency_key: createKey() };
}

// Portal admin: actions are offered only where the account is a manager (or global
// admin). A manager whose membership at a site is "staff" gets 403 on every action.
export function managedSiteList(sites) {
  return (Array.isArray(sites) ? sites : []).filter((site) => ["manager", "admin"].includes(site?.role));
}

export function canManageSite(sites, siteId) {
  return siteId !== null && siteId !== undefined && siteId !== ""
    && managedSiteList(sites).some((site) => String(site.id) === String(siteId));
}

// The server decides which review decisions can succeed (an hourly/daily DEMO order
// in review has lost its slot hold and can only be rejected).
export function orderReviewActions(row) {
  return Array.isArray(row?.review_actions) ? row.review_actions.filter((action) => ["approve", "reject"].includes(action)) : [];
}

// Every pending order has a payment deadline: the slot hold for hourly/daily orders,
// the order window for monthly orders. Counter collection is refused after it.
export function paymentDeadline(order) {
  if (order?.status !== "pending") return null;
  const value = order.hold_expires_at || order.payment_deadline;
  return Number.isFinite(Date.parse(value)) ? value : null;
}

// server_now anchors the countdown; zero asks for a fresh server state.
export function paymentRemaining(order, elapsedMilliseconds = 0) {
  const end = Date.parse(paymentDeadline(order)), now = Date.parse(order?.server_now);
  if (!Number.isFinite(end) || !Number.isFinite(now)) return null;
  return Math.max(0, Math.ceil((end - now - Math.max(0, elapsedMilliseconds)) / 1000));
}

export function counterInstruction(order, formatTime) {
  const deadline = paymentDeadline(order);
  const timed = (order?.product_kind || "monthly") !== "monthly";
  const when = deadline ? `trước ${formatTime(deadline)}` : "trước hạn thanh toán trên đơn";
  return timed
    ? `Mang mã đơn đến quầy và thanh toán ${when} (hạn giữ chỗ). Quá hạn này chỗ giữ được trả lại và đơn hết hiệu lực. Chỉ trạng thái máy chủ xác nhận mới cấp quyền sử dụng.`
    : `Mang mã đơn đến quầy và thanh toán ${when}. Quá hạn này đơn tự hết hiệu lực; khi đó hãy tạo đơn mới (có thể tạo tại quầy). Chỉ trạng thái máy chủ xác nhận mới cấp quyền sử dụng.`;
}

export function monthlyPaymentNotice(plan, paymentMode) {
  const minutes = Number(plan?.payment_window_minutes);
  if ((plan?.product_kind || "monthly") !== "monthly" || !Number.isSafeInteger(minutes) || minutes <= 0) return "";
  return `Sau khi tạo đơn, bạn có ${minutes} phút để thanh toán${paymentMode === "manual" ? " tại quầy" : ""}; quá hạn đơn tự hết hiệu lực và cần tạo đơn mới.`;
}

// #54: what happens to the manager's decision note. Link/vehicle notes reach the
// customer in a notification; a rejected link requester has no customer profile, so
// that reason cannot be delivered or stored and is optional. Order reviews store it.
export function decisionNoteField(kind, approve) {
  if (kind === "vehicle-requests") {
    return approve
      ? { required: false, label: "Ghi chú xác minh (không bắt buộc)", help: "Nội dung được gửi trong thông báo cho khách." }
      : { required: true, label: "Lý do từ chối", help: "Lý do được gửi trong thông báo cho khách." };
  }
  if (kind === "link-requests") {
    return approve
      ? { required: false, label: "Ghi chú xác minh (không bắt buộc)", help: "Nội dung được gửi trong thông báo cho khách sau khi liên kết." }
      : { required: false, label: "Lý do từ chối (không bắt buộc)", help: "Người gửi chưa có hồ sơ nên chỉ thấy trạng thái bị từ chối; lý do không được lưu. Hãy báo lý do trực tiếp cho khách nếu cần." };
  }
  return { required: true, label: "Ghi chú xác minh / lý do xử lý", help: "" };
}
