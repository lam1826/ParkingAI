import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { transformWithOxc } from "vite";
import { staffFeeActions } from "../src/pages/Expansion/sessionFeeState.js";
import { settlementAmounts } from "../src/pages/ParkingSession/settlementAmounts.js";
import { admissionChoices, operationLookup, operationTypeName } from "../src/pages/Expansion/operationsState.js";
import { getErrorMessage } from "../src/utils/errorMessage.js";
import { createCheckoutFlow } from "../src/pages/ParkingSession/checkoutFlow.js";

const source = path => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");
const createElement = (type, props, ...children) => ({ type, props: { ...props, children: children.flat(Infinity) } });
const text = node => node == null || typeof node === "boolean" ? "" : typeof node !== "object" ? String(node) : (node.props?.children || []).map(text).join("");
function find(tree, predicate) {
  if (!tree || typeof tree !== "object") return [];
  return [...(predicate(tree) ? [tree] : []), ...(tree.props?.children || []).flatMap(child => find(child, predicate))];
}

// Shallow render the actual components, with real useRemote and separate hook
// state per component. Only the API and unrelated UI leaves are substituted.
function runtime() {
  const stores = new Map();
  let hooks, index, effects = [], dirty;
  const changed = (before, after) => !before || before.length !== after.length || before.some((value, i) => !Object.is(value, after[i]));
  const useState = initial => {
    const i = index++;
    if (!hooks[i]) {
      const entry = { value: typeof initial === "function" ? initial() : initial };
      entry.set = value => { const next = typeof value === "function" ? value(entry.value) : value; if (!Object.is(next, entry.value)) { entry.value = next; dirty = true; } };
      hooks[i] = entry;
    }
    return [hooks[i].value, hooks[i].set];
  };
  const useRef = initial => { const i = index++; return hooks[i] ||= { current: initial }; };
  const useCallback = (fn, deps) => { const i = index++; if (!hooks[i] || changed(hooks[i].deps, deps)) hooks[i] = { fn, deps }; return hooks[i].fn; };
  const useEffect = (fn, deps) => {
    const i = index++;
    if (!hooks[i] || changed(hooks[i].deps, deps)) {
      const previous = hooks[i]?.cleanup, entry = { deps };
      hooks[i] = entry;
      effects.push(() => { previous?.(); entry.cleanup = fn(); });
    }
  };
  const useSyncExternalStore = (subscribe, snapshot) => { useEffect(() => subscribe(() => { dirty = true; }), [subscribe]); return snapshot(); };
  const bindings = { useState, useRef, useCallback, useEffect, useSyncExternalStore, createElement, Fragment: "fragment" };
  const shared = source("pages/Expansion/shared.jsx");
  const remote = shared.slice(shared.indexOf("export function useRemote"), shared.indexOf("export function useAction")).replace("export ", "");
  bindings.useRemote = new Function(...Object.keys(bindings), "getErrorMessage", `${remote}; return useRemote;`)(...Object.values(bindings), getErrorMessage);
  return {
    bindings,
    async render(component, props) {
      if (!stores.has(component)) stores.set(component, []);
      for (let turn = 0; turn < 30; turn++) {
        hooks = stores.get(component); index = 0; dirty = false;
        const tree = component(props), pending = effects;
        effects = []; pending.forEach(effect => effect());
        await new Promise(resolve => setTimeout(resolve, 2));
        if (!dirty && !pending.length) return tree;
      }
      throw new Error("Component did not settle");
    },
  };
}

async function compile(path, name, bindings) {
  const input = source(path).replace(/^import[\s\S]*?;\s*/gm, "").replace("export default function", "function");
  const { code } = await transformWithOxc(input, path, { lang: "jsx", jsx: { runtime: "classic", pragma: "createElement", pragmaFrag: "Fragment" } });
  return new Function(...Object.keys(bindings), `${code}; return ${name};`)(...Object.values(bindings));
}

const quote = { session_id: "stay-79", license_plate: "30A12345", parking_fee: 25000, online_paid: 0, balance_due: 25000,
  check_in_time: "2026-10-05T12:00:00+07:00", duration_minutes: 60 };
