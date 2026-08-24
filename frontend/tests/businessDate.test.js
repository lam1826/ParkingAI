import assert from "node:assert/strict";
import test from "node:test";

import {
  businessDateDaysAgo,
  formatBusinessLongDate,
  toBusinessDateString,
} from "../src/utils/businessDate.js";

// Đợt 10A — Timezone hardening (frontend). Mọi test dùng instant TUYỆT ĐỐI
// (chuỗi ISO có 'Z') để không phụ thuộc timezone của máy chạy test runner —
// Node's Intl luôn quy đổi từ đúng instant UTC sang Asia/Ho_Chi_Minh bất kể
// TZ hệ thống đang set gì.

test("toBusinessDateString: 2025-12-31T17:30:00Z -> 2026-01-01 (17:30 UTC + 7h = 00:30 VN, đã sang ngày mới)", () => {
  const result = toBusinessDateString(new Date("2025-12-31T17:30:00Z"));
  assert.equal(result, "2026-01-01");
});

test("toBusinessDateString: KHÔNG bị quy đổi qua UTC như toISOString().slice() cũ — chứng minh khác biệt trực tiếp", () => {
  const instant = new Date("2025-12-31T17:30:00Z");
  const buggyOldWay = instant.toISOString().slice(0, 10); // UTC date -> "2025-12-31"
  const correctWay = toBusinessDateString(instant); // VN date -> "2026-01-01"
  assert.equal(buggyOldWay, "2025-12-31");
  assert.equal(correctWay, "2026-01-01");
  assert.notEqual(buggyOldWay, correctWay, "Hai cách phải cho kết quả KHÁC nhau ở boundary này");
});

test("boundary VN 00:00:00 — đúng đầu ngày VN phải thuộc về ngày đó", () => {
  // VN 2026-03-10 00:00:00 = UTC 2026-03-09 17:00:00
  const result = toBusinessDateString(new Date("2026-03-09T17:00:00Z"));
  assert.equal(result, "2026-03-10");
});

test("boundary VN 23:59:00 — cuối ngày VN vẫn thuộc về ngày đó, chưa sang ngày mới", () => {
  // VN 2026-03-10 23:59:00 = UTC 2026-03-10 16:59:00
  const result = toBusinessDateString(new Date("2026-03-10T16:59:00Z"));
  assert.equal(result, "2026-03-10");
});

test("boundary: một giây trước 00:00 VN vẫn thuộc về ngày HÔM TRƯỚC", () => {
  // VN 2026-03-09 23:59:59 = UTC 2026-03-09 16:59:59 (một giây trước mốc 00:00:00 đã test ở trên)
  const result = toBusinessDateString(new Date("2026-03-09T16:59:59Z"));
  assert.equal(result, "2026-03-09");
});

test("businessDateDaysAgo: 6 ngày trước tính bằng mili-giây tuyệt đối, không dùng Date.setDate() cục bộ", () => {
  const from = new Date("2026-03-10T10:00:00Z"); // VN 2026-03-10 17:00
  assert.equal(businessDateDaysAgo(0, from), "2026-03-10");
  assert.equal(businessDateDaysAgo(6, from), "2026-03-04");
});

test("businessDateDaysAgo: đúng 7 ngày liên tiếp (start..end inclusive) qua boundary tháng", () => {
  const end = new Date("2026-03-01T10:00:00Z"); // VN 2026-03-01
  assert.equal(businessDateDaysAgo(6, end), "2026-02-23");
});

test("toBusinessDateString: định dạng luôn 2 chữ số cho tháng/ngày (không phụ thuộc locale)", () => {
  // VN 2026-01-05 nhỏ hơn 10 -> phải có số 0 đứng trước cho cả tháng và ngày
  const result = toBusinessDateString(new Date("2026-01-04T20:00:00Z")); // UTC 20:00 + 7h = VN 03:00 ngày 5/1
  assert.equal(result, "2026-01-05");
});

// ---------------------------------------------------------------------------
// formatBusinessLongDate — ngày dài hiển thị trên DashboardHeader
// ---------------------------------------------------------------------------

test("formatBusinessLongDate: instant 2026-08-24T17:30:00Z phải thuộc ngày 25/08/2026 tại Việt Nam", () => {
  // UTC 17:30 + 7h = VN 00:30 ngày hôm sau -> phải hiển thị ngày 25, không phải 24
  const result = formatBusinessLongDate(new Date("2026-08-24T17:30:00Z"));
  assert.match(result, /25/, `Phải chứa ngày 25, nhận được: ${result}`);
  assert.match(result, /2026/, `Phải chứa năm 2026, nhận được: ${result}`);
  assert.doesNotMatch(result, /\b24\b/, `KHÔNG được hiển thị ngày 24 (ngày theo UTC), nhận được: ${result}`);
});

test("formatBusinessLongDate: đúng thứ trong tuần theo lịch Việt Nam", () => {
  // VN 2026-08-25 là Thứ Ba (locale vi-VN: "Thứ Ba")
  const result = formatBusinessLongDate(new Date("2026-08-24T17:30:00Z"));
  assert.match(result, /Thứ Ba/i, `Phải là Thứ Ba theo lịch VN, nhận được: ${result}`);
});

test("formatBusinessLongDate: một khắc trước nửa đêm VN vẫn thuộc ngày cũ", () => {
  // UTC 2026-08-24T16:59:59Z = VN 2026-08-24 23:59:59 -> vẫn ngày 24
  const result = formatBusinessLongDate(new Date("2026-08-24T16:59:59Z"));
  assert.match(result, /24/, `Phải chứa ngày 24, nhận được: ${result}`);
  assert.doesNotMatch(result, /\b25\b/, `Chưa được sang ngày 25, nhận được: ${result}`);
});

test("formatBusinessLongDate: không truyền tham số vẫn trả chuỗi hợp lệ cho thời điểm hiện tại", () => {
  const result = formatBusinessLongDate();
  assert.equal(typeof result, "string");
  assert.ok(result.length > 0);
  assert.match(result, /\d{4}/, "Phải chứa năm 4 chữ số");
});
