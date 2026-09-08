export function parseCashAmount(value, { positive = false } = {}) {
  const raw = String(value).trim();
  if (!/^\d+$/.test(raw)) throw new Error("Nhập số tiền bằng đồng, chỉ gồm chữ số và không có dấu phân cách.");
  const amount = Number(raw);
  if (!Number.isSafeInteger(amount)) throw new Error("Số tiền vượt phạm vi được hỗ trợ.");
  if (positive && amount === 0) throw new Error("Số tiền hoàn phải lớn hơn 0 đồng.");
  return amount;
}

export function buildRefundPayload({ amount, method, reason, idempotencyKey, refundableAmount }) {
  const parsedAmount = parseCashAmount(amount, { positive: true });
  if (parsedAmount > refundableAmount) throw new Error("Số tiền hoàn vượt số tiền còn lại trên phiếu thu.");
  if (!["cash", "transfer"].includes(method)) throw new Error("Chọn phương thức hoàn tiền.");
  const trimmedReason = reason.trim();
  if (!trimmedReason || trimmedReason.length > 500) throw new Error("Nhập lý do hoàn tiền từ 1 đến 500 ký tự.");
  return { amount: parsedAmount, method, reason: trimmedReason, idempotency_key: idempotencyKey };
}

export const paymentMethodLabels = { cash: "Tiền mặt", transfer: "Chuyển khoản", legacy_unknown: "Không rõ (dữ liệu cũ)", demo: "Mô phỏng đồ án" };