const disabled = { enabled: false, message: "Bãi chỉ nhận thanh toán tại quầy." };
const enabled = { enabled: true, supported: true, session_status: "active" };

async function feePanel(status) {
  const rt = runtime(), reads = [], intents = [];
  const panel = await compile("pages/Expansion/OperationsPanel.jsx", "OperationsPanel", {
    ...rt.bindings, Alert: "alert", Button: "button", CameraOperations: "camera", OperationIcon: "icon",
    admissionChoices, operationLookup, operationTypeName, settlementAmounts, staffFeeActions,
    items: value => value, read: async path => { reads.push(path); if (status instanceof Error) throw status; return status; }, send: async () => {},
    money: String, dateTime: String, formatParkingDuration: String, PageControls: "pages",
    BillingBasisDetails: "basis", PrepaidDetails: "prepaid", useAction: () => ({ busy: false }),
  });
  const session = { id: quote.session_id, status: "active", license_plate: quote.license_plate };
  const tree = await rt.render(panel, {
    site: { id: 7 }, selected: session, sessions: { data: [session] }, availability: { data: { slots: [] } },
    vehicleTypes: { data: [] }, page: { page: 0, size: 25 }, action: { busy: false },
    adapters: { loadQuote: async () => quote }, onCheckout: (...args) => intents.push(args),
  });
  const selected = find(tree, node => node.type?.name === "SelectedStay")[0];
  return { tree: await rt.render(selected.type, selected.props), reads, intents };
}

for (const [label, status, primary, secondary] of [
  ["off", disabled, "Thu tiền mặt", "Chuyển khoản"],
  ["on", enabled, "Tạo QR cho khách", "Thu tiền mặt"],
]) test(`staff fee panel with payOS ${label} offers the available payment actions`, async () => {
  const h = await feePanel(status);
  const buttons = find(h.tree, node => node.type === "button");
  const first = buttons.find(node => node.props.className === "button primary");
  const second = buttons.find(node => node.props.className === "button secondary");
  assert.equal(text(first), primary);
  assert.equal(text(second), secondary);
  assert.deepEqual(h.reads, ["/sites/7/sessions/stay-79/payment-status"]);
  first.props.onClick(); second.props.onClick();
  assert.deepEqual(h.intents, status.enabled ? [["stay-79", "online"], ["stay-79", "cash"]] : [["stay-79", "cash"], ["stay-79", "transfer"]]);
  if (!status.enabled) {
    assert.equal(buttons.some(node => text(node).includes("QR")), false);
    assert.ok(text(h.tree).includes(disabled.message));
  }
});

test("control: failed payment-status read keeps staff cash and transfer actions", async () => {
  const h = await feePanel(new Error("offline"));
  const buttons = find(h.tree, node => node.type === "button");
  assert.equal(text(buttons.find(node => node.props.className === "button primary")), "Thu tiền mặt");
  assert.equal(text(buttons.find(node => node.props.className === "button secondary")), "Chuyển khoản");
  assert.ok(text(h.tree).includes("Chưa xác nhận được thanh toán QR"));
});

async function checkout(status, initialOnline) {
  const rt = runtime(), reads = [], writes = [];
  const components = Object.fromEntries(["Alert", "Box", "Button", "Checkbox", "CircularProgress", "Dialog", "DialogActions", "DialogContent",
    "DialogTitle", "FormControl", "FormControlLabel", "FormLabel", "Radio", "RadioGroup", "Stack", "Typography"].map(name => [name, name]));
  const fullQuote = { ...quote, quote_token: "signed-79", quoted_at: "2026-10-05T13:00:00+07:00", expires_at: "2026-10-05T13:05:00+07:00" };
  const dialog = await compile("pages/ParkingSession/components/CheckoutDialog.jsx", "CheckoutDialog", {
    ...rt.bindings, ...components, staffFeeActions, createCheckoutFlow, settlementAmounts,
    read: async path => { reads.push(path); if (status instanceof Error) throw status; return status; },
    formatBusinessDateOnly: String, formatBusinessTimestamp: String, formatParkingFee: String, formatParkingDuration: String,
    BillingBasisDetails: "basis", PrepaidDetails: "prepaid", SessionFeePayment: "SessionFeePayment",
    singleSiteId: () => 1, parkingSessionService: {}, localStorage: { getItem: () => "test-token" },
    window: { setInterval: () => 1, clearInterval() {}, addEventListener() {}, removeEventListener() {} },
  });
  const props = { sessionId: "stay-79", siteId: 7, initialOnline, initialPaymentMethod: "transfer",
    loadQuote: async () => fullQuote, confirmCheckout: async (id, body) => { writes.push({ id, body }); return { id, status: "completed" }; },
    onClose() {}, onCompleted() {} };
  return { render: () => rt.render(dialog, props), reads, writes };
}

