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

// Which manager decisions apply to a refund request in its current state.
export function refundDecisions(row) {
  if (!row || row.legacy) return { review: false, approve: false, reject: false, record: false };
  const open = row.status === "pending" || row.status === "reviewing";
  return { review: row.status === "pending", approve: open, reject: open || row.status === "approved",
    record: row.status === "approved" && row.payment_channel !== "demo" };
}

export function refundAmountHint(row) {
  if (!row) return "";
  if (row.status === "refunded") return `Đã hoàn ${row.approved_amount ?? ""}`.trim();
  if (row.status === "approved") return "Đã duyệt; tiền chưa được ghi nhận hoàn.";
  return "";
}
