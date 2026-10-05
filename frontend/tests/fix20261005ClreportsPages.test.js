// Lane CL-REPORTS (review 2026-10-05): #63 chatbot lot picker, #71 /zones "Thêm khu vực",
// #73 header "Làm mới", #77 "Bãi đỗ" single-site scope.
//
// These tests execute the REAL page components. Each .jsx/.js file under src/ is compiled with the
// repo's own Vite (OXC) into a temporary directory and run under a small hooks renderer below
// (function components, keys/remounts, state, refs, effects, context and bubbling event handlers).
// Only leaves are stubbed: MUI widgets, icons, router links, the page header, the auth context,
// the permission hook and the HTTP client (a scripted fake: no network, no backend).
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(here, "..");
const SRC = path.join(FRONTEND, "src");
const vite = await import(pathToFileURL(path.join(FRONTEND, "node_modules/vite/dist/node/index.js")).href);
const OUT = mkdtempSync(path.join(tmpdir(), "parkingai-clreports-"));
test.after(() => rmSync(OUT, { recursive: true, force: true }));

// ---------------------------------------------------------------------------------------------
// Minimal hooks renderer
// ---------------------------------------------------------------------------------------------
const RUNTIME_SOURCE = String.raw`
export const Fragment = Symbol.for("clreports.fragment");
export function createElement(type, props, ...children) {
  const { key = null, ...rest } = props || {};
  if (children.length === 1) rest.children = children[0];
  else if (children.length > 1) rest.children = children;
  return { $$el: true, type, key, props: rest };
}
export function createContext(defaultValue) {
  const context = { defaultValue, stack: [] };
  context.Provider = { $$provider: context };
  return context;
}
export function useContext(context) {
  return context.stack.length ? context.stack[context.stack.length - 1] : context.defaultValue;
}
let frame = null;
function slot() { const index = frame.index; frame.index += 1; return [frame.inst, index]; }
const sameDeps = (a, b) => Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((value, index) => Object.is(value, b[index]));
export function useState(initial) {
  const [inst, index] = slot();
  if (!(index in inst.hooks)) {
    const hook = { value: typeof initial === "function" ? initial() : initial };
    hook.set = (next) => {
      if (inst.dead) return;
      const value = typeof next === "function" ? next(hook.value) : next;
      if (!Object.is(value, hook.value)) { hook.value = value; inst.root.dirty = true; }
    };
    inst.hooks[index] = hook;
  }
  return [inst.hooks[index].value, inst.hooks[index].set];
}
export function useRef(initial) {
  const [inst, index] = slot();
  if (!(index in inst.hooks)) inst.hooks[index] = { current: initial };
  return inst.hooks[index];
}
export function useMemo(compute, deps) {
  const [inst, index] = slot();
  const hook = inst.hooks[index];
  if (hook && sameDeps(hook.deps, deps)) return hook.value;
  const value = compute();
  inst.hooks[index] = { value, deps };
  return value;
}
export function useCallback(callback, deps) { return useMemo(() => callback, deps); }
export function useEffect(effect, deps) {
  const [inst, index] = slot();
  const hook = inst.hooks[index] || (inst.hooks[index] = { deps: undefined, cleanup: null, effect: true });
  if (hook.ran && sameDeps(hook.deps, deps)) return;
  inst.root.pending.push({ inst, hook, effect, deps });
}
export const useLayoutEffect = useEffect;
export function useId() { const ref = useRef(null); if (ref.current === null) ref.current = "id-" + Math.random().toString(36).slice(2); return ref.current; }
export default { createElement, Fragment, createContext, useContext, useState, useRef, useMemo, useCallback, useEffect, useLayoutEffect, useId };

function kill(inst) {
  inst.dead = true;
  for (const hook of inst.hooks) if (hook?.effect && typeof hook.cleanup === "function") hook.cleanup();
}
class Root {
  constructor() { this.instances = new Map(); this.pending = []; this.dirty = false; this.tree = null; }
  render(element) { this.element = element; this.commit(); }
  commit() {
    for (let pass = 0; pass < 100; pass += 1) {
      this.dirty = false;
      const seen = new Set();
      this.tree = this.node(this.element, "", seen, null);
      for (const [id, inst] of this.instances) if (!seen.has(id)) { kill(inst); this.instances.delete(id); }
      const effects = this.pending; this.pending = [];
      for (const { inst, hook, effect, deps } of effects) {
        if (inst.dead) continue;
        if (typeof hook.cleanup === "function") hook.cleanup();
        const cleanup = effect();
        hook.cleanup = typeof cleanup === "function" ? cleanup : null;
        hook.deps = deps; hook.ran = true;
      }
      if (!this.dirty) return;
    }
    throw new Error("render did not settle");
  }
  unmount() { for (const inst of this.instances.values()) kill(inst); this.instances.clear(); this.tree = null; }
  children(value, path, seen, parent) {
    if (Array.isArray(value)) return value.map((child, index) => this.node(child, path + "[" + (child?.key ?? index) + "]", seen, parent));
    return this.node(value, path + "[" + (value?.key ?? 0) + "]", seen, parent);
  }
  node(element, path, seen, parent) {
    if (element == null || typeof element === "boolean") return null;
    if (Array.isArray(element)) return this.children(element, path, seen, parent);
    if (typeof element !== "object" || !element.$$el) return element;
    const { type, props, key } = element;
    if (typeof type === "function") {
      const id = path + "<" + (type.name || "anonymous") + "#" + (key ?? "") + ">";
      seen.add(id);
      let inst = this.instances.get(id);
      if (!inst) { inst = { hooks: [], root: this, id }; this.instances.set(id, inst); }
      const previous = frame; frame = { inst, index: 0 };
      let output;
      try { output = type(props); } finally { frame = previous; }
      return this.node(output, id, seen, parent);
    }
    if (type && type.$$provider) {
      const context = type.$$provider;
      context.stack.push(props.value);
      try { return this.children(props.children, path + "<provider>", seen, parent); } finally { context.stack.pop(); }
    }
    if (type === Fragment) return this.children(props.children, path + "<fragment#" + (key ?? "") + ">", seen, parent);
    const host = { type, props, parent, children: null };
    host.children = this.children(props.children, path + "<" + type + "#" + (key ?? "") + ">", seen, host);
    return host;
  }
}
export function createRoot() { return new Root(); }
`;
writeFileSync(path.join(OUT, "runtime.mjs"), RUNTIME_SOURCE);
const RUNTIME = pathToFileURL(path.join(OUT, "runtime.mjs")).href;
const R = await import(RUNTIME);
const h = R.createElement;

