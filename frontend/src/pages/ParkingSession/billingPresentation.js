import { formatParkingFee } from "../../utils/formatCurrency.js";
import { formatBusinessDateOnly, formatBusinessTimestamp } from "../../utils/formatDate.js";

export function formatBillableDuration(seconds) {
  if (!Number.isSafeInteger(seconds) || seconds < 0) return "Chưa có số liệu";
  if (seconds === 0) return "0 giây";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor(seconds % 86400 / 3600);
  const minutes = Math.floor(seconds % 3600 / 60);
  const remainder = seconds % 60;
  return [[days, "ngày"], [hours, "giờ"], [minutes, "phút"], [remainder, "giây"]]
    .filter(([value]) => value > 0).map(([value, unit]) => `${value} ${unit}`).join(" ");
}

// These are server-provided billing facts. Never derive fees or rounded blocks
// from the clock in the browser: the signed quote remains authoritative.
export function billingPresentation(basis) {
  const source = basis?.rate_source;
  const knownSource = (source === "entry_snapshot" && basis.policy_version === "entry-v1")
    || (source === "prepaid_snapshot" && basis.policy_version === "prepaid-window-v1")
    || (source === "legacy_current_rate" && basis.policy_version === "legacy-current-rate");
  if (!knownSource || !["HOURLY", "DAILY"].includes(basis.ticket_type)
      || ![basis.unit_price, basis.billable_seconds, basis.billable_blocks].every((value) => Number.isSafeInteger(value) && value >= 0)
      || !Number.isFinite(Date.parse(basis.billable_from))) {
    return { available: false, rows: [] };
  }
  const hourly = basis.ticket_type === "HOURLY";
  const rows = [
    { label: "Đơn giá", value: `${formatParkingFee(basis.unit_price)} VND / ${hourly ? "giờ" : "24 giờ"}` },
    { label: "Mốc bắt đầu tính phí", value: formatBusinessTimestamp(basis.billable_from) },
    { label: "Thời gian tính phí", value: formatBillableDuration(basis.billable_seconds) },
    { label: "Số đơn vị tính phí", value: `${basis.billable_blocks} × ${hourly ? "1 giờ" : "24 giờ"}` },
  ];
  if (basis.effective_date) rows.push({ label: "Ngày áp dụng giá", value: formatBusinessDateOnly(basis.effective_date) });
  return { available: true, rows, legacy: source === "legacy_current_rate", prepaid: source === "prepaid_snapshot",
    sourceLabel: source === "prepaid_snapshot" ? "Giá phụ trội đã chốt khi mua gói" : source === "entry_snapshot" ? "Giá ghi nhận lúc xe vào" : "Giá hiện hành theo chính sách cũ" };
}

export function prepaidPresentation(prepaid) {
  if (!prepaid || !prepaid.order_id || !Number.isSafeInteger(prepaid.amount) || prepaid.amount < 0
      || !Number.isFinite(Date.parse(prepaid.start_at)) || !Number.isFinite(Date.parse(prepaid.end_at))) return { available: false };
  return { available: true, demo: prepaid.payment_mode === "demo", amount: `${formatParkingFee(prepaid.amount)} VND`,
    start: formatBusinessTimestamp(prepaid.start_at), end: formatBusinessTimestamp(prepaid.end_at), orderId: prepaid.order_id };
}
