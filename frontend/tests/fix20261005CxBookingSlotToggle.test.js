import { Buffer } from "node:buffer";
// Executes the REAL OperationsPanel.jsx (compiled with the repo's own Vite/OXC) under a
// tiny hooks runtime, drives the "Chọn vị trí nhận xe" / "Tự xếp chỗ" toggle and the
// check-in form, and records what send() is called with. Read-only w.r.t. the repo.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(here, "..");
const SRC = `${FRONTEND}/src/pages/Expansion/OperationsPanel.jsx`;
const vite = await import(pathToFileURL(path.join(FRONTEND, "node_modules/vite/dist/node/index.js")).href);

const stubReact = "data:text/javascript;base64," + Buffer.from("// Minimal hooks runtime for driving a single function component without a DOM.\nexport const Fragment = Symbol(\"Fragment\");\nexport function createElement(type, props, ...children) {\n  return { type, props: { ...(props || {}), children: children.flat(Infinity) } };\n}\nconst store = { slots: [], index: 0, dirty: false };\nexport function __reset() { store.slots = []; store.index = 0; }\nexport function __beginRender() { store.index = 0; }\nexport function useState(initial) {\n  const i = store.index++;\n  if (!(i in store.slots)) {\n    const holder = { value: typeof initial === \"function\" ? initial() : initial };\n    holder.set = next => { holder.value = typeof next === \"function\" ? next(holder.value) : next; };\n    store.slots[i] = holder;\n  }\n  const holder = store.slots[i];\n  return [holder.value, holder.set];\n}\nexport function useRef(initial) {\n  const i = store.index++;\n  if (!(i in store.slots)) store.slots[i] = { current: initial };\n  return store.slots[i];\n}\nexport function useCallback(fn) { store.index++; return fn; }\nexport function useEffect() { store.index++; }\nexport function useMemo(fn) { store.index++; return fn(); }\nexport default { createElement, Fragment, useState, useRef, useCallback, useEffect, useMemo };\n").toString("base64");
const stubMisc = "data:text/javascript;base64," + Buffer.from("// Stubs for imports that are not under test (shallow render: never invoked).\nexport const Alert = function Alert() { return null; };\nexport const Button = function Button() { return null; };\nexport default function Stub() { return null; }\nexport const PageControls = function PageControls() { return null; };\nexport const items = data => Array.isArray(data) ? data : data?.items || [];\nexport const read = async () => [];\nexport const sent = [];\nexport const send = async (path, body) => { sent.push({ path, body }); return { session_id: \"s-new\", license_plate: body.license_plate }; };\nexport const dateTime = v => String(v ?? \"—\");\nexport const money = v => String(v ?? 0);\nexport const useAction = () => ({ run: async () => {}, busy: false });\nexport const useRemote = () => ({ data: null, loading: false, error: \"\" });\nexport const settlementAmounts = () => null;\nexport const formatParkingDuration = () => \"\";\n").toString("base64");
const realState = pathToFileURL(`${FRONTEND}/src/pages/Expansion/operationsState.js`).href;

const source = readFileSync(SRC, "utf8");
const out = await vite.transformWithOxc(source, SRC, { lang: "jsx", jsx: { runtime: "classic", pragma: "createElement", pragmaFrag: "Fragment" } });
const map = {
  "react": stubReact, "@mui/material": stubMisc, "./CameraOperations.jsx": stubMisc, "./OperationIcon": stubMisc,
  "./operationsState": realState, "./shared": stubMisc, "../ParkingSession/settlementAmounts": stubMisc,
  "../ParkingSession/sessionPresentation": stubMisc, "../ParkingSession/components/BillingBasisDetails": stubMisc,
  "../ParkingSession/components/PrepaidDetails": stubMisc,
  "./sessionFeeState": pathToFileURL(`${FRONTEND}/src/pages/Expansion/sessionFeeState.js`).href,
};
let code = out.code.replace(/from\s+["']([^"']+)["']/g, (m, spec) => {
  if (!(spec in map)) throw new Error(`unmapped import ${spec}`);
  return `from ${JSON.stringify(map[spec])}`;
});
code = `import { createElement, Fragment } from ${JSON.stringify(stubReact)};\n` + code;
const compiled = "data:text/javascript;base64," + Buffer.from(code).toString("base64");
const React = await import(stubReact);
const misc = await import(stubMisc);
const OperationsPanel = (await import(compiled)).default;

// ---------- tiny tree helpers ----------
const text = node => node == null || typeof node === "boolean" ? "" : typeof node !== "object" ? String(node) : (node.props?.children || []).map(text).join("");
function walk(node, fn) { if (!node || typeof node !== "object") return; if (Array.isArray(node)) return node.forEach(n => walk(n, fn)); fn(node); (node.props?.children || []).forEach(c => walk(c, fn)); }
const findAll = (tree, pred) => { const r = []; walk(tree, n => { if (pred(n)) r.push(n); }); return r; };
const button = (tree, label) => findAll(tree, n => n.type === "button" && text(n).includes(label))[0];
const byId = (tree, id) => findAll(tree, n => n.props?.id === id)[0];

