// Fix 28/10/2026, lane FB, item R2-06 (UI): only a refund that settles the receipt
// ends the ticket or monthly period; a partial approval is compensation and keeps it.
// The manager's approval dialog words what the typed amount will do against the
// server's refundable amount (supportState.approvalEffectNote, binding rule R2-06),
// and the lists mark a partial decision ("· một phần") only when money was approved
// or refunded.
// Runs the REAL RefundAdminPanel and CustomerSupportPanel, with the real supportState
// and portalState, under the shared harness (fake HTTP client).
import test from "node:test";
import assert from "node:assert/strict";
import { buttonsNamed, fakeApi, findAll, fire, h, loadReal, R, settle, stub, tableUnder, textOf } from "./fix20261005IntegrationHarness.js";

const MUI = stub("fix20261028-refund-mui", `
const host = (tag) => function Mui({ children, ...props }) { return createElement(tag, props, children); };
export const Alert = host("mui-alert"), Box = host("div"), Button = host("button"), CircularProgress = host("progress");
export const MenuItem = host("option"), Stack = host("div"), TextField = host("mui-textfield"), Typography = host("span");
export const DialogActions = host("div"), DialogContent = host("div"), DialogTitle = host("h2"), Checkbox = host("mui-checkbox");
export function FormControlLabel({ control, label, ...props }) { return createElement("label", props, control, label); }
export function Dialog({ open, children, ...props }) { return open ? createElement("dialog", props, children) : null; }
`);

const pending = { id: "q1", site_id: 4, customer_name: "Khách A", payment_channel: "counter", source_type: "portal_order", source_id: "o1",
  reason: "Đổi lịch", requested_amount: 15000, approved_amount: null, status: "pending", created_at: "2026-10-28T08:00:00+07:00" };
const partial = { ...pending, id: "q2", source_type: "monthly_pass", requested_amount: 300000, approved_amount: 100000, status: "approved" };
const demoPartial = { ...pending, id: "q3", payment_channel: "demo", demo: true, requested_amount: 12000, approved_amount: 4000, status: "refunded" };
const fullMonthly = { ...partial, id: "q4", approved_amount: 300000 };
// The backend lets a manager reject after a partial approval and keeps approved_amount (refund_service.reject).
const rejectedAfterPartial = { ...pending, id: "q5", requested_amount: 12000, approved_amount: 4000, status: "rejected", decision_note: "Khách đổi ý" };
const monthly = { ...pending, id: "m1", source_type: "monthly_pass", requested_amount: 300000 };
const demoTicket = { ...pending, id: "d1", payment_channel: "demo", demo: true, requested_amount: 12000 };
const demoMonthly = { ...monthly, id: "d2", payment_channel: "demo", demo: true };
const credit = { ...pending, id: "c1", source_type: "session_credit", requested_amount: 5000 };

// Server refund_state per request: q1 had 3.000 ₫ refunded already, so 12.000 ₫ is refundable, not the requested 15.000 ₫.
const STATES = { q1: { amount: 15000, refunded_amount: 3000, refundable_amount: 12000 } };

