// Executes the REAL source of useRemote (shared.jsx) and the hook part of
// SelectedStay (OperationsPanel.jsx) under a tiny hook runtime, fed with the
// representative backend quote and conflict responses.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = fileURLToPath(new URL("../src/", import.meta.url));
const mod = (p) => import(pathToFileURL(path.join(ROOT, p)).href);
const { getErrorMessage } = await mod("utils/errorMessage.js");
const { settlementAmounts } = await mod("pages/ParkingSession/settlementAmounts.js");
const { operationTypeName } = await mod("pages/Expansion/operationsState.js");
const { staffFeeActions } = await mod("pages/Expansion/sessionFeeState.js");

const shared = readFileSync(path.join(ROOT, "pages/Expansion/shared.jsx"), "utf8");
const panel = readFileSync(path.join(ROOT, "pages/Expansion/OperationsPanel.jsx"), "utf8");
const useRemoteSrc = shared.slice(shared.indexOf("export function useRemote"), shared.indexOf("export function useAction")).replace("export ", "");
const stayStart = panel.indexOf("function SelectedStay(");
const stayHookSrc = panel.slice(stayStart, panel.indexOf("  return <section", stayStart))
  + "  return { remote, quote, amounts, typeName, shownPlate: quote?.license_plate || session.license_plate, shownCheckIn: quote?.check_in_time || session.check_in_time };\n}\n";
const currentLine = panel.match(/const current = sessions\.data\?\.find\(row => row\.id === selected\?\.id\) \|\| selected;/)[0];
assert.ok(useRemoteSrc.includes('getErrorMessage(failure, "Không tải được dữ liệu. Vui lòng thử lại.")'));

function runtime() {
  let hooks = [], idx = 0, effects = [], dirty = false;
  const changed = (a, b) => !a || !b || a.length !== b.length || a.some((x, k) => !Object.is(x, b[k]));
  const useRef = (init) => { const i = idx++; if (!hooks[i]) hooks[i] = { current: init }; return hooks[i]; };
  const useState = (init) => {
    const i = idx++;
    if (!hooks[i]) { const h = { v: init }; h.set = (val) => { const nv = typeof val === "function" ? val(h.v) : val; if (!Object.is(nv, h.v)) { h.v = nv; dirty = true; } }; hooks[i] = h; }
    return [hooks[i].v, hooks[i].set];
  };
  const useCallback = (fn, deps) => { const i = idx++; if (!hooks[i] || changed(hooks[i].deps, deps)) hooks[i] = { fn, deps }; return hooks[i].fn; };
  const useEffect = (fn, deps) => {
    const i = idx++; const h = hooks[i];
    if (!h || changed(h.deps, deps)) {
      const old = h?.cleanup; const slot = { deps, cleanup: undefined }; hooks[i] = slot;
      effects.push(() => { old?.(); const c = fn(); slot.cleanup = typeof c === "function" ? c : undefined; });
    }
  };
  const SelectedStay = new Function("useCallback", "useEffect", "useRef", "useState", "getErrorMessage", "settlementAmounts", "operationTypeName", "staffFeeActions", "read",
    `${useRemoteSrc}\n${stayHookSrc}\nreturn SelectedStay;`)(useCallback, useEffect, useRef, useState, getErrorMessage, settlementAmounts, operationTypeName, staffFeeActions, async () => null);
  async function render(props) {
    let out;
    for (let n = 0; n < 50; n++) {
      idx = 0; dirty = false; out = SelectedStay(props);
      const run = effects; effects = []; run.forEach((e) => e());
      await new Promise((r) => setTimeout(r, 5));
      if (!dirty && !run.length) return out;
    }
    throw new Error("did not settle");
  }
  return { render };
}

test("departed selected stay shows the server terminal message without payment actions", async () => {
  const row = {"id": "0654dfce-8ff2-46df-bf20-a8a6c675559d", "vehicle_id": 1, "parking_slot_id": 1, "monthly_pass_id": null, "check_in_time": "2026-10-05T15:54:41+07:00", "check_out_time": null, "parking_fee": null, "status": "active", "created_at": "2026-10-05T08:54:41+00:00", "updated_at": "2026-10-05T08:54:41+00:00", "billing_basis": null, "monthly_coverage_end": null, "prepaid": null, "online_paid": 0, "paid_through": null, "balance_due": null, "license_plate": "30A-999.99", "slot_name": "A-01"};
  const activeQuote = {"session_id": "fixture-session", "license_plate": "30A-999.99", "check_in_time": "2026-10-05T15:54:41+07:00", "parking_fee": 0, "online_paid": 0, "balance_due": 0};
  const conflict = {"status": 409, "data": {"detail": {"code": "checkout_state_conflict", "message": "Lượt gửi không còn đang hoạt động. Hãy tra lịch sử xe ra."}}};
  let departed = false;
  const adapters = { loadQuote: async (id) => {
    if (departed) { const e = new Error("Request failed with status code 409"); e.response = { status: conflict.status, data: conflict.data }; throw e; }
    return { ...activeQuote, session_id: id };
  } };
  const reload = () => {};
  const currentOf = new Function("sessions", "selected", `${currentLine}\nreturn current;`);
  const props = (sessions, selected) => ({ session: currentOf(sessions, selected), sessions, vehicleTypes: [], slots: [], adapters, onCheckout() {}, onDetail() {}, onTicket() {} });
  const rt = runtime();

  // 1. Manager clicks the active car in the list.
  const listed = { data: [row], loading: false, error: "", reload };
  let out = await rt.render(props(listed, row));
  assert.equal(out.remote.error, "");
  assert.ok(out.amounts);

  // 2. Another tab checks the car out. 3. Manager clicks 'Làm mới dữ liệu'.
  departed = true;
  await rt.render(props({ ...listed, loading: true }, row));
  const refreshed = { data: [], loading: false, error: "", reload };
  out = await rt.render(props(refreshed, row));
  assert.equal(out.remote.error, "");
  assert.equal(out.remote.data?.terminal, true);
  assert.equal(out.remote.data.message, conflict.data.detail.message);
  assert.notEqual(out.remote.error, conflict.data.detail.message);
  assert.equal(out.quote, null);
  assert.equal(out.shownPlate, row.license_plate);

  // Subsequent refreshes keep the terminal state rather than a retry error.
  for (let i = 0; i < 3; i++) {
    await out.remote.reload();
    out = await rt.render(props(refreshed, row));
    assert.equal(out.remote.error, "");
  assert.equal(out.remote.data?.terminal, true);
  assert.equal(out.remote.data.message, conflict.data.detail.message);
  }
  // Contrast: the server's message exists on the error object.
});