function harness(slots) {
  React.__reset();
  misc.sent.length = 0;
  const props = {
    site: { id: 1 },
    availability: { data: { occupied: 0, slots }, loading: false, error: "" },
    vehicleTypes: { data: [{ id: 1, name: "Ô tô", requires_plate: true, is_active: true }], loading: false, error: "" },
    sessions: { data: [], loading: false, error: "" },
    page: { page: 0, size: 25, setPage() {} },
    action: { busy: false, run: async (op, msg, onOk) => { const r = await op(); onOk?.(r); } },
    adapters: {}, selected: null, onSelect() {}, onCheckout() {}, onDetail() {}, onTicket() {},
    onReservations() {}, onRefresh: async () => {},
  };
  const render = () => { React.__beginRender(); return OperationsPanel(props); };
  return { props, render };
}
const A1 = { id: 11, slot_name: "A1", zone_name: "Z", vehicle_type_id: 1, available_now: true };
const A2 = { id: 12, slot_name: "A2", zone_name: "Z", vehicle_type_id: 1, available_now: true };
const ev = { preventDefault() {} };

test("control: never choosing a slot -> request has no parking_slot_id", async () => {
  const h = harness([A1, A2]);
  let tree = h.render();
  byId(tree, "operation-plate").props.onChange({ target: { value: "51K-12345" } });
  tree = h.render();
  await findAll(tree, n => n.type === "form")[0].props.onSubmit(ev);
  assert.equal(misc.sent.length, 1);
  assert.equal("parking_slot_id" in misc.sent[0].body, false);
});

test("manual slot is omitted after toggling back to automatic placement", async () => {
  const h = harness([A1, A2]);
  let tree = h.render();
  button(tree, "Chọn vị trí nhận xe").props.onClick();
  tree = h.render();
  byId(tree, "operation-slot").props.onChange({ target: { value: "11" } });
  tree = h.render();
  assert.equal(byId(tree, "operation-slot").props.value, 11);
  const back = button(tree, "Tự xếp chỗ");
  assert.ok(back, "toggle now labelled 'Tự xếp chỗ'");
  back.props.onClick();
  tree = h.render();
  assert.equal(byId(tree, "operation-slot"), undefined, "slot picker hidden => UI says auto placement");
  byId(tree, "operation-plate").props.onChange({ target: { value: "51K-12345" } });
  tree = h.render();
  await findAll(tree, n => n.type === "form")[0].props.onSubmit(ev);
  assert.equal("parking_slot_id" in misc.sent[0].body, false);
});

test("automatic placement remains enabled when the formerly selected slot fills", async () => {
  const h = harness([A1, A2]);
  let tree = h.render();
  button(tree, "Chọn vị trí nhận xe").props.onClick();
  tree = h.render();
  byId(tree, "operation-slot").props.onChange({ target: { value: "11" } });
  tree = h.render();
  button(tree, "Tự xếp chỗ").props.onClick();
  tree = h.render();
  byId(tree, "operation-plate").props.onChange({ target: { value: "51K-12345" } });
  // Another lane admits a car into A1; availability reloads.
  h.props.availability = { data: { occupied: 1, slots: [{ ...A1, available_now: false }, A2] }, loading: false, error: "" };
  tree = h.render();
  const submit = findAll(tree, n => n.type === "button" && n.props.type === "submit")[0];
  const warning = text(tree).includes("Vị trí đã chọn không còn trống");
  assert.equal(submit.props.disabled, false);
  assert.equal(warning, false, "no explanation visible");
  await findAll(tree, n => n.type === "form")[0].props.onSubmit(ev);
  assert.equal(misc.sent.length, 1);
});

test("declared reception carries only its selected booking until the vehicle changes", async () => {
  const h=harness([A1,A2]);
  Object.assign(h.props,{initialBookingId:'booking-context',initialPlate:'51K-12345',initialTypeId:1,initialAction:'check_in'});
  let tree=h.render();
  byId(tree,'operation-plate').props.onChange({target:{value:'51K12345'}});
  tree=h.render();
  await findAll(tree,n=>n.type==='form')[0].props.onSubmit(ev);
  assert.equal(misc.sent[0].body.declared_booking_id,'booking-context');
  const changed=harness([A1,A2]);
  Object.assign(changed.props,{initialBookingId:'booking-context',initialPlate:'51K-12345',initialTypeId:1,initialAction:'check_in'});
  tree=changed.render();
  byId(tree,'operation-plate').props.onChange({target:{value:'51K-54321'}});
  tree=changed.render();
  await findAll(tree,n=>n.type==='form')[0].props.onSubmit(ev);
  assert.equal('declared_booking_id' in misc.sent[0].body,false);
});
