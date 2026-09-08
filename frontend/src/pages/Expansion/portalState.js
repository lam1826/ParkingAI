export function mergeSelectedOrder(detail, rows = []) {
  if (!detail) return null;
  // A failed list request has null data; the separately fetched detail remains valid.
  const listed = rows?.find((row) => row.id === detail.id);
  // A refreshed list intentionally excludes the private QR; keep it from detail.
  // A response to a mutation can arrive before the list is refreshed.
  const merged = listed?.status === "pending" && detail.status !== "pending"
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
