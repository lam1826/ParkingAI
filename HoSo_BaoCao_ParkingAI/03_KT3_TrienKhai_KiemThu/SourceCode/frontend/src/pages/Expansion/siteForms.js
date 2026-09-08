/** HTML datetime-local fields represent Vietnam business time, regardless of browser timezone. */
export function bookingTimestamp(value) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value || "")) throw new Error("Hãy nhập đủ ngày và giờ.");
  const result = `${value}:00+07:00`;
  const instant = Date.parse(result);
  if (!Number.isFinite(instant) || new Date(instant + 7 * 3600000).toISOString().slice(0, 16) !== value) throw new Error("Ngày giờ không hợp lệ.");
  return result;
}

export function bookingBody(form, siteId, requestId, { waitlist = false } = {}) {
  const site = Number(siteId), vehicle = Number(form.vehicle_id);
  if (!Number.isSafeInteger(site) || site <= 0 || !Number.isSafeInteger(vehicle) || vehicle <= 0) {
    throw new Error("Hãy chọn bãi và xe hợp lệ.");
  }
  const start = bookingTimestamp(form.start_at), end = bookingTimestamp(form.end_at);
  if (Date.parse(end) <= Date.parse(start)) throw new Error("Giờ kết thúc phải sau giờ bắt đầu.");
  const result = { site_id: site, vehicle_id: vehicle, start_at: start, end_at: end, request_id: requestId };
  if (!waitlist && form.slot_id) {
    const slot = Number(form.slot_id);
    if (!Number.isSafeInteger(slot) || slot <= 0) throw new Error("Vị trí không hợp lệ.");
    result.slot_id = slot;
  }
  return result;
}

export function checkoutAdapters(api, siteId) {
  const prefix = `/api/v2/sites/${encodeURIComponent(siteId)}/sessions`;
  return {
    loadQuote: async (id) => (await api.get(`${prefix}/${encodeURIComponent(id)}/checkout-quote`)).data,
    confirmCheckout: async (id, body) => (await api.put(`${prefix}/${encodeURIComponent(id)}/check-out`, body)).data,
  };
}

export function nextBookingWindow(now = Date.now()) {
  // Date's ISO rendering is used only after applying the fixed business offset.
  const start = Math.ceil((now + 5 * 60000) / 60000) * 60000;
  const local = (value) => new Date(value + 7 * 3600000).toISOString().slice(0, 16);
  return { start_at: local(start), end_at: local(start + 2 * 3600000) };
}