async function renderPanel(rows) {
  fakeApi.setHandler(async (method, url) => {
    if (method === "get" && url === "/api/v2/sites/4/refund-requests") return rows;
    if (method === "get" && url === "/api/v2/sites/4/other-site-requests") return { visible: false };
    const row = rows.find((item) => url === `/api/v2/sites/4/refund-requests/${item.id}`);
    if (method === "get" && row) {
      const amount = row.requested_amount;
      return { refund_state: STATES[row.id] || { amount, refunded_amount: 0, refundable_amount: amount }, entitlement_revoked: false };
    }
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: RefundAdminPanel } = await loadReal("pages/Expansion/RefundAdminPanel.jsx", { "@mui/material": MUI });
  const root = R.createRoot();
  root.render(h(RefundAdminPanel, { siteId: 4 }));
  await settle(root);
  return root;
}
const dialogText = (root) => textOf(findAll(root, (node) => node.type === "dialog")[0]);

/** Open "Duyệt" on the index-th approvable row, type `value` (undefined = leave blank) and read the dialog. */
async function approvalDialog(root, index, value) {
  fire(buttonsNamed(root, "Duyệt")[index], "onClick");
  await settle(root);
  if (value !== undefined) {
    const amount = findAll(root, (node) => node.type === "mui-textfield" && node.props.label === "Số tiền duyệt hoàn (đồng)")[0];
    fire(amount, "onChange", { target: { value } });
    await settle(root);
  }
  const text = dialogText(root);
  fire(buttonsNamed(root, "Quay lại")[0], "onClick");
  await settle(root);
  return text;
}

const FULL_TICKET = /Duyệt sẽ thu hồi ngay vé giờ\/ngày và chỗ giữ của khách; sau đó chỉ còn bước ghi nhận đã hoàn tiền\./;
const FULL_DEMO_TICKET = /Duyệt toàn bộ sẽ hoàn mô phỏng ngay và thu hồi vé giờ\/ngày cùng chỗ giữ của khách\./;
const FULL_MONTHLY = /Duyệt toàn bộ: kỳ vé tháng sẽ dừng khi ghi nhận đã hoàn tiền\./;
const FULL_DEMO_MONTHLY = /Duyệt toàn bộ sẽ hoàn mô phỏng ngay và dừng kỳ vé tháng của khách\./;
const PARTIAL = /Duyệt một phần chỉ hoàn số tiền đã nhập; vé\/kỳ vé của khách vẫn còn hiệu lực và khách có thể gửi yêu cầu hoàn phần còn lại\./;

test("R2-06 the approval dialog the manager reads follows the typed amount against the server's refundable amount", async () => {
  const root = await renderPanel([pending, monthly, demoTicket, demoMonthly, credit]);
  // Counter hour/day ticket: blank = everything still refundable (12.000 ₫ per the server) revokes the ticket at the decision.
  assert.match(await approvalDialog(root, 0), FULL_TICKET);
  const partialTicket = await approvalDialog(root, 0, "4000");
  assert.match(partialTicket, PARTIAL);
  assert.doesNotMatch(partialTicket, /thu hồi/, "a partial approval keeps the ticket (refund_service.approve only revokes when the receipt settles)");
  assert.match(await approvalDialog(root, 0, "12000"), FULL_TICKET, "the server's refundable amount, not the requested 15.000 ₫, is the full amount");
  // Counter monthly pass: nothing stops at the decision; a full refund stops the period when it is recorded.
  const partialMonthly = await approvalDialog(root, 1, "100000");
  assert.match(partialMonthly, PARTIAL);
  assert.doesNotMatch(partialMonthly, /dừng/);
  assert.match(await approvalDialog(root, 1), FULL_MONTHLY);
  // DEMO: the simulated refund is written at the decision.
  const partialDemo = await approvalDialog(root, 2, "4000");
  assert.match(partialDemo, PARTIAL);
  assert.doesNotMatch(partialDemo, /thu hồi/);
  assert.match(await approvalDialog(root, 2), FULL_DEMO_TICKET);
  assert.match(await approvalDialog(root, 3), FULL_DEMO_MONTHLY);
  // A session credit carries no ticket or period: no effect note.
  assert.doesNotMatch(await approvalDialog(root, 4), /Duyệt toàn bộ|Duyệt một phần|thu hồi/);
  root.unmount();
});

test("R2-06 the amount field keeps the server's refundable amount as its bound", async () => {
  const root = await renderPanel([pending]);
  fire(buttonsNamed(root, "Duyệt")[0], "onClick");
  await settle(root);
  const field = findAll(root, (node) => node.type === "mui-textfield" && node.props.label === "Số tiền duyệt hoàn (đồng)")[0];
  assert.equal(field.props.slotProps.htmlInput.max, 12000);
  assert.match(field.props.helperText, /Để trống để duyệt toàn bộ 12\.000/);
  root.unmount();
});

test("R2-06 the manager list marks a partial decision and the record dialog says the ticket or period stays", async () => {
  const root = await renderPanel([pending, partial, demoPartial, fullMonthly, rejectedAfterPartial]);
  const rows = findAll(root, (node) => node.type === "tr").map((row) => textOf(row));
  assert.ok(rows.some((row) => row.includes("Được duyệt, chờ hoàn · một phần")), "approved partial monthly refund");
  assert.ok(rows.some((row) => row.includes("Đã hoàn mô phỏng (DEMO) · một phần")), "DEMO partial refund");
  assert.ok(rows.some((row) => row.includes("Đã tiếp nhận") && !row.includes("một phần")), "an undecided request is not partial");
  assert.ok(rows.some((row) => row.includes("Bị từ chối")), "the rejected request is listed");
  assert.ok(!rows.some((row) => row.includes("Bị từ chối · một phần")), "a request rejected after a partial approval refunded nothing");
  fire(buttonsNamed(root, "Ghi nhận đã hoàn")[0], "onClick");
  await settle(root);
  assert.match(dialogText(root), /Khoản hoàn một phần: ghi nhận này không thu hồi vé hay dừng kỳ vé của khách\./);
  fire(buttonsNamed(root, "Quay lại")[0], "onClick");
  await settle(root);
  fire(buttonsNamed(root, "Ghi nhận đã hoàn")[1], "onClick");
  await settle(root);
  assert.match(dialogText(root), /Ghi nhận hoàn toàn bộ sẽ dừng kỳ vé tháng của khách\./, "a full monthly refund stops the period at recording");
  assert.doesNotMatch(dialogText(root), /một phần/);
  root.unmount();
});

test("R2-06 the page explains that only a full approval ends the ticket or monthly period", async () => {
  const root = await renderPanel([]);
  assert.match(textOf(root.tree), /Chỉ khi duyệt hoàn toàn bộ số còn có thể hoàn, vé giờ\/ngày mới bị thu hồi hoặc kỳ vé tháng mới dừng; duyệt một phần vẫn giữ vé và khách có thể yêu cầu hoàn phần còn lại\./);
  root.unmount();
});

test("R2-06 partial = an approved or refunded amount below the requested amount, for a ticket or monthly pass only", async () => {
  const { partialRefund, refundLabelWithPart } = await import("../src/pages/Expansion/portalState.js");
  assert.equal(partialRefund(partial), true);
  assert.equal(partialRefund(demoPartial), true);
  assert.equal(partialRefund(pending), false, "no decision yet");
  assert.equal(partialRefund({ ...partial, approved_amount: 300000 }), false, "a full approval");
  assert.equal(partialRefund({ ...partial, source_type: "session_credit" }), false, "no entitlement to keep");
  assert.equal(partialRefund({ ...partial, legacy: true, requested_amount: null }), false, "legacy rows have no amounts");
  assert.equal(partialRefund(rejectedAfterPartial), false, "rejected after a partial approval: nothing was refunded");
  assert.equal(partialRefund(null), false);
  assert.equal(refundLabelWithPart("Đã hoàn tiền", partial), "Đã hoàn tiền · một phần");
  assert.equal(refundLabelWithPart("Đã tiếp nhận", pending), "Đã tiếp nhận");
  assert.equal(refundLabelWithPart("Bị từ chối", rejectedAfterPartial), "Bị từ chối");
});

test("R2-06 the customer's refund list marks a partial decision, but not a rejected one", async () => {
  fakeApi.setHandler(async (method, url) => {
    if (method === "get" && url === "/api/v2/sites") return [{ id: 4, name: "Bãi trung tâm" }];
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: CustomerSupportPanel } = await loadReal("pages/Expansion/CustomerSupportPanel.jsx");
  const refunds = { data: [partial, demoPartial, rejectedAfterPartial, fullMonthly], loading: false, error: "", reload: async () => {} };
  const root = R.createRoot();
  root.render(h(CustomerSupportPanel, { linked: false, orders: [], sessions: [], receipts: [], refunds }));
  await settle(root);
  const table = tableUnder(root, "Yêu cầu hoàn tiền của tôi");
  const status = table.headers.indexOf("Trạng thái");
  assert.deepEqual(table.rows.map((row) => row[status]),
    ["Được duyệt, chờ hoàn · một phần", "Đã hoàn mô phỏng (DEMO) · một phần", "Bị từ chối", "Được duyệt, chờ hoàn"]);
  root.unmount();
});
