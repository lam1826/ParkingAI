import { hasMinimumRole } from "../../constants/roles.js";

export function canManageCameras(globalRole, siteRole) {
  return hasMinimumRole(globalRole, "manager") && hasMinimumRole(siteRole, "manager");
}

export function cameraHealthText(camera) {
  if (camera.is_active === false) return "Ngừng hoạt động";
  return { unseen: "Chưa nhận ảnh", recent: "Có ảnh mới", stale: "Chưa có ảnh mới — kiểm tra kết nối", disabled: "Ngừng hoạt động" }[camera.health] || "Chưa có thông tin nhận ảnh";
}

export function cameraWriteBody(form, { siteId, editing = false } = {}) {
  const name = String(form.name || "").trim(), retention = Number(form.retention_hours);
  if (!name || name.length > 100) throw new Error("Tên camera cần từ 1 đến 100 ký tự.");
  if (!["entry", "exit"].includes(form.direction)) throw new Error("Chọn hướng xe vào hoặc xe ra.");
  if (!Number.isSafeInteger(retention) || retention < 1 || retention > 72) throw new Error("Thời gian lưu ảnh phải là số giờ nguyên từ 1 đến 72.");
  if (typeof form.is_active !== "boolean") throw new Error("Chọn trạng thái hoạt động của camera.");
  const body = { name, direction: form.direction, retention_hours: retention, is_active: form.is_active };
  if (!editing) {
    if (!Number.isSafeInteger(Number(siteId)) || Number(siteId) <= 0) throw new Error("Chọn bãi để tạo camera.");
    Object.assign(body, { site_id: Number(siteId), zone_id: null });
  }
  return body;
}