for (const [label, status] of [["off", disabled], ["on", enabled]]) test(`checkout with payOS ${label} keeps only available payment UI`, async () => {
  const h = await checkout(status, !status.enabled);
  let tree = await h.render();
  assert.deepEqual(h.reads, ["/sites/7/sessions/stay-79/payment-status"]);
  const qrButton = find(tree, node => node.type === "Button" && text(node) === "Xem thanh toán QR của lượt này")[0];
  assert.equal(Boolean(qrButton), status.enabled);
  if (status.enabled) {
    qrButton.props.onClick(); tree = await h.render();
    assert.equal(find(tree, node => node.type === "SessionFeePayment").length, 1);
    assert.equal(find(tree, node => node.type === "RadioGroup").length, 0);
    assert.equal(find(tree, node => node.type === "Button" && text(node) === "Đã thu tiền — cho xe ra")[0].props.disabled, true);
  } else {
    assert.equal(find(tree, node => node.type === "SessionFeePayment").length, 0);
    assert.equal(find(tree, node => node.type === "RadioGroup")[0].props.value, "transfer");
    assert.ok(find(tree, node => node.type === "Alert" && node.props.severity === "info").some(node => text(node).includes(disabled.message)));
    const confirmation = find(tree, node => node.type === "FormControlLabel" && node.props.control?.type === "Checkbox")[0];
    confirmation.props.control.props.onChange({ target: { checked: true } });
    tree = await h.render();
    const submit = find(tree, node => node.type === "Button" && text(node) === "Đã thu tiền — cho xe ra")[0];
    assert.equal(submit.props.disabled, false);
    submit.props.onClick(); await h.render();
    assert.deepEqual(h.writes, [{ id: "stay-79", body: { quote_token: "signed-79", payment_confirmed: true, payment_method: "transfer" } }]);
  }
});

test("control: unavailable payment status falls back from an initial QR dialog", async () => {
  const h = await checkout(new Error("offline"), true);
  const tree = await h.render();
  assert.equal(find(tree, node => node.type === "SessionFeePayment").length, 0);
  assert.equal(find(tree, node => node.type === "RadioGroup")[0].props.value, "transfer");
  assert.ok(find(tree, node => node.type === "Alert").some(node => text(node).includes("Chưa xác nhận được thanh toán QR")));
  assert.equal(find(tree, node => node.type === "Button" && text(node) === "Đã thu tiền — cho xe ra")[0].props.disabled, true);
});

for (const intent of ["cash", "transfer", "online"]) test(`site checkout preserves the ${intent} payment intent`, async () => {
  const workspace = source("pages/Expansion/SitesWorkspace.jsx");
  const start = workspace.indexOf("<CheckoutDialog key="), end = workspace.indexOf("/>}", start);
  const { code } = await transformWithOxc(`function mount() { return (${workspace.slice(start, end + 2)}); }`, "mount.jsx",
    { lang: "jsx", jsx: { runtime: "classic", pragma: "createElement", pragmaFrag: "Fragment" } });
  const factory = new Function("createElement", "CheckoutDialog", "site", "checkout", "checkoutIntent", "adapters", "closeCheckout", `${code}; return mount;`);
  const mount = factory(createElement, "checkout", { id: 7 }, "stay-79", intent, {}, () => {});
  const node = mount();
  assert.equal(node.props.initialOnline, intent === "online");
  assert.equal(node.props.initialPaymentMethod, intent === "online" ? "" : intent);
});
