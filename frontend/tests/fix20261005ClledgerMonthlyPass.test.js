// Review 05/10/2026 CL-LEDGER #8 (renewal default), #19 (pass owner), #0 (counter site).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { customerForVehicle, ownerChoices, renewalDefaults, renewalEndsBeforeToday, withCounterSite } from "../src/pages/MonthlyPass/monthlyPassForm.js";

test("#8 renewing a lapsed pass defaults to a period starting today", () => {
  assert.deepEqual(renewalDefaults("2026-09-04", "2026-10-05"), { start_date: "2026-10-05", end_date: "2026-11-03" });
  // A pass still running renews from the day after it ends.
  assert.deepEqual(renewalDefaults("2026-10-20", "2026-10-05"), { start_date: "2026-10-21", end_date: "2026-11-19" });
  assert.deepEqual(renewalDefaults("2026-10-04", "2026-10-05"), { start_date: "2026-10-05", end_date: "2026-11-03" });
  assert.equal(renewalEndsBeforeToday({ end_date: "2026-10-04" }, "2026-10-05"), true);
  assert.equal(renewalEndsBeforeToday({ end_date: "2026-10-05" }, "2026-10-05"), false);
  assert.equal(renewalEndsBeforeToday({ end_date: "" }, "2026-10-05"), false);
});

const vehicles = [{ id: 1, customer_id: 10 }, { id: 2, customer_id: null }];
const customers = [{ id: 10, full_name: "A" }, { id: 11, full_name: "B" }];

test("#19 the pass customer is the vehicle owner; walk-in vehicles keep every customer", () => {
  assert.deepEqual(ownerChoices(vehicles, customers, "1").map((row) => row.id), [10]);
  assert.deepEqual(ownerChoices(vehicles, customers, 2).map((row) => row.id), [10, 11]);
  assert.deepEqual(ownerChoices(vehicles, customers, "").map((row) => row.id), [10, 11]);
  assert.equal(customerForVehicle(vehicles, customers, "1", 11), 10);
  assert.equal(customerForVehicle(vehicles, customers, 2, 11), 11);
  assert.equal(customerForVehicle(vehicles, customers, 2, 99), "");
});

test("#0 a single-site deployment records counter sales at its lot", () => {
  assert.deepEqual(withCounterSite({ price: 1 }, 2), { price: 1, site_id: 2 });
  assert.deepEqual(withCounterSite({ price: 1 }, null), { price: 1 });
});

test("dialog and hook use the shared decisions", () => {
  const dialog = readFileSync(new URL("../src/pages/MonthlyPass/components/MonthlyPassDialog.jsx", import.meta.url), "utf8");
  assert.match(dialog, /renewalDefaults\(pass\.end_date, toBusinessDateString\(\)\)/);
  assert.match(dialog, /ownerChoices\(vehicles, customers, form\.vehicle_id\)/);
  assert.match(dialog, /renewalElapsed/);
  assert.doesNotMatch(dialog, /nextStart\.setUTCDate/);
  const hook = readFileSync(new URL("../src/pages/MonthlyPass/hooks/useMonthlyPass.js", import.meta.url), "utf8");
  assert.match(hook, /withCounterSite\(formData, singleSiteId\(\)\)/);
});
