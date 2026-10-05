// Review 05/10/2026 CL-LEDGER #33 (refund request lands on details), #76 (single-site
// scope of refund/support targets), #20 (site for site-less links), #23 (reject after revocation).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { portalTab } from "../src/pages/Expansion/customerFlow.js";
import {
  approvalEffectNote, customerRefundAction, linkNeedsSite, OTHER_SITE_CLOSED_LABEL, OTHER_SITE_LABEL, otherSiteName,
  otherSiteRequests, outsideSingleSite, rejectBlockedLabel, requestSitePath, scopeOrderActions, SUPPORT_DETAILS,
  supportLinkCandidates, supportRequestBody,
} from "../src/pages/Expansion/supportState.js";

test("#33 after a receipt refund request the customer lands on the refund/support details tab", () => {
  const params = new URLSearchParams(SUPPORT_DETAILS);
  assert.equal(portalTab(params), 5);
  // CustomerPortal routes `tab=support` WITHOUT a view to the simple overview; details keeps CustomerTickets mounted.
  assert.equal(params.get("view"), "details");
  const source = readFileSync(new URL("../src/pages/Expansion/CustomerPortal.jsx", import.meta.url), "utf8");
  assert.match(source, /value === 5 \? SUPPORT_DETAILS/);
  assert.doesNotMatch(source, /value === 5 \? \{ tab: "support" \}/);
});

const eligible = { id: "r1", kind: "receipt", site_id: 1, refund: { eligible: true, refundable_amount: 1000 } };

test("#76 single-site deployment does not offer requests that land in another site's queue", () => {
  assert.equal(outsideSingleSite(eligible, 2), true);
  assert.equal(outsideSingleSite(eligible, null), false);
  assert.equal(outsideSingleSite({ ...eligible, site_id: null }, 2), false);
  assert.equal(outsideSingleSite({ ...eligible, site_id: "2" }, 2), false);
  assert.deepEqual(customerRefundAction(eligible, 2), { kind: "blocked", label: OTHER_SITE_LABEL });
  assert.equal(customerRefundAction(eligible, 1).kind, "request");
  assert.equal(customerRefundAction(eligible, null).kind, "request");
  // A server block keeps its own wording.
  const blocked = { ...eligible, refund: { eligible: false, blocked_label: "Đã hết hạn" } };
  assert.deepEqual(customerRefundAction(blocked, 2), { kind: "blocked", label: "Đã hết hạn" });
  const order = { id: "o1", site_id: 1, allowed_actions: ["request_refund", "view"] };
  assert.deepEqual(scopeOrderActions(order, 2).allowed_actions, ["view"]);
  assert.equal(scopeOrderActions(order, 1), order);
  assert.equal(scopeOrderActions(null, 2), null);
  const describe = { order: (row) => row.id, session: (row) => row.id, receipt: (row) => row.id, refund_request: (row) => row.id };
  const lists = {
    orders: [{ id: "o1", site_id: 1 }, { id: "o2", site_id: 2 }],
    sessions: [{ id: "s1" }],
    receipts: [{ id: "r1", kind: "receipt", site_id: 1 }, { id: "r2", kind: "receipt", site_id: null }, { id: "x", kind: "refund", site_id: 2 }],
    refunds: [{ id: "q1", site_id: 1 }, { id: "q2", site_id: 2 }, { id: "legacy", site_id: 2, legacy: true }],
  };
  const scoped = supportLinkCandidates(lists, describe, 2);
  assert.deepEqual(scoped.order.map((row) => row.id), ["o2"]);
  assert.deepEqual(scoped.session.map((row) => row.id), ["s1"]);
  assert.deepEqual(scoped.receipt.map((row) => row.id), ["r2"]);
  assert.deepEqual(scoped.refund_request.map((row) => row.id), ["q2"]);
  assert.deepEqual(supportLinkCandidates(lists, describe, null).order.map((row) => row.id), ["o1", "o2"]);
});

