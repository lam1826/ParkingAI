import assert from "node:assert/strict";
import test from "node:test";

import formatMetadataTimestamp from "../src/utils/formatMetadataTimestamp.js";

// Đợt 10A — phương án A cho metadata UTC-naive.
//
// Các cột created_at/updated_at dùng server_default=func.now() được SQLite
// sinh bằng CURRENT_TIMESTAMP, luôn là UTC. API trả chuỗi naive KHÔNG có
// hậu tố 'Z' (ví dụ "2026-08-24T17:30:00"), nên `new Date(...)` của trình
// duyệt diễn giải nhầm thành giờ local -> lệch 7 giờ (và lệch cả NGÀY trong
// khung UTC 17:00–23:59). Helper này diễn giải đúng là UTC rồi format rõ
// ràng theo Asia/Ho_Chi_Minh, không phụ thuộc timezone máy người dùng.
//
// Mọi test dùng instant tuyệt đối / chuỗi cố định nên kết quả không phụ
// thuộc TZ của máy chạy test runner.

test("chuỗi UTC-naive 17:30 phải hiển thị sang NGÀY KẾ TIẾP theo giờ Việt Nam", () => {
  // UTC 2026-08-24 17:30 + 7h = VN 2026-08-25 00:30 (đã sang ngày mới)
  const result = formatMetadataTimestamp("2026-08-24T17:30:00");
  assert.match(result, /25\/08\/2026/, `Phải là ngày 25/08/2026 theo giờ VN, nhận được: ${result}`);
  assert.match(result, /00:30/, `Phải là 00:30 giờ VN, nhận được: ${result}`);
});

test("chuỗi UTC-naive giữa ngày: cộng đúng 7 giờ, không đổi ngày", () => {
  // UTC 2026-08-24 03:15 + 7h = VN 2026-08-24 10:15
  const result = formatMetadataTimestamp("2026-08-24T03:15:00");
  assert.match(result, /24\/08\/2026/);
  assert.match(result, /10:15/);
});

test("chuỗi UTC-naive có dấu cách thay vì 'T' (định dạng SQLite thô) vẫn được hiểu là UTC", () => {
  // SQLite CURRENT_TIMESTAMP trả "YYYY-MM-DD HH:MM:SS"
  const result = formatMetadataTimestamp("2026-08-24 17:30:00");
  assert.match(result, /25\/08\/2026/);
  assert.match(result, /00:30/);
});

test("chuỗi ĐÃ có hậu tố 'Z' phải được giữ nguyên, KHÔNG thêm 'Z' lần hai", () => {
  const withZ = formatMetadataTimestamp("2026-08-24T17:30:00Z");
  const withoutZ = formatMetadataTimestamp("2026-08-24T17:30:00");
  assert.equal(withZ, withoutZ, "Chuỗi có 'Z' và không có 'Z' cùng chỉ một instant -> phải ra kết quả giống hệt");
  assert.match(withZ, /25\/08\/2026/);
});

test("chuỗi đã có offset tường minh phải được tôn trọng, không bị coi là UTC", () => {
  // +07:00 nghĩa là ĐÃ là giờ VN -> hiển thị đúng 17:30 cùng ngày, KHÔNG cộng thêm 7h nữa
  const result = formatMetadataTimestamp("2026-08-24T17:30:00+07:00");
  assert.match(result, /24\/08\/2026/, `Offset +07:00 đã là giờ VN, không được cộng thêm: ${result}`);
  assert.match(result, /17:30/);
});

test("offset âm cũng được tôn trọng đúng", () => {
  // UTC-05:00 12:30 = UTC 17:30 = VN 00:30 ngày hôm sau
  const result = formatMetadataTimestamp("2026-08-24T12:30:00-05:00");
  assert.match(result, /25\/08\/2026/);
  assert.match(result, /00:30/);
});

test("giá trị null/undefined/chuỗi rỗng trả fallback an toàn, không ném lỗi", () => {
  assert.equal(formatMetadataTimestamp(null), "—");
  assert.equal(formatMetadataTimestamp(undefined), "—");
  assert.equal(formatMetadataTimestamp(""), "—");
});

test("chuỗi không parse được trả fallback an toàn, không ném lỗi và không hiện 'Invalid Date'", () => {
  const result = formatMetadataTimestamp("không-phải-ngày");
  assert.equal(result, "—");
  assert.doesNotMatch(result, /Invalid/i);
});

test("fallback tùy chỉnh được tôn trọng", () => {
  assert.equal(formatMetadataTimestamp(null, { fallback: "N/A" }), "N/A");
});

test("đối tượng Date được truyền thẳng cũng format đúng theo giờ VN", () => {
  const result = formatMetadataTimestamp(new Date("2026-08-24T17:30:00Z"));
  assert.match(result, /25\/08\/2026/);
  assert.match(result, /00:30/);
});
