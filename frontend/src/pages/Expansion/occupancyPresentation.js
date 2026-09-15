export const occupancyDefaults = Object.freeze({ pixel_delta: 30, empty_ratio: 0.06, occupied_ratio: 0.25,
  max_lighting_shift: 35, min_blur_variance: 15, stale_after_seconds: 30, confirmation_frames: 2 });

export const occupancyLabel = (state) => ({ occupied: "Có xe theo ảnh", empty: "Trống theo ảnh", unknown: "Chưa xác định", inactive: "Ngừng sử dụng" })[state] || "Chưa xác định";
export const occupancyReason = (reason) => ({
  reference_expired: "Ảnh nền đã hết hạn hoặc bị xóa; cần cấu hình ảnh nền mới.", source_expired: "Ảnh quan sát đã hết hạn hoặc bị xóa.",
  stale_capture: "Ảnh chụp đã cũ; cần ảnh mới để xác định hiện trạng.", future_capture: "Thời điểm chụp nằm trong tương lai; kiểm tra đồng hồ thiết bị.",
  camera_disabled: "Camera đã ngừng hoạt động.", no_observation: "Chưa phân tích ảnh với phiên bản cấu hình này.",
  slot_inactive: "Chỗ, khu vực hoặc loại xe đã ngừng sử dụng.", insufficient_history: "Cần thêm ảnh mới để xác nhận trạng thái.",
  slot_mapping_changed: "Thông tin chỗ đã thay đổi; quản lý cần cấu hình lại vùng.",
  unstable_observations: "Các ảnh gần nhau chưa thống nhất; cần kiểm tra trực tiếp.", too_dark: "Ảnh quá tối.", too_bright: "Ảnh quá sáng.",
  blurred: "Ảnh quá mờ.", obscured: "Khung hình bị che hoặc mất chi tiết.", region_obscured: "Vùng chỗ đỗ bị che hoặc mất chi tiết.",
  reference_quality: "Ảnh nền không đủ rõ.", lighting_changed: "Ánh sáng thay đổi nhiều; cần kiểm tra ảnh nền.",
  scene_changed: "Khung cảnh thay đổi nhiều; kiểm tra góc camera.", frame_geometry_changed: "Kích thước ảnh khác ảnh nền; cần giữ nguyên góc chụp và kích thước.",
  ambiguous_change: "Mức thay đổi chưa đủ để kết luận.",
})[reason] || (reason ? "Cần kiểm tra trực tiếp." : "");

export function normalizedPoint(x, y, rect) {
  if (![x, y, rect?.left, rect?.top, rect?.width, rect?.height].every(Number.isFinite) || rect.width <= 0 || rect.height <= 0) return null;
  const point = [(x - rect.left) / rect.width, (y - rect.top) / rect.height];
  return point.every((value) => value >= 0 && value <= 1) ? point.map((value) => Math.round(value * 10000) / 10000) : null;
}

export function regionDraft(slotId, polygon) {
  const slot = Number(slotId);
  if (!Number.isSafeInteger(slot) || slot <= 0) throw new Error("Chọn chỗ đỗ cần khoanh vùng.");
  if (!Array.isArray(polygon) || polygon.length < 3 || polygon.length > 12 || polygon.some((point) => !Array.isArray(point) || point.length !== 2 || point.some((value) => !Number.isFinite(value) || value < 0 || value > 1))) {
    throw new Error("Vùng cần từ 3 đến 12 đỉnh, mỗi tọa độ từ 0 đến 1.");
  }
  if (new Set(polygon.map((point) => point.join(","))).size !== polygon.length) throw new Error("Các đỉnh không được trùng nhau.");
  return { slot_id: slot, polygon: polygon.map((point) => [...point]) };
}

// Server time + monotonic elapsed time; local timezone/clock cannot keep a stale state green.
export function occupancyIsCurrent(data, elapsedMs = 0) {
  const expiry = Date.parse(data?.valid_until), observed = Date.parse(data?.server_now);
  return Number.isFinite(expiry) && Number.isFinite(observed) && Number.isFinite(elapsedMs) && elapsedMs >= 0 && observed + elapsedMs < expiry;
}

export function visibleReadings(data, elapsedMs) {
  if (occupancyIsCurrent(data, elapsedMs)) return data?.readings || [];
  return (data?.readings || []).map((row) => ({ ...row, state: "unknown", mismatch: null, reason: row.state === "unknown" ? row.reason : "stale_capture" }));
}