function stub(name, source) {
  const file = path.join(OUT, `${name}.mjs`);
  writeFileSync(file, `import { createElement, createContext } from ${JSON.stringify(RUNTIME)};\n${source}`);
  return pathToFileURL(file).href;
}

const STUBS = {
  mui: stub("mui", `
const host = (tag) => function Mui({ children, ...props }) { return createElement(tag, props, children); };
export const Alert = host("mui-alert"), Box = host("div"), Button = host("button"), CircularProgress = host("progress");
export const MenuItem = host("option"), Stack = host("div"), TextField = host("mui-textfield"), Typography = host("span");
export const DialogActions = host("div"), DialogContent = host("div"), DialogTitle = host("h2");
export function Dialog({ open, children, ...props }) { return open ? createElement("dialog", props, children) : null; }
export function Snackbar({ open, children }) { return open ? createElement("snackbar", null, children) : null; }
`),
  icon: stub("icon", "export default function Icon() { return null; }"),
  router: stub("router", `
export function Link({ to, children, ...props }) { return createElement("a", { ...props, href: to }, children); }
export const useLocation = () => ({ pathname: "/" });
`),
  prototype: stub("prototype", `
export function PageHeader({ title, description, actions, children }) {
  return createElement("header", null, createElement("h1", null, title), description ? createElement("p", null, description) : null, actions || children || null);
}
export function WorkspaceTabs() { return null; }
export function PrototypeIcon() { return null; }
`),
  auth: stub("auth", "export const AuthContext = createContext({ user: null });"),
  permissions: stub("permissions", "export default function useCorePermissions() { return { canManageConfiguration: true }; }"),
  aiResult: stub("ai-result", "export default function AIResultContent() { return null; }"),
  api: stub("api", `
export const calls = [];
let handler = async () => { throw new Error("no fake API handler"); };
export function setHandler(next) { handler = next; calls.length = 0; }
const call = (method) => async (url, first, second) => {
  const config = method === "get" || method === "delete" ? first : second;
  const body = method === "get" || method === "delete" ? undefined : first;
  calls.push({ method, url, params: config?.params, body });
  return { data: await handler(method, url, config?.params, body) };
};
export default { get: call("get"), post: call("post"), put: call("put"), delete: call("delete"), defaults: {} };
`),
  siteFinance: stub("site-finance", `
import { useEffect } from ${JSON.stringify(RUNTIME)};
import api from "./api.mjs";
// Stands in for CL-LEDGER's SiteFinance: like the real one it loads its sections when it mounts.
export default function SiteFinance({ site }) {
  useEffect(() => { void api.get("/api/v2/sites/" + site.id + "/payments"); }, [site.id]);
  return createElement("section", { "data-finance-site": site.id });
}
`),
};
const fakeApi = await import(STUBS.api);

