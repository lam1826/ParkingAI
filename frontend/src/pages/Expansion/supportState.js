// Labels and small decisions for the customer support and refund screens.
export const SUPPORT_CATEGORIES = [["general", "Câu hỏi chung"], ["order", "Đơn vé / gói vé"], ["session", "Lượt gửi xe"],
  ["receipt", "Chứng từ / thanh toán"], ["refund", "Hoàn tiền"]];
export const SUPPORT_STATUS = { open: "Chờ phản hồi", answered: "Đã phản hồi", closed: "Đã đóng" };
export const REFUND_STATUS = { pending: "Đã tiếp nhận", reviewing: "Đang xem xét", approved: "Được duyệt, chờ hoàn",
  rejected: "Bị từ chối", refunded: "Đã hoàn tiền" };
export const CHANNEL_LABEL = { demo: "DEMO — mô phỏng", counter: "Thu tại quầy", online: "Chuyển khoản online", legacy: "Chứng từ lịch sử" };
export const LINK_LABEL = { order: "Đơn vé", session: "Lượt gửi", receipt: "Chứng từ", refund_request: "Yêu cầu hoàn" };

export const supportStatusLabel = (status) => SUPPORT_STATUS[status] || status || "—";
export const refundStatusLabel = (row) => (row?.demo && row?.status === "refunded" ? "Đã hoàn mô phỏng (DEMO)" : REFUND_STATUS[row?.status] || row?.status || "—");
export const channelLabel = (channel) => CHANNEL_LABEL[channel] || "Chưa xác định";
export const categoryLabel = (value) => SUPPORT_CATEGORIES.find(([key]) => key === value)?.[1] || value;

// The server's refund block is the only source of truth for the button; the
// browser only decides how to phrase it.
export function refundAction(receipt) {
  const refund = receipt?.refund;
  if (!refund || receipt.kind !== "receipt") return { kind: "none", label: "" };
  if (refund.eligible) return { kind: "request", label: `Yêu cầu hoàn ${refund.refundable_amount ? "" : ""}`.trim() };
  if (refund.open_request_id) return { kind: "open", label: "Đã có yêu cầu hoàn" };
  return { kind: "blocked", label: refund.blocked_label || "Không đủ điều kiện hoàn" };
}

// After a receipt refund request the customer lands on the refund/support
// details view, which lists "Yêu cầu hoàn tiền của tôi" (review 05/10 #33).
// Without `view` the router shows the simple support overview instead.
export const SUPPORT_DETAILS = Object.freeze({ tab: "support", view: "details" });

// A single-site deployment (SINGLE_SITE_ID) only has staff queues for its own
// site: a request filed against another site's receipt, order or stay would
// never reach anyone (review 05/10 #76). Rows without a site stay to the server.
export const OTHER_SITE_LABEL = "Chứng từ thuộc bãi khác; hãy liên hệ trực tiếp bãi đó để được hỗ trợ hoàn tiền.";
export function outsideSingleSite(row, singleSite) {
  return singleSite != null && row?.site_id != null && Number(row.site_id) !== Number(singleSite);
}

export function customerRefundAction(receipt, singleSite = null) {
  const state = refundAction(receipt);
  if (state.kind === "request" && outsideSingleSite(receipt, singleSite)) return { kind: "blocked", label: OTHER_SITE_LABEL };
  return state;
}

/** Hide "request_refund" on another site's order in a single-site deployment. */
export function scopeOrderActions(order, singleSite = null) {
  if (!order || !outsideSingleSite(order, singleSite) || !Array.isArray(order.allowed_actions)) return order;
  return { ...order, allowed_actions: order.allowed_actions.filter((action) => action !== "request_refund") };
}

/**
 * Resources a support request may be linked to. Each keeps its site (null =
 * the resource has no site; undefined = the list does not say). In a
 * single-site deployment other sites' resources are not offered.
 */
export function supportLinkCandidates({ orders, sessions, receipts, refunds }, describe, singleSite = null) {
  const keep = (row) => !outsideSingleSite(row, singleSite);
  const entry = (row, label) => ({ id: row.id, label, site_id: row.site_id });
  return {
    order: (orders || []).filter(keep).map((row) => entry(row, describe.order(row))),
    session: (sessions || []).filter(keep).map((row) => entry(row, describe.session(row))),
    receipt: (receipts || []).filter((row) => row.kind === "receipt" && keep(row)).map((row) => entry(row, describe.receipt(row))),
    refund_request: (refunds || []).filter((row) => !row.legacy && keep(row)).map((row) => entry(row, describe.refund_request(row))),
  };
}

/** A linked resource without a site needs the receiving site chosen by the customer (review 05/10 #20). */
export function linkNeedsSite(candidate) {
  return candidate?.site_id === null;
}

export function supportRequestBody(form, candidate, siteId) {
  const body = { subject: form.subject.trim(), category: form.category, message: form.message.trim() };
  if (form.linked_type) {
    body.linked_type = form.linked_type;
    body.linked_id = form.linked_id;
    if (linkNeedsSite(candidate) && siteId) body.site_id = Number(siteId);
  } else {
    body.site_id = Number(siteId);
  }
  return body;
}

// Which manager decisions apply to a refund request in its current state.
export function refundDecisions(row) {
  if (!row || row.legacy) return { review: false, approve: false, reject: false, record: false };
  const open = row.status === "pending" || row.status === "reviewing";
  return { review: row.status === "pending", approve: open, reject: open || row.status === "approved",
    record: row.status === "approved" && row.payment_channel !== "demo" };
}

// A non-DEMO approval of a prepaid hour/day ticket revokes the ticket at the
// decision (review 05/10 #23); the request can then only be recorded, not rejected.
export const REVOKED_REJECT_LABEL = "Vé đã được thu hồi khi duyệt hoàn: hãy ghi nhận đã hoàn tiền cho khách thay vì từ chối.";
export function rejectBlockedLabel(row, detail) {
  return row?.status === "approved" && detail?.entitlement_revoked ? REVOKED_REJECT_LABEL : "";
}
export function approvalEffectNote(row) {
  return row?.source_type === "portal_order" && row?.payment_channel !== "demo" && !row?.legacy
    ? "Duyệt sẽ thu hồi ngay vé giờ/ngày và chỗ giữ của khách; sau đó chỉ còn bước ghi nhận đã hoàn tiền." : "";
}

export function refundAmountHint(row) {
  if (!row) return "";
  if (row.status === "refunded") return `Đã hoàn ${row.approved_amount ?? ""}`.trim();
  if (row.status === "approved") return "Đã duyệt; tiền chưa được ghi nhận hoàn.";
  return "";
}

// Requests filed under a site the working screen cannot open (review 05/10 #76,
// rework): the server lists them to a global admin only. In single-site mode
// every other site is hidden; otherwise only closed sites are (an active site
// is reachable with the site picker). An active site's request is handled at
// its own site path; a closed site's request is shown for information.
export const OTHER_SITE_CLOSED_LABEL = "Bãi đã ngừng hoạt động: chỉ xem được, cần mở lại bãi để xử lý.";
export function otherSiteRequests(data, key, singleSiteMode) {
  if (!data?.visible || !Array.isArray(data[key])) return [];
  return singleSiteMode ? data[key] : data[key].filter((row) => !row.site_active);
}
export const otherSiteName = (row) => `${row?.site_name || `Bãi #${row?.site_id}`}${row?.site_active ? "" : " (đã ngừng hoạt động)"}`;
/** The site path a manager action on this row must use (its own site, else the working site). */
export const requestSitePath = (row, siteId) => row?.site_id || siteId;
