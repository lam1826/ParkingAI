// Executes the real source text of loadOpenBalances + loadMoney from OverviewPage.jsx
// (JSX file cannot be imported by node, so the two plain-JS pieces are sliced out verbatim).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { settlementAmounts } from "../src/pages/ParkingSession/settlementAmounts.js";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src/pages/Expansion/", import.meta.url));
const page = readFileSync(root + "OverviewPage.jsx", "utf8").split(String.fromCharCode(13)).join("");
const shared = readFileSync(root + "shared.jsx", "utf8").split(String.fromCharCode(13)).join("");
const backend = {"sessions": [{"id": "active"}, {"id": "departed"}], "revenue": {"total_revenue": 25000, "payment_count": 1}, "quotes": {"active": {"status": 200, "data": {"parking_fee": 25000, "online_paid": 0, "balance_due": 25000}}, "departed": {"status": 409, "data": {"detail": {"code": "checkout_state_conflict", "message": "Ended"}}}}};

const start = page.indexOf("async function loadOpenBalances");
const loadOpenBalancesSrc = page.slice(start, page.indexOf("\n}\n", start) + 2);
const marker = "const loadMoney = useCallback(async () => ";
const loadMoneyStart = page.indexOf(marker) + marker.length;
const loadMoneyExpr = page.slice(loadMoneyStart, page.indexOf(", [prefix, today, financial]);", loadMoneyStart));
const itemsSrc = shared.match(/export const items = (.*);\n/)[1];

function build(read) {
  const factory = new Function("read", "settlementAmounts", `
    const items = ${itemsSrc};
    ${loadOpenBalancesSrc}
    return { loadOpenBalances, loadMoney: (prefix, today, financial) => ${loadMoneyExpr} };
  `);
  return factory(read, settlementAmounts);
}

// Mock api: replies with the real backend payloads captured by the pytest repro.
function mockRead(calls) {
  return async (path) => {
    calls.push(path);
    if (path.endsWith("/sessions")) return backend.sessions;
    if (path.endsWith("/revenue")) return backend.revenue;
    const id = path.split("/sessions/")[1]?.split("/")[0];
    const quote = backend.quotes[id];
    if (quote.status !== 200) {
      const error = new Error(`Request failed with status code ${quote.status}`);
      error.response = { status: quote.status, data: quote.data };
      throw error;
    }
    return quote.data;
  };
}

test("departed session is skipped while revenue and remaining open balance are retained", async () => {
  const calls = [];
  const { loadMoney } = build(mockRead(calls));
  let outcome;
  try {
    outcome = { ok: await loadMoney("/sites/1", "2026-10-05", true) };
  } catch (error) {
    outcome = { error };
  }
  assert.ok(calls.some(p => p.endsWith("/revenue")), "revenue was requested");
  assert.equal(outcome.ok.revenue.total_revenue, 25000);
  assert.deepEqual(outcome.ok.balance, { due: 25000, unpaid: 1 });
});

test("control: without the departed session the same code succeeds", async () => {
  const departed = Object.entries(backend.quotes).find(([, q]) => q.status !== 200)[0];
  const all = Array.isArray(backend.sessions) ? backend.sessions : backend.sessions.items;
  const remaining = all.filter(s => s.id !== departed);
  const calls = [];
  const inner = mockRead(calls);
  const read = async (path, params) => path.endsWith("/sessions") ? remaining : inner(path, params);
  const result = await build(read).loadMoney("/sites/1", "2026-10-05", true);
  assert.deepEqual(result.balance, { due: 25000, unpaid: 1 });
});
