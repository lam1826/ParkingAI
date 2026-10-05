// Integration round 2 (PORTAL), review 05/10/2026 #76 remainder (CL-LEDGER request 4):
// /me/sessions rows now carry `site_id` (portal_router.location), so the existing
// single-site filter leaves another site's stay out of the support-link choices.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { linkNeedsSite, supportLinkCandidates, supportRequestBody } from "../src/pages/Expansion/supportState.js";

const describe = { order: (row) => row.id, session: (row) => row.license_plate, receipt: (row) => row.id, refund_request: (row) => row.id };
// Shape of GET /api/v2/me/sessions items after the fix (see tests/test_fix20261005_integration_portal_session_site.py).
const sessions = [
  { id: "stay-here", license_plate: "30A-123.45", site_id: 2, slot_name: "A-01", zone_name: "Khu A" },
  { id: "stay-there", license_plate: "30A-123.45", site_id: 1, slot_name: "B-01", zone_name: "Khu B" },
  { id: "stay-slotless", license_plate: "30A-123.45", site_id: null, slot_name: null, zone_name: null },
];

test("#76 single-site mode does not offer another site's stay as a support link", () => {
  const scoped = supportLinkCandidates({ sessions }, describe, 2).session;
  assert.deepEqual(scoped.map((row) => row.id), ["stay-here", "stay-slotless"]);
  assert.deepEqual(scoped.map((row) => row.site_id), [2, null]);
  // Multi-site mode keeps every stay; the server routes each to its own site.
  assert.deepEqual(supportLinkCandidates({ sessions }, describe, null).session.map((row) => row.id), ["stay-here", "stay-there", "stay-slotless"]);
});

test("#76 a stay with a site keeps it authoritative; a stay without a slot asks for the receiving site", () => {
  const [here, slotless] = supportLinkCandidates({ sessions }, describe, 2).session;
  const form = { subject: " Xe bị trầy ", category: "session", message: " Kiểm tra giúp ", linked_type: "session" };
  assert.equal(linkNeedsSite(here), false);
  assert.equal("site_id" in supportRequestBody({ ...form, linked_id: here.id }, here, "2"), false);
  assert.equal(linkNeedsSite(slotless), true);
  assert.equal(supportRequestBody({ ...form, linked_id: slotless.id }, slotless, "2").site_id, 2);
});

test("#76 the support panel receives the raw /me/sessions rows (site_id is not dropped on the way)", () => {
  const portal = readFileSync(new URL("../src/pages/Expansion/CustomerPortal.jsx", import.meta.url), "utf8");
  assert.match(portal, /usePagedPortalList\("\/me\/sessions", sessionsPage, linked\)/);
  assert.match(portal, /<CustomerSupportPanel [^>]*sessions=\{sessions\.data\}/);
  const panel = readFileSync(new URL("../src/pages/Expansion/CustomerSupportPanel.jsx", import.meta.url), "utf8");
  assert.match(panel, /supportLinkCandidates\(\{ orders, sessions, receipts, refunds: refunds\?\.data \}/);
  const router = readFileSync(new URL("../../backend/expansion/portal_router.py", import.meta.url), "utf8");
  assert.match(router, /"site_id": zone\.site_id if zone else None/);
});
