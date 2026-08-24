// Đợt 10A — hiển thị đúng metadata timestamp UTC-naive (phương án A).
//
// Bối cảnh: các cột metadata `created_at`/`updated_at` trong backend dùng
// `server_default=func.now()` / `onupdate=func.now()`. Giá trị do CHÍNH
// SQLite sinh qua `CURRENT_TIMESTAMP`, mà SQLite luôn trả **UTC**. API
// serialize ra chuỗi naive KHÔNG hậu tố (ví dụ "2026-08-24T17:30:00"), nên
// `new Date(chuỗi)` của trình duyệt hiểu nhầm là giờ LOCAL -> lệch 7 giờ,
// và lệch cả NGÀY trong khung UTC 17:00–23:59 (= VN 00:00–06:59).
//
// Helper này KHÔNG đổi DB/schema/API: chỉ sửa lớp hiển thị — diễn giải đúng
// chuỗi naive là UTC, rồi format tường minh theo `Asia/Ho_Chi_Minh` bằng
// `Intl.DateTimeFormat` (không phụ thuộc timezone máy người dùng).
//
// LƯU Ý phân biệt với `businessDate.js`: file kia dựng chuỗi ngày cho
// payload NGHIỆP VỤ (check-in/report — vốn đã là naive business-local, xem
// backend/core/clock.py). File này chỉ dùng cho METADATA UTC-naive. Hai
// nhóm có semantics khác nhau, không dùng lẫn.

const BUSINESS_TIME_ZONE = "Asia/Ho_Chi_Minh";
const DEFAULT_FALLBACK = "—";

// Nhận diện chuỗi ĐÃ mang thông tin múi giờ tường minh: kết thúc bằng 'Z'
// (hoa/thường) hoặc có offset dạng +HH:MM / -HHMM / +HH ở cuối. Những chuỗi
// này đã đủ thông tin để xác định instant -> KHÔNG được gắn thêm 'Z'.
const HAS_EXPLICIT_ZONE = /(?:[Zz]|[+-]\d{2}:?\d{2}|[+-]\d{2})$/;

const dateTimeFormatter = new Intl.DateTimeFormat("vi-VN", {
  timeZone: BUSINESS_TIME_ZONE,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function toInstant(value) {
  if (value instanceof Date) return value;
  if (typeof value !== "string") return null;

  const trimmed = value.trim();
  if (!trimmed) return null;

  // Chuỗi thô của SQLite dùng dấu cách thay vì 'T' — chuẩn hóa trước để
  // Date parse ổn định trên mọi engine.
  const isoish = trimmed.replace(" ", "T");

  // Chỉ gắn 'Z' khi chuỗi CHƯA có thông tin múi giờ nào. Chuỗi đã có 'Z'
  // hoặc offset (+07:00, -05:00, …) được giữ nguyên để tôn trọng đúng
  // instant nó biểu diễn.
  return new Date(HAS_EXPLICIT_ZONE.test(isoish) ? isoish : `${isoish}Z`);
}

/**
 * Format một metadata timestamp (UTC-naive từ `func.now()`, hoặc chuỗi đã
 * có Z/offset, hoặc Date) thành chuỗi ngày-giờ theo Asia/Ho_Chi_Minh.
 * Trả `fallback` cho giá trị rỗng hoặc không parse được — không bao giờ
 * ném lỗi, không bao giờ hiển thị "Invalid Date".
 */
export default function formatMetadataTimestamp(value, { fallback = DEFAULT_FALLBACK } = {}) {
  const instant = toInstant(value);
  if (!instant || Number.isNaN(instant.getTime())) return fallback;
  return dateTimeFormatter.format(instant);
}
