import { toBusinessDateString } from "./businessDate.js";
import { hasMinimumRole } from "../constants/roles.js";

export function canViewReportRevenue(data, role) {
  return hasMinimumRole(role, "manager") && data.data_scope !== "operations" && data.revenue != null;
}

export function reportStatistics(data, role) {
  const rows = [
    { id: "arrivals", label: "Lượt xe vào", value: data.total_arrivals },
    { id: "departures", label: "Lượt xe ra", value: data.total_departures },
  ];
  if (data.total_movements != null) rows.push({ id: "movements", label: "Tổng lượt vào và ra", value: data.total_movements });
  if (canViewReportRevenue(data, role)) {
    for (const [id, key, label] of [
      ["parking", "parking_revenue", "Thu gửi xe"],
      ["monthly", "monthly_pass_revenue", "Thu vé tháng"],
      ["refunds", "refunds", "Hoàn tiền"],
      ["net", "total_revenue", "Doanh thu thuần (không gồm demo)"],
    ]) rows.push({ id, label, value: data.revenue[key], currency: true });
  }
  return rows;
}

export function sessionSearchParams(page, filters) {
  const params = { ...page };
  for (const key of ["license_plate", "session_id", "status", "date_from", "date_to"]) {
    if (filters[key]) params[key] = filters[key];
  }
  return params;
}

export function analysisPayload({ kind, period, anchorDate, question, requestId }, now = new Date()) {
  return { kind, period, anchor_date: anchorDate || toBusinessDateString(now),
    question: kind === "question" ? question.trim() : "", request_id: requestId };
}
