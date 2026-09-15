import { businessDateDaysAgo, toBusinessDateString } from "./businessDate.js";

function validDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function getMonthlyPassStatus(pass, now = new Date()) {
  if (!pass.is_active) return { label: "Ngừng hoạt động", color: "default" };
  if (!validDate(pass.start_date) || !validDate(pass.end_date) || pass.start_date > pass.end_date) {
    return { label: "Chưa rõ hiệu lực", color: "default" };
  }
  const today = toBusinessDateString(now);
  if (pass.end_date < today) return { label: "Hết hạn", color: "error" };
  if (pass.start_date > today) return { label: "Chưa đến hạn", color: "info" };
  if (pass.end_date <= businessDateDaysAgo(-7, now)) return { label: "Sắp hết hạn", color: "warning" };
  return { label: "Đang hoạt động", color: "success" };
}
