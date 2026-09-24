export const passageLabels = {
  entered: "Đã nhận xe", exited: "Đã cho xe ra", already_entered: "Xe đã ở trong bãi",
  waiting_payment: "Chờ thanh toán", manual: "Cần kiểm tra", disabled: "Tự động đang tắt",
};

export function framesForAutomation(rows, cameraId, handled, now = Date.now(), maxAgeSeconds = 15) {
  return rows.filter(row => Number(row.camera_id) === Number(cameraId) && row.review_status === "pending"
    && ["live_camera", "edge"].includes(row.capture_source)
    && !handled.has(row.id) && Number.isFinite(Date.parse(row.captured_at))
    && now >= Date.parse(row.captured_at) && now - Date.parse(row.captured_at) <= maxAgeSeconds * 1000)
    .sort((a, b) => Date.parse(a.captured_at) - Date.parse(b.captured_at)).slice(0, 4);
}
