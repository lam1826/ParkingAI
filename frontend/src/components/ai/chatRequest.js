import { toBusinessDateString } from "../../utils/businessDate.js";

export function chatScopeKey(userId, role, siteId) {
  return `${userId}:${role}:${siteId || "no-site"}`;
}

export function chatRequest({ role, siteId, question, action = "question", createKey, now = new Date() }) {
  if (!Number.isSafeInteger(Number(siteId)) || Number(siteId) <= 0) throw new Error("Chưa chọn được bãi đang hoạt động.");
  const text = String(question || "").trim();
  if (!text || text.length > 2000) throw new Error("Câu hỏi cần từ 1 đến 2.000 ký tự.");
  if (role === "customer") return { path: `/api/v2/public/sites/${siteId}/assistant`, body: { question: text } };
  if (!["admin", "manager", "staff"].includes(role)) throw new Error("Tài khoản không có quyền sử dụng trợ lý.");
  const period = action === "weekly" || /tuần/i.test(text) ? "week" : "day";
  const kind = ["daily", "weekly"].includes(action) ? "report" : action === "staff" ? "staff" : "question";
  return { path: `/api/v2/sites/${siteId}/ai/analyses`, body: {
    kind, period, anchor_date: toBusinessDateString(now), question: kind === "question" ? text : "", request_id: createKey(),
  } };
}
