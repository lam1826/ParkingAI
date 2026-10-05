// CL-AUTH #67: Nhật ký hoạt động asks for one bounded server page per view,
// debounces typed filters and aborts the request of an outdated view, instead
// of downloading the whole audit table on every keystroke.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  AUDIT_PAGE_SIZE, AUDIT_TEXT_FILTER_DELAY_MS, auditLogPageView, auditLogRequest, textFiltersPending,
} from "../src/pages/AuditLog/auditLogQuery.js";

// Fake backend mirroring routers/audit_log.py (ilike %username%, newest first, offset/limit).
const names = ["manager_a", "manager_b", "anonymous", "staff_01"];
const table = Array.from({ length: 3000 }, (_, i) => ({ id: i + 1, username: names[i % names.length] })).reverse();
function serve(params) {
  const rows = params.username ? table.filter((row) => row.username.includes(params.username)) : table;
  return rows.slice(params.skip, params.skip + params.limit);
}

test("one view is one bounded request, with a look-ahead row for 'Trang sau'", () => {
  const first = auditLogRequest({}, 0);
  assert.deepEqual(first.params, { skip: 0, limit: AUDIT_PAGE_SIZE + 1 });
  const view = auditLogPageView(serve(first.params));
  assert.equal(view.rows.length, AUDIT_PAGE_SIZE);
  assert.equal(view.hasNext, true);
  assert.equal(view.rows[0].id, 3000);

  const third = auditLogRequest({ username: " manage ", action: "LOGIN", success: "false" }, 2);
  assert.deepEqual(third.params, { skip: 50, limit: 26, action: "LOGIN", username: "manage", success: "false" });

  const last = auditLogRequest({}, 119); // rows 2976..3000 of 3000
  const lastView = auditLogPageView(serve(last.params));
  assert.equal(lastView.rows.length, 25);
  assert.equal(lastView.hasNext, false);
  assert.deepEqual(auditLogPageView(null), { rows: [], hasNext: false });
  assert.equal(auditLogRequest({}, -3).params.skip, 0);
});

test("typed filters wait for a pause; only changed text is pending", () => {
  assert.ok(AUDIT_TEXT_FILTER_DELAY_MS >= 250);
  assert.equal(textFiltersPending({ username: "man", requestId: "" }, { username: "", requestId: "" }), true);
  assert.equal(textFiltersPending({ username: "man", requestId: "" }, { username: "man", requestId: "" }), false);
  assert.equal(textFiltersPending({ username: "", requestId: "x" }, { username: "", requestId: "" }), true);
});

test("the page fetches one page per view, aborts stale views and debounces typing", async () => {
  const source = await readFile(new URL("../src/pages/AuditLog/AuditLogPage.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /requestAllOffsetPages/);
  assert.match(source, /api\.get\("\/api\/v1\/audit-logs", \{ params: request\.params, signal \}\)/);
  assert.match(source, /new AbortController\(\)/);
  assert.match(source, /controller\.abort\(\)/);
  assert.match(source, /setTimeout\(\(\) => \{ setApplied\(typed\); setPage\(0\); \}, AUDIT_TEXT_FILTER_DELAY_MS\)/);
  assert.match(source, /clearTimeout\(timer\)/);
  // Typing changes only the draft; the query follows the applied filters.
  assert.match(source, /value=\{typed\.username\}/);
  assert.match(source, /\}, \[action, success, applied, page\]\);/);
  assert.match(source, /disabled=\{!hasNext\}/);
});
