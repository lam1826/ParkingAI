// Đợt 10A — Timezone hardening.
//
// Module thuần (không phụ thuộc React/DOM) chịu trách nhiệm gửi request AI
// report ngày/tuần với đúng ngày nghiệp vụ Asia/Ho_Chi_Minh. Nhận
// `apiClient` qua tham số (dependency injection) thay vì import trực tiếp
// `services/api.js`, để test được bằng fake client — không cần mock
// axios/network, không cần render component.
//
// Bất biến bắt buộc: daily và weekly PHẢI dẫn xuất từ đúng MỘT instant
// `now` duy nhất do caller truyền vào (mặc định `new Date()` nếu không
// truyền). Cả hai hàm dưới đây tuyệt đối KHÔNG đọc đồng hồ lần thứ hai bên
// trong thân hàm — luôn truyền thẳng `now` nhận được xuống
// `toBusinessDateString`/`businessDateDaysAgo`. Nhờ vậy `start_date`/
// `end_date` của báo cáo tuần không bao giờ lệch nhau dù boundary rơi đúng
// nửa đêm VN giữa lúc hàm được gọi.

import { businessDateDaysAgo, toBusinessDateString } from "../utils/businessDate.js";

export const AI_DAILY_REPORT_URL = "/ai/daily-report";
export const AI_WEEKLY_REPORT_URL = "/ai/weekly-report";
export const AI_REQUEST_TIMEOUT_MS = 90_000;
const WEEKLY_WINDOW_DAYS = 6;

export function requestAI(apiClient, url, payload) {
  return apiClient.post(url, payload, { timeout: AI_REQUEST_TIMEOUT_MS });
}

/**
 * Gửi request sinh báo cáo ngày qua `apiClient`. `target_date` tính từ đúng
 * một instant `now`.
 */
export function requestDailyReport(apiClient, now = new Date()) {
  return requestAI(apiClient, AI_DAILY_REPORT_URL, {
    target_date: toBusinessDateString(now),
  });
}

/**
 * Gửi request sinh báo cáo tuần qua `apiClient`. `start_date` và `end_date`
 * cùng dẫn xuất từ đúng MỘT instant `now` duy nhất (không đọc đồng hồ lần
 * thứ hai bên trong hàm này).
 */
export function requestWeeklyReport(apiClient, now = new Date()) {
  return requestAI(apiClient, AI_WEEKLY_REPORT_URL, {
    start_date: businessDateDaysAgo(WEEKLY_WINDOW_DAYS, now),
    end_date: toBusinessDateString(now),
  });
}
