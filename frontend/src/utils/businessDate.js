// Đợt 10A — Timezone hardening (frontend).
//
// Dựng chuỗi ngày "YYYY-MM-DD" theo lịch nghiệp vụ Asia/Ho_Chi_Minh, KHÔNG
// phụ thuộc timezone của máy/trình duyệt người dùng và KHÔNG quy đổi qua UTC
// trước khi lấy ngày (khác `date.toISOString().slice(0, 10)`, vốn lấy ngày
// theo UTC — sai lệch trong khung 00:00–06:59 giờ VN).
//
// Dùng `Intl.DateTimeFormat(..., { timeZone: "Asia/Ho_Chi_Minh" })` — API
// chuẩn của trình duyệt/Node, luôn tính từ đúng instant UTC thật của `Date`
// rồi quy đổi theo timeZone chỉ định, không phụ thuộc cấu hình hệ thống.
// Dùng `formatToParts()` thay vì `.format()` để lấy trực tiếp từng thành
// phần year/month/day theo `type`, không dựa vào thứ tự ký tự của một chuỗi
// đã format sẵn (vốn phụ thuộc locale).

const BUSINESS_TIME_ZONE = "Asia/Ho_Chi_Minh";
const DAY_MS = 24 * 60 * 60 * 1000; // Việt Nam không dùng DST -> mỗi ngày đúng 24h

const partsFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: BUSINESS_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

// Ngày dài để HIỂN THỊ (khác partsFormatter dùng để dựng payload): locale
// vi-VN cho nhãn thứ/tháng tiếng Việt, nhưng vẫn ghim timeZone nghiệp vụ để
// ngày hiển thị không lệch theo timezone máy người dùng.
const longDateFormatter = new Intl.DateTimeFormat("vi-VN", {
  timeZone: BUSINESS_TIME_ZONE,
  weekday: "long",
  day: "2-digit",
  month: "long",
  year: "numeric",
});

/**
 * Chuyển một Date (hoặc instant hiện tại nếu không truyền) thành chuỗi
 * "YYYY-MM-DD" theo lịch Asia/Ho_Chi_Minh.
 */
export function toBusinessDateString(date = new Date()) {
  const parts = partsFormatter.formatToParts(date);
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${byType.year}-${byType.month}-${byType.day}`;
}

/**
 * Chuỗi "YYYY-MM-DD" của ngày cách `from` (mặc định: hiện tại) đúng `days`
 * ngày về trước, theo lịch Asia/Ho_Chi_Minh. Trừ thẳng mili-giây trên chính
 * instant (không dùng Date.setDate() cục bộ trình duyệt) để tránh lệch ngày
 * nếu "hôm nay" theo trình duyệt và theo giờ VN rơi vào hai ngày khác nhau.
 */
export function businessDateDaysAgo(days, from = new Date()) {
  return toBusinessDateString(new Date(from.getTime() - days * DAY_MS));
}

/**
 * Ngày dạng dài (thứ, ngày, tháng, năm) theo locale vi-VN và lịch
 * Asia/Ho_Chi_Minh — dùng cho phần hiển thị "hôm nay" trên giao diện.
 * Khác `new Date().toLocaleDateString("vi-VN", …)` không có `timeZone`:
 * cách cũ lấy ngày theo timezone máy người dùng, nên máy đặt lệch múi giờ
 * (hoặc server-side render ở UTC) sẽ hiện sai ngày trong khung 00:00–06:59
 * giờ VN.
 */
export function formatBusinessLongDate(date = new Date()) {
  return longDateFormatter.format(date);
}
