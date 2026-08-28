import assert from "node:assert/strict";
import test from "node:test";

import formatCurrency, { formatParkingFee } from "../src/utils/formatCurrency.js";
import formatDate from "../src/utils/formatDate.js";
import { getToken, removeToken, setToken } from "../src/utils/storage.js";
import { isEmpty } from "../src/utils/validators.js";

test("isEmpty chỉ xem undefined, null và chuỗi rỗng là rỗng", () => {
  assert.equal(isEmpty(undefined), true);
  assert.equal(isEmpty(null), true);
  assert.equal(isEmpty(""), true);
  assert.equal(isEmpty(0), false);
  assert.equal(isEmpty(false), false);
  assert.equal(isEmpty(" "), false);
});

test("formatCurrency định dạng số theo locale Việt Nam", () => {
  assert.equal(formatCurrency(1234567), "1.234.567");
  assert.equal(formatCurrency(0), "0");
});

test("formatParkingFee hiển thị 0 đồng và chỉ dùng fallback khi thiếu dữ liệu", () => {
  assert.equal(formatParkingFee(0), "0");
  assert.equal(formatParkingFee(25000), "25.000");
  assert.equal(formatParkingFee(null), "—");
  assert.equal(formatParkingFee(undefined), "—");
});

test("formatDate định dạng ngày theo locale Việt Nam", () => {
  const result = formatDate("2026-08-23T12:00:00+07:00");
  assert.match(result, /^23\/0?8\/2026$/);
});

test("formatDate giữ nguyên ngày nghiệp vụ YYYY-MM-DD, không parse thành UTC rồi lùi ngày", () => {
  assert.equal(formatDate("2026-01-05"), "05/01/2026");
});

test("formatDate tôn trọng định dạng giờ mà SessionTable yêu cầu", () => {
  assert.equal(
    formatDate("2026-08-25T01:02:03", "HH:mm:ss - DD/MM/YYYY"),
    "01:02:03 - 25/08/2026",
  );
});

test("formatDate quy đổi timestamp có zone về giờ nghiệp vụ Việt Nam", () => {
  assert.equal(
    formatDate("2026-08-24T17:30:00Z", "HH:mm:ss - DD/MM/YYYY"),
    "00:30:00 - 25/08/2026",
  );
});

test("formatDate trả fallback an toàn cho giá trị rỗng hoặc sai", () => {
  assert.equal(formatDate(null), "—");
  assert.equal(formatDate("không-phải-ngày"), "—");
});

test("storage lưu, đọc và xóa access token", () => {
  const values = new Map();
  globalThis.localStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };

  assert.equal(getToken(), null);
  setToken("token-123");
  assert.equal(getToken(), "token-123");
  removeToken();
  assert.equal(getToken(), null);

  delete globalThis.localStorage;
});
