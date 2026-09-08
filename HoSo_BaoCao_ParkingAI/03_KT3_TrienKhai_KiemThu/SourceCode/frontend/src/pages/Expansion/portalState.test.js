import test from "node:test";
import assert from "node:assert/strict";
import { mergeSelectedOrder, passStatus } from "./portalState.js";

test("order list refresh preserves the selected private QR while pending", () => {
  const detail = { id: "one", status: "pending", demo_token: "secret", demo_qr_svg: "<svg/>" };
  assert.equal(mergeSelectedOrder(detail, [{ id: "one", status: "pending", amount: 100 }]).demo_token, "secret");
  assert.equal(mergeSelectedOrder(detail, [{ id: "two", status: "pending" }]).id, "one");
});
test("a committed outcome cannot temporarily revert to pending or keep a usable QR", () => {
  assert.equal(mergeSelectedOrder({ id: "one", status: "fulfilled" }, [{ id: "one", status: "pending" }]).status, "fulfilled");
  const result = mergeSelectedOrder({ id: "one", status: "pending", demo_token: "secret", demo_qr_svg: "<svg/>" }, [{ id: "one", status: "expired" }]);
  assert.equal(result.status, "expired");
  assert.equal(result.demo_token, undefined);
  assert.equal(result.demo_qr_svg, undefined);
});

test("failed order-list refresh keeps the selected detail and strips completed payment credentials", () => {
  const pending = { id: "one", status: "pending", amount: 100, demo_token: "demo-secret", demo_qr_svg: "<svg/>" };
  assert.deepEqual(mergeSelectedOrder(pending, null), pending);
  const completed = mergeSelectedOrder({ ...pending, status: "fulfilled" }, null);
  assert.equal(completed.status, "fulfilled");
  assert.equal(completed.demo_token, undefined);
  assert.equal(completed.demo_qr_svg, undefined);
  assert.equal(pending.demo_token, "demo-secret");
});

test("pass visibility distinguishes active flag from inclusive business-date validity", () => {
  const period = { is_active: true, start_date: "2026-09-07", end_date: "2026-10-06" };
  assert.equal(passStatus(period, "2026-09-06"), "Chưa tới kỳ");
  assert.equal(passStatus(period, "2026-10-06"), "Đang hiệu lực");
  assert.equal(passStatus(period, "2026-10-07"), "Hết hạn");
  assert.equal(passStatus({ ...period, is_active: false }, "2026-09-07"), "Ngừng áp dụng");
});