test("#20 a linked resource without a site sends the chosen receiving site", () => {
  const form = { subject: " Vé tháng ", category: "receipt", message: " Giúp ", linked_type: "receipt", linked_id: "r2" };
  assert.equal(linkNeedsSite({ id: "r2", site_id: null }), true);
  assert.equal(linkNeedsSite({ id: "s1", site_id: undefined }), false);
  assert.deepEqual(supportRequestBody(form, { id: "r2", site_id: null }, "3"),
    { subject: "Vé tháng", category: "receipt", message: "Giúp", linked_type: "receipt", linked_id: "r2", site_id: 3 });
  // A resource with its own site stays authoritative: no site is sent.
  assert.equal("site_id" in supportRequestBody({ ...form, linked_id: "r1" }, { id: "r1", site_id: 1 }, "3"), false);
  assert.deepEqual(supportRequestBody({ ...form, linked_type: "", linked_id: "" }, null, "3"),
    { subject: "Vé tháng", category: "receipt", message: "Giúp", site_id: 3 });
  const source = readFileSync(new URL("../src/pages/Expansion/CustomerSupportPanel.jsx", import.meta.url), "utf8");
  assert.match(source, /supportRequestBody\(form, candidate, sites\.siteId\)/);
  assert.match(source, /needsSite && !sites\.singleSiteMode && <SitePicker/);
});

test("#23 an approved request whose ticket was revoked at approval cannot be rejected in the UI", () => {
  assert.match(rejectBlockedLabel({ status: "approved" }, { entitlement_revoked: true }), /ghi nhận đã hoàn/);
  assert.equal(rejectBlockedLabel({ status: "pending" }, { entitlement_revoked: true }), "");
  assert.equal(rejectBlockedLabel({ status: "approved" }, { entitlement_revoked: false }), "");
  assert.match(approvalEffectNote({ source_type: "portal_order", payment_channel: "counter" }), /thu hồi/);
  assert.equal(approvalEffectNote({ source_type: "portal_order", payment_channel: "demo" }), "");
  assert.equal(approvalEffectNote({ source_type: "monthly_pass", payment_channel: "counter" }), "");
});


test("#76 rework: the admin sees open requests filed at sites the working screen cannot open", () => {
  const data = { visible: true,
    refund_requests: [{ id: "q1", site_id: 1, site_name: "Bãi cũ", site_active: true }, { id: "q3", site_id: 3, site_name: "Bãi đóng", site_active: false }],
    support_requests: [{ id: "t1", site_id: 1, site_name: "Bãi cũ", site_active: true }] };
  // Single-site mode hides every other site; multi-site mode only closed sites (the picker reaches active ones).
  assert.deepEqual(otherSiteRequests(data, "refund_requests", true).map((row) => row.id), ["q1", "q3"]);
  assert.deepEqual(otherSiteRequests(data, "refund_requests", false).map((row) => row.id), ["q3"]);
  assert.deepEqual(otherSiteRequests(data, "support_requests", true).map((row) => row.id), ["t1"]);
  // Not an admin (or an older server): nothing.
  assert.deepEqual(otherSiteRequests({ visible: false, refund_requests: [], support_requests: [] }, "refund_requests", true), []);
  assert.deepEqual(otherSiteRequests(null, "refund_requests", true), []);
  assert.equal(otherSiteName(data.refund_requests[0]), "Bãi cũ");
  assert.equal(otherSiteName(data.refund_requests[1]), "Bãi đóng (đã ngừng hoạt động)");
  // Actions use the row's own site; a site-less historical request stays on the working site.
  assert.equal(requestSitePath({ site_id: 1 }, 2), 1);
  assert.equal(requestSitePath({ site_id: null }, 2), 2);
  for (const file of ["RefundAdminPanel.jsx", "SupportAdminPanel.jsx"]) {
    const source = readFileSync(new URL(`../src/pages/Expansion/${file}`, import.meta.url), "utf8");
    assert.match(source, /\/other-site-requests/);
    assert.match(source, /requestSitePath\((dialogRow|selected), siteId\)/);
    assert.match(source, /requestSitePath\((row|detail\.data), siteId\)/);
    assert.match(source, /OTHER_SITE_CLOSED_LABEL/);
  }
  assert.match(OTHER_SITE_CLOSED_LABEL, /ngừng hoạt động/);
});
