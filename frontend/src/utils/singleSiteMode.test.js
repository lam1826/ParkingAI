import test from "node:test";
import assert from "node:assert/strict";
import { scopeDemoCatalog, singleSiteId } from "./singleSiteMode.js";

test("single site catalog selects the configured site even when it is not first", () => {
  const rows = [{ id: 1 }, { id: 2 }, { id: 3 }];
  assert.deepEqual(scopeDemoCatalog("/sites", rows, { SINGLE_SITE_ID: 2 }), [{ id: 2 }]);
  assert.equal(rows.length, 3);
});

test("missing permission or inactive site does not select a different site", () => {
  assert.deepEqual(scopeDemoCatalog("/sites", [{ id: 3 }], { SINGLE_SITE_ID: 2 }), []);
  assert.deepEqual(scopeDemoCatalog("/sites", [], { SINGLE_SITE_ID: 2 }), []);
});

test("ticket catalog keeps its envelope and only exposes the selected site's plans", () => {
  for (const path of ["/plans", "/portal/admin/plans"]) {
    assert.deepEqual(scopeDemoCatalog(path, { items: [{ site_id: 3 }, { site_id: 2 }, { site_id: null }] },
      { SINGLE_SITE_ID: "2" }), { items: [{ site_id: 2 }] });
  }
});

test("historical records are preserved and default mode stays compatible", () => {
  const rows = [{ site_id: 3 }];
  assert.equal(scopeDemoCatalog("/me/receipts", rows, { SINGLE_SITE_ID: 2 }), rows);
  assert.equal(scopeDemoCatalog("/plans", rows, {}), rows);
  assert.equal(singleSiteId({}), null);
});

test("invalid configuration fails instead of silently expanding scope", () => {
  for (const value of [0, -2, 1.5, true, "oops", "2 OR 1", Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => singleSiteId({ SINGLE_SITE_ID: value }));
  }
  assert.throws(() => scopeDemoCatalog("/sites", {}, { SINGLE_SITE_ID: 2 }));
});