const BASE_OVERRIDES = {
  "react": RUNTIME,
  "@mui/material": STUBS.mui,
  "@mui/icons-material/Refresh": STUBS.icon,
  "@mui/icons-material/Add": STUBS.icon,
  "react-router-dom": STUBS.router,
  "components/common/PrototypeUI.jsx": STUBS.prototype,
  "context/AuthContext.jsx": STUBS.auth,
  "hooks/useCorePermissions.js": STUBS.permissions,
  "services/api.js": STUBS.api,
  "components/ai/AIResultContent.js": STUBS.aiResult,
};

let scenarioCount = 0;
/** Compile `entry` (path under src/) and everything it imports, except the given overrides. */
async function loadReal(entry, extraOverrides = {}) {
  const overrides = { ...BASE_OVERRIDES, ...extraOverrides };
  const dir = path.join(OUT, `scenario-${scenarioCount += 1}`);
  mkdirSync(dir);
  const cache = new Map();
  const resolveFile = (from, spec) => {
    const base = path.resolve(path.dirname(from), spec);
    for (const candidate of [base, `${base}.js`, `${base}.jsx`, path.join(base, "index.js")]) {
      if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
    }
    throw new Error(`cannot resolve ${spec} from ${from}`);
  };
  const importPattern = /((?:\bfrom|\bimport)\s*\(?\s*)(["'])([^"'\n]+)\2/g;
  async function compile(file) {
    if (cache.has(file)) return cache.get(file);
    const target = path.join(dir, `${path.relative(SRC, file).replace(/[\\/]/g, "__").replace(/\.jsx?$/, "")}.mjs`);
    const url = pathToFileURL(target).href;
    cache.set(file, url);
    const lang = file.endsWith(".jsx") ? "jsx" : "js";
    const out = await vite.transformWithOxc(readFileSync(file, "utf8"), file, { lang, jsx: { runtime: "classic", pragma: "__h", pragmaFrag: "__Fragment" } });
    let code = out.code;
    const mapping = new Map();
    for (const [, , , spec] of code.matchAll(importPattern)) {
      if (mapping.has(spec)) continue;
      if (overrides[spec]) { mapping.set(spec, overrides[spec]); continue; }
      if (!spec.startsWith(".")) throw new Error(`unmapped package "${spec}" imported by ${path.relative(SRC, file)}`);
      const resolved = resolveFile(file, spec);
      const relative = path.relative(SRC, resolved).split(path.sep).join("/");
      mapping.set(spec, overrides[relative] ?? await compile(resolved));
    }
    code = code.replace(importPattern, (all, head, quote, spec) => `${head}${JSON.stringify(mapping.get(spec))}`);
    writeFileSync(target, `import { createElement as __h, Fragment as __Fragment } from ${JSON.stringify(RUNTIME)};\n${code}`);
    return url;
  }
  return import(await compile(path.join(SRC, entry)));
}

// ---------------------------------------------------------------------------------------------
// Browser-ish globals and tree helpers
// ---------------------------------------------------------------------------------------------
class MemoryStorage {
  constructor() { this.map = new Map(); }
  get length() { return this.map.size; }
  key(index) { return [...this.map.keys()][index] ?? null; }
  getItem(key) { return this.map.has(key) ? this.map.get(key) : null; }
  setItem(key, value) { this.map.set(key, String(value)); }
  removeItem(key) { this.map.delete(key); }
  clear() { this.map.clear(); }
}
const confirmations = [];
let confirmAnswer = true;
for (const [name, value] of Object.entries({
  sessionStorage: new MemoryStorage(),
  localStorage: new MemoryStorage(),
  window: { addEventListener() {}, removeEventListener() {}, dispatchEvent() {}, confirm: (message) => { confirmations.push(message); return confirmAnswer; } },
  requestAnimationFrame: (callback) => setTimeout(callback, 0),
})) Object.defineProperty(globalThis, name, { value, configurable: true, writable: true });

async function settle(root, rounds = 40) {
  for (let round = 0; round < rounds; round += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    if (root.dirty) root.commit();
  }
}
function findAll(root, predicate) {
  const found = [];
  const walk = (node) => {
    if (node == null || typeof node !== "object") return;
    if (Array.isArray(node)) { node.forEach(walk); return; }
    if (predicate(node)) found.push(node);
    walk(node.children);
  };
  walk(root.tree);
  return found;
}
function textOf(node) {
  if (node == null || typeof node === "boolean") return "";
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (typeof node !== "object") return String(node);
  return textOf(node.children);
}
const pageText = (root) => textOf(root.tree);
/** React-style bubbling: the handler runs on the node, then on every host ancestor. */
function fire(node, handler, event = {}) {
  let stopped = false;
  const synthetic = { target: node, nativeEvent: {}, preventDefault() {}, stopPropagation() { stopped = true; }, ...event };
  for (let current = node; current && !stopped; current = current.parent) {
    const callback = current.props?.[handler];
    if (callback) callback({ ...synthetic, currentTarget: current });
  }
}
const buttonsNamed = (root, text) => findAll(root, (node) => node.type === "button" && (node.props["aria-label"] === text || textOf(node).trim() === text));
const countCalls = (predicate) => fakeApi.calls.filter(predicate).length;
const withSite = (rows, singleSiteId) => { globalThis.__PARKINGAI_CONFIG__ = singleSiteId == null ? { API_URL: "" } : { API_URL: "", SINGLE_SITE_ID: singleSiteId }; return rows; };

// ---------------------------------------------------------------------------------------------
// #63 — the chatbot lot picker must not close the chat
// ---------------------------------------------------------------------------------------------
test("#63 switching 'Bãi đang hỏi' keeps the chat open with the typed draft", async () => {
  withSite(null, null);
  sessionStorage.clear();
  fakeApi.setHandler(async (method, url) => {
    if (url === "/api/v2/sites") return [{ id: 1, name: "Bãi A" }, { id: 2, name: "Bãi B" }];
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: AIChatbot } = await loadReal("components/ai/AIChatbot.jsx");
  const { AuthContext } = await import(STUBS.auth);
  const root = R.createRoot();
  root.render(h(AuthContext.Provider, { value: { user: { id: 7, role: "admin" } } }, h(AIChatbot)));
  await settle(root);

  fire(findAll(root, (node) => String(node.props.className || "").includes("chat-launcher") && node.type === "button")[0], "onClick");
  await settle(root);
  const windows = () => findAll(root, (node) => node.type === "section" && node.props.className === "chat-window");
  assert.equal(windows().length, 1);
  const draft = () => findAll(root, (node) => node.props.id === "parking-chat-question")[0];
  fire(draft(), "onChange", { target: { value: "Doanh thu bãi B hôm nay?" } });
  await settle(root);

  const picker = findAll(root, (node) => node.type === "mui-textfield" && node.props.label === "Bãi đang hỏi")[0];
  assert.ok(picker, "the lot picker is shown in the general (multi-site) interface");
  fire(picker, "onChange", { target: { value: 2 } });
  await settle(root);

  assert.equal(windows().length, 1, "the chat window stays open after choosing another lot");
  assert.equal(draft().props.value, "Doanh thu bãi B hôm nay?");
  assert.equal(findAll(root, (node) => node.type === "mui-textfield" && node.props.label === "Bãi đang hỏi")[0].props.value, 2);
  root.unmount();
});

test("#63 a chat opened before the lot list arrives stays open (single-site config)", async () => {
  withSite(null, 2);
  sessionStorage.clear();
  let release;
  const sitesReady = new Promise((resolve) => { release = resolve; });
  fakeApi.setHandler(async (method, url) => {
    if (url === "/api/v2/sites") { await sitesReady; return [{ id: 1, name: "Bãi A" }, { id: 2, name: "Bãi B" }]; }
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: AIChatbot } = await loadReal("components/ai/AIChatbot.jsx");
  const { AuthContext } = await import(STUBS.auth);
  const root = R.createRoot();
  root.render(h(AuthContext.Provider, { value: { user: { id: 8, role: "manager" } } }, h(AIChatbot)));
  await settle(root);
  fire(findAll(root, (node) => node.type === "button" && String(node.props.className || "").includes("chat-launcher"))[0], "onClick");
  await settle(root);
  fire(findAll(root, (node) => node.props.id === "parking-chat-question")[0], "onChange", { target: { value: "Còn chỗ không?" } });
  await settle(root);

  release();
  await settle(root);
  assert.equal(findAll(root, (node) => node.type === "section" && node.props.className === "chat-window").length, 1);
  assert.equal(findAll(root, (node) => node.props.id === "parking-chat-question")[0].props.value, "Còn chỗ không?");
  root.unmount();
  globalThis.__PARKINGAI_CONFIG__ = undefined;
});

// ---------------------------------------------------------------------------------------------
// #73 — the page header "Làm mới" must reload the page data, not only the site list
// ---------------------------------------------------------------------------------------------
const SUMMARY = {
  period: "day", start_date: "2026-10-05", end_date: "2026-10-05", data_scope: "management", demo_mode: false,
  total_arrivals: 1, total_departures: 0, total_movements: 1, peak_hours: [], peak_movement_hours: [],
  daily_traffic: [], hourly_traffic: [], current_availability: { as_of: null, zones: [] },
  revenue: { parking_revenue: 0, monthly_pass_revenue: 0, prepaid_revenue: 0, refunds: 0, total_revenue: 0, demo_receipts: 0, demo_refunds: 0 },
};

test("#73 reports and AI pages: header 'Làm mới' re-fetches summary, AI status and history, keeping the chosen period", async () => {
  withSite(null, null);
  fakeApi.setHandler(async (method, url) => {
    if (url === "/api/v2/sites") return [{ id: 1, name: "Bãi 1", role: "manager" }];
    if (url === "/api/v2/sites/1/reports/summary") return SUMMARY;
    if (url === "/api/v2/sites/1/ai/status") return { enabled: false };
    if (url === "/api/v2/sites/1/ai/analyses") return [];
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: CoreAnalyticsPage } = await loadReal("pages/Expansion/CoreAnalyticsPage.jsx");
  for (const mode of ["reports", "ai"]) {
    const root = R.createRoot();
    root.render(h(CoreAnalyticsPage, { mode }));
    await settle(root);
    const summary = (period) => countCalls((call) => call.url === "/api/v2/sites/1/reports/summary" && (!period || call.params?.period === period));
    const status = () => countCalls((call) => call.url === "/api/v2/sites/1/ai/status");
    const history = () => countCalls((call) => call.url === "/api/v2/sites/1/ai/analyses");
    const periodSelect = findAll(root, (node) => node.type === "select" && textOf(node).includes("7 ngày đến ngày chọn"))[0];
    fire(periodSelect, "onChange", { target: { value: "week" } });
    await settle(root);
    const before = { week: summary("week"), status: status(), history: history() };
    assert.ok(before.week >= 1);

    const [refresh] = buttonsNamed(root, "Làm mới");
    assert.ok(refresh, "the page header has a 'Làm mới' button");
    fire(refresh, "onClick");
    await settle(root);

    assert.equal(summary("week"), before.week + 1, `${mode}: the report summary is fetched again for the chosen period`);
    assert.equal(status(), before.status + 1, `${mode}: AI status is fetched again`);
    assert.equal(history(), before.history + 1, `${mode}: the analysis history is fetched again`);
    root.unmount();
    fakeApi.calls.length = 0;
  }
});

test("#73 finance page: header 'Làm mới' reloads the finance sections", async () => {
  withSite(null, null);
  fakeApi.setHandler(async (method, url) => {
    if (url === "/api/v2/sites") return [{ id: 4, name: "Bãi 4", role: "staff" }];
    if (url === "/api/v2/sites/4/payments") return { items: [] };
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: SiteFinancePage } = await loadReal("pages/Expansion/SiteFinancePage.jsx", { "pages/Expansion/SiteFinance.jsx": STUBS.siteFinance });
  const root = R.createRoot();
  root.render(h(SiteFinancePage));
  await settle(root);
  const payments = () => countCalls((call) => call.url === "/api/v2/sites/4/payments");
  assert.equal(payments(), 1);
  fire(buttonsNamed(root, "Làm mới")[0], "onClick");
  await settle(root);
  assert.equal(payments(), 2, "shifts, receipts and revenue are loaded again");
  assert.equal(findAll(root, (node) => node.props["data-finance-site"] === 4).length, 1);
  root.unmount();
});

test("#73 site settings: header 'Làm mới' re-fetches the profile and asks before dropping unsaved edits", async () => {
  withSite(null, null);
  confirmations.length = 0;
  fakeApi.setHandler(async (method, url) => {
    if (url === "/api/v2/sites") return [{ id: 5, name: "Bãi 5", role: "manager" }];
    if (url === "/api/v2/sites/5/public-profile") return { address: "1 Đường A", can_edit: true, contact: {}, location: null, profile_updated_at: null };
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: SiteConfigurationPage } = await loadReal("pages/Expansion/SiteConfigurationPage.jsx");
  const root = R.createRoot();
  root.render(h(SiteConfigurationPage));
  await settle(root);
  const profiles = () => countCalls((call) => call.url === "/api/v2/sites/5/public-profile");
  const address = () => findAll(root, (node) => node.type === "mui-textfield" && node.props.label === "Địa chỉ")[0];
  assert.equal(profiles(), 1);
  assert.equal(address().props.value, "1 Đường A");

  fire(buttonsNamed(root, "Làm mới")[0], "onClick");
  await settle(root);
  assert.equal(profiles(), 2, "without edits the profile is fetched again at once");
  assert.equal(confirmations.length, 0);

  fire(address(), "onChange", { target: { value: "2 Đường B" } });
  await settle(root);
  confirmAnswer = false;
  fire(buttonsNamed(root, "Làm mới")[0], "onClick");
  await settle(root);
  assert.equal(confirmations.length, 1, "unsaved edits: the user is asked first");
  assert.equal(profiles(), 2, "declined: nothing is re-fetched");
  assert.equal(address().props.value, "2 Đường B", "declined: the typed address is kept");

  confirmAnswer = true;
  fire(buttonsNamed(root, "Làm mới")[0], "onClick");
  await settle(root);
  assert.equal(confirmations.length, 2);
  assert.equal(profiles(), 3);
  assert.equal(address().props.value, "1 Đường A", "confirmed: the saved profile is shown again");
  root.unmount();
});

// ---------------------------------------------------------------------------------------------
// #71 — /zones offers "Thêm khu vực" only when the server can create a zone from this form
// ---------------------------------------------------------------------------------------------
async function renderZonePage(scope) {
  withSite(null, 2);
  fakeApi.setHandler(async (method, url) => {
    if (url === "/api/v1/zones") return [{ id: 3, name: "Khu B", capacity: 10, is_active: true, site_id: 2 }];
    if (url === "/api/v1/zones/creation-scope") return scope;
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: ZonePage } = await loadReal("pages/Zone/ZonePage.jsx");
  const root = R.createRoot();
  root.render(h(ZonePage));
  await settle(root);
  return root;
}

test("#71 with several sites /zones hides 'Thêm khu vực' and points to the scoped form", async () => {
  const detail = "Hệ thống có nhiều bãi. Hãy tạo khu vực trong mục Vận hành bãi và chọn bãi cụ thể.";
  const root = await renderZonePage({ legacy_create_allowed: false, detail });
  assert.equal(findAll(root, (node) => node.type === "button" && textOf(node).includes("Thêm khu vực")).length, 0);
  const note = findAll(root, (node) => node.props.role === "note")[0];
  assert.ok(note, "an explanation replaces the button");
  assert.ok(textOf(note).includes(detail));
  assert.deepEqual(findAll(root, (node) => node.type === "a").filter((node) => findAll({ tree: note }, (inner) => inner === node).length).map((node) => node.props.href), ["/sites"]);
  assert.equal(buttonsNamed(root, "Sửa").length, 1, "existing zones stay editable");
  root.unmount();
  globalThis.__PARKINGAI_CONFIG__ = undefined;
});

test("#71 with one site /zones keeps 'Thêm khu vực'", async () => {
  const root = await renderZonePage({ legacy_create_allowed: true, detail: null });
  const add = findAll(root, (node) => node.type === "button" && textOf(node).includes("Thêm khu vực"));
  assert.equal(add.length, 1);
  fire(add[0], "onClick");
  await settle(root);
  assert.equal(findAll(root, (node) => node.type === "section" && String(node.props.className).includes("core-editor")).length, 1);
  assert.equal(findAll(root, (node) => node.props.role === "note").length, 0);
  root.unmount();
  globalThis.__PARKINGAI_CONFIG__ = undefined;
});

// ---------------------------------------------------------------------------------------------
// #77 — "Bãi đỗ" in single-site mode shows, counts and offers only the configured site
// ---------------------------------------------------------------------------------------------
test("#77 single-site 'Bãi đỗ' lists, counts and offers only the configured site's zones and slots", async () => {
  withSite(null, 2);
  fakeApi.setHandler(async (method, url) => {
    if (url === "/api/v1/zones") return [
      { id: 1, name: "Khu bãi một", capacity: 5, is_active: true, site_id: 1 },
      { id: 2, name: "Khu bãi hai", capacity: 5, is_active: true, site_id: 2 },
    ];
    if (url === "/api/v1/vehicle-types") return [{ id: 1, name: "Ô tô", is_active: true }];
    if (url === "/api/v1/parking-slots") return [
      { id: 11, slot_name: "M-01", zone_id: 1, vehicle_type_id: 1, is_active: true, is_occupied: true },
      { id: 12, slot_name: "M-02", zone_id: 1, vehicle_type_id: 1, is_active: true, is_occupied: false },
      { id: 21, slot_name: "H-01", zone_id: 2, vehicle_type_id: 1, is_active: true, is_occupied: false },
    ];
    if (url === "/api/v2/sites") return [{ id: 1, name: "Bãi một" }, { id: 2, name: "Bãi hai" }, { id: 3, name: "Bãi ba" }];
    if (url === "/api/v2/sites/2/availability") return { slots: [{ id: 21, is_occupied: false, available_now: true, reserved: false }] };
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: ParkingSlotPage } = await loadReal("pages/ParkingSlot/ParkingSlotPage.jsx");
  const root = R.createRoot();
  root.render(h(ParkingSlotPage));
  await settle(root);

  const text = pageText(root);
  assert.ok(text.includes("H-01"));
  assert.ok(!text.includes("M-01") && !text.includes("M-02"), "other sites' slots are not listed");
  const cards = findAll(root, (node) => node.type === "div" && /^slot /.test(String(node.props.className)));
  assert.deepEqual(cards.map((card) => textOf(card.children[0])), ["H-01"]);
  assert.deepEqual(cards.map((card) => textOf(card.children[1])), ["Còn nhận xe"], "no slot is shown as 'Chưa rõ khả dụng'");
  const stats = findAll(root, (node) => node.type === "span" && node.props.className === "stat-item").map(textOf);
  assert.deepEqual(stats.slice(0, 4), ["1còn nhận xe", "0đang có xe", "0giữ chỗ", "0ngừng phục vụ"]);
  assert.ok(text.includes("Bãi hai"), "the page names the lot it shows");
  const zoneOptions = (select) => findAll({ tree: select }, (node) => node.type === "option").map(textOf).filter((label) => label.startsWith("Khu "));
  const filter = findAll(root, (node) => node.type === "select" && textOf(node).includes("Tất cả khu vực"))[0];
  assert.deepEqual(zoneOptions(filter), ["Khu bãi hai"]);

  fire(findAll(root, (node) => node.type === "button" && textOf(node).includes("Thêm vị trí đỗ"))[0], "onClick");
  await settle(root);
  const editorZone = findAll(root, (node) => node.type === "select" && node.props.name === "zone_id")[0];
  assert.deepEqual(zoneOptions(editorZone), ["Khu bãi hai"], "a new slot can only go into this site's zones");
  root.unmount();
  globalThis.__PARKINGAI_CONFIG__ = undefined;
});

test("#77 without single-site mode the catalogue still shows every site", async () => {
  withSite(null, null);
  fakeApi.setHandler(async (method, url) => {
    if (url === "/api/v1/zones") return [
      { id: 1, name: "Khu bãi một", capacity: 5, is_active: true, site_id: 1 },
      { id: 2, name: "Khu bãi hai", capacity: 5, is_active: true, site_id: 2 },
    ];
    if (url === "/api/v1/vehicle-types") return [{ id: 1, name: "Ô tô", is_active: true }];
    if (url === "/api/v1/parking-slots") return [
      { id: 11, slot_name: "M-01", zone_id: 1, vehicle_type_id: 1, is_active: true, is_occupied: false },
      { id: 21, slot_name: "H-01", zone_id: 2, vehicle_type_id: 1, is_active: true, is_occupied: false },
    ];
    if (url === "/api/v2/sites") return [{ id: 1, name: "Bãi một" }, { id: 2, name: "Bãi hai" }];
    if (url === "/api/v2/sites/1/availability") return { slots: [{ id: 11, is_occupied: false, available_now: true }] };
    if (url === "/api/v2/sites/2/availability") return { slots: [{ id: 21, is_occupied: false, available_now: true }] };
    throw new Error(`unexpected ${method} ${url}`);
  });
  const { default: ParkingSlotPage } = await loadReal("pages/ParkingSlot/ParkingSlotPage.jsx");
  const root = R.createRoot();
  root.render(h(ParkingSlotPage));
  await settle(root);
  const text = pageText(root);
  assert.ok(text.includes("M-01") && text.includes("H-01"));
  root.unmount();
});
