import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("bảng phiên gần đây dùng formatter giờ nghiệp vụ Việt Nam", async () => {
  const source = await readFile(
    new URL(
      "../src/pages/Dashboard/components/RecentSessionsTable.jsx",
      import.meta.url,
    ),
    "utf8",
  );

  assert.match(source, /formatBusinessTimestamp/);
  assert.doesNotMatch(source, /new Date\s*\(/);
});


test("bảng phiên gửi xe giữ nguyên phí 0 thay vì hiển thị thiếu dữ liệu", async () => {
  const source = await readFile(
    new URL(
      "../src/pages/ParkingSession/components/SessionTable.jsx",
      import.meta.url,
    ),
    "utf8",
  );

  assert.match(source, /formatParkingFee\(value\)/);
  assert.doesNotMatch(source, /value\s*\?\s*new Intl\.NumberFormat/);
});


test("tra cứu phiên và báo cáo chỉ nhận response mới nhất", async () => {
  const [parkingHook, reportPage] = await Promise.all([
    readFile(
      new URL(
        "../src/pages/ParkingSession/hooks/useParkingSession.js",
        import.meta.url,
      ),
      "utf8",
    ),
    readFile(
      new URL("../src/pages/Report/ReportPage.jsx", import.meta.url),
      "utf8",
    ),
  ]);

  for (const source of [parkingHook, reportPage]) {
    assert.match(source, /createLatestRequestGate/);
    assert.match(source, /\.begin\(\)/);
    assert.match(source, /\.isCurrent\(/);
    assert.match(source, /\.invalidate\(\)/);
  }
});


test("refresh chỗ trống chỉ nhận response mới nhất", async () => {
  const source = await readFile(
    new URL(
      "../src/pages/ParkingSession/hooks/useParkingSession.js",
      import.meta.url,
    ),
    "utf8",
  );

  assert.match(source, /slotRequestGate/);
  assert.match(source, /slotRequestGate\.current\.begin\(\)/);
  assert.match(source, /slotRequestGate\.current\.isCurrent\(/);
  assert.match(source, /slotRequestGate\.current\.invalidate\(\)/);
});


test("nhật ký tải đủ mọi trang và bỏ qua response filter đã cũ", async () => {
  const source = await readFile(
    new URL("../src/pages/AuditLog/AuditLogPage.jsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /requestAllOffsetPages/);
  assert.match(source, /createLatestRequestGate/);
  assert.match(source, /\.isCurrent\(/);
  assert.doesNotMatch(source, /limit:\s*500/);
});
