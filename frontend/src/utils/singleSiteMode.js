// Presentation scope for the school demo. Authorization stays on the server.
// An unavailable configured site must never fall back to another site's data.
export function singleSiteId(config = globalThis.__PARKINGAI_CONFIG__) {
  const value = config?.SINGLE_SITE_ID;
  if (value == null || value === "") return null;
  if (!/^[1-9]\d*$/.test(String(value)) || !Number.isSafeInteger(Number(value))) {
    throw new Error("Cấu hình bãi đỗ chưa hợp lệ. Liên hệ quản trị viên.");
  }
  return Number(value);
}

export function scopeDemoCatalog(path, data, config = globalThis.__PARKINGAI_CONFIG__) {
  const siteId = singleSiteId(config);
  if (siteId === null || !["/sites", "/plans", "/portal/admin/plans"].includes(path)) return data;
  const rows = Array.isArray(data) ? data : data?.items;
  if (!Array.isArray(rows)) throw new Error("Không đọc được danh mục của bãi đỗ. Hãy thử tải lại.");
  const key = path === "/sites" ? "id" : "site_id";
  const selected = rows.filter((row) => Number(row[key]) === siteId);
  return Array.isArray(data) ? selected : { ...data, items: selected };
}
