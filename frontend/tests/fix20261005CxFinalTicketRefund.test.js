// Final money review: render the real SiteFinance with server-shaped ticket rows.
import test from "node:test";
import assert from "node:assert/strict";
import { buttonsNamed, fakeApi, findAll, fire, h, loadReal, R, settle, textOf } from "./fix20261005IntegrationHarness.js";

const site = { id: 4, role: "manager" };
const beforeStartLabel = "Vé giờ/ngày chưa sử dụng và chưa tới giờ bắt đầu: hãy xử lý qua yêu cầu hoàn tiền của khách để thu hồi vé và chỗ giữ.";
const revocationNotice = "Vé giờ/ngày chưa sử dụng sẽ bị thu hồi và chỗ giữ sẽ bị hủy, kể cả khi chỉ hoàn một phần.";
const receipt = (id, fields = {}) => ({
  id, kind: "receipt", source_type: "portal_order", method: "cash", amount: 12000,
  refundable_amount: 12000, created_at: "2026-10-05T10:00:00+07:00", shift_id: null,
  direct_refund_blocked_reason: null, direct_refund_revokes_ticket: false, ...fields,
});

async function mount(rows) {
  fakeApi.setHandler(async (method, url) => {
    assert.equal(method, "get");
    if (url.endsWith("/cash-shifts")) return { items: [] };
    if (url.endsWith("/payments")) return { items: rows };
    if (url.endsWith("/revenue")) return { total_revenue: 12000, unassigned_revenue: 12000, note: "" };
    throw new Error(`unexpected ${url}`);
  });
  const Page = (await loadReal("pages/Expansion/SiteFinance.jsx")).default;
  const root = R.createRoot();
  root.render(h(Page, { site }));
  await settle(root);
  return root;
}

test("only the before-start ticket and open-request rows point to the workflow", async () => {
  const root = await mount([
    receipt("before", { direct_refund_blocked_reason: "portal_ticket", direct_refund_blocked_label: beforeStartLabel }),
    receipt("started", { direct_refund_revokes_ticket: true }),
    receipt("expired"), receipt("consumed"), receipt("revoked"),
    receipt("open", { direct_refund_blocked_reason: "request_open", direct_refund_blocked_label: "Hãy xử lý yêu cầu hoàn đang mở." }),
    receipt("monthly", { source_type: "monthly_pass", direct_refund_blocked_reason: "portal_monthly", direct_refund_blocked_label: "Vé tháng: xử lý yêu cầu hoàn." }),
  ]);
  try {
    assert.equal(buttonsNamed(root, "Hoàn tiền").length, 4);
    assert.ok(textOf(root.tree).includes(beforeStartLabel));
    assert.ok(textOf(root.tree).includes("Hãy xử lý yêu cầu hoàn đang mở."));
    assert.ok(textOf(root.tree).includes("Vé tháng: xử lý yêu cầu hoàn."));
  } finally { root.unmount(); }
});

test("a started unused ticket refund explains that even a partial refund stops admission", async () => {
  const root = await mount([receipt("started-dialog", { direct_refund_revokes_ticket: true })]);
  try {
    fire(buttonsNamed(root, "Hoàn tiền")[0], "onClick");
    await settle(root);
    const dialog = findAll(root, (node) => node.type === "dialog")[0];
    assert.ok(dialog);
    assert.ok(textOf(dialog).includes(revocationNotice));
    assert.match(textOf(dialog), /12\.000/);
  } finally { root.unmount(); }
});

test("a terminal ticket refund has no entitlement-revocation warning", async () => {
  const root = await mount([receipt("expired-dialog")]);
  try {
    fire(buttonsNamed(root, "Hoàn tiền")[0], "onClick");
    await settle(root);
    assert.equal(textOf(root.tree).includes(revocationNotice), false);
  } finally { root.unmount(); }
});
