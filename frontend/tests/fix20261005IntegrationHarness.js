// Shared harness for the integration round-2 tests of review 05/10/2026 (agent MONEY).
//
// It executes REAL page components: each .jsx/.js file under src/ is compiled with the repo's own
// Vite (OXC) into a temporary directory and run under a small hooks renderer (function components,
// keys/remounts, state, refs, effects, context and bubbling event handlers). Only leaves are stubbed:
// MUI widgets, icons, router, page header, contexts and the HTTP client (a scripted fake: no network).
// Same approach as tests/fix20261005ClreportsPages.test.js (CL-REPORTS); this file is not a test.
import test from "node:test";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(here, "..");
const SRC = path.join(FRONTEND, "src");
const vite = await import(pathToFileURL(path.join(FRONTEND, "node_modules/vite/dist/node/index.js")).href);
const OUT = mkdtempSync(path.join(tmpdir(), "parkingai-integration-r2-"));
test.after(() => rmSync(OUT, { recursive: true, force: true }));

const RUNTIME_SOURCE = String.raw`
export const Fragment = Symbol.for("integration.fragment");
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
    // Like React, an update queued on an unmounted component is dropped (its updater never runs).
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
export const R = await import(RUNTIME);
export const h = R.createElement;

export function stub(name, source) {
  const file = path.join(OUT, `${name}.mjs`);
  writeFileSync(file, `import { createElement, createContext } from ${JSON.stringify(RUNTIME)};\n${source}`);
  return pathToFileURL(file).href;
}

export const STUBS = {
  mui: stub("mui", `
const host = (tag) => function Mui({ children, ...props }) { return createElement(tag, props, children); };
export const Alert = host("mui-alert"), Box = host("div"), Button = host("button"), CircularProgress = host("progress");
export const MenuItem = host("option"), Stack = host("div"), TextField = host("mui-textfield"), Typography = host("span");
export const DialogActions = host("div"), DialogContent = host("div"), DialogTitle = host("h2");
export const Tabs = host("mui-tabs"), Tab = host("mui-tab");
export function Dialog({ open, children, ...props }) { return open ? createElement("dialog", props, children) : null; }
`),
  icon: stub("icon", "export default function Icon() { return null; }"),
  router: stub("router", `
export const location = { search: "" };
export function Link({ to, children, ...props }) { return createElement("a", { ...props, href: to }, children); }
export const useLocation = () => ({ pathname: "/" });
export function useSearchParams() {
  return [new URLSearchParams(location.search), (next) => { location.search = new URLSearchParams(next).toString(); }];
}
`),
  prototype: stub("prototype", `
export function PageHeader({ title, description, actions, children }) {
  return createElement("header", null, createElement("h1", null, title), description ? createElement("p", null, description) : null, actions || children || null);
}
export function WorkspaceTabs() { return null; }
export function PrototypeIcon() { return null; }
`),
  expansion: stub("expansion", "export const useExpansion = () => ({ demo_payments_enabled: false });"),
  empty: stub("empty", "export default function Empty() { return null; }"),
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
};
export const fakeApi = await import(STUBS.api);
export const fakeRouter = await import(STUBS.router);

const BASE_OVERRIDES = {
  "react": RUNTIME,
  "@mui/material": STUBS.mui,
  "@mui/icons-material/Refresh": STUBS.icon,
  "react-router-dom": STUBS.router,
  "components/common/PrototypeUI.jsx": STUBS.prototype,
  "context/ExpansionContext.jsx": STUBS.expansion,
  "services/api.js": STUBS.api,
};

let scenarioCount = 0;
/**
 * Compile `entry` (path under src/) and everything it imports, except the given overrides. Every call
 * produces fresh module instances, i.e. it behaves like a page reload (module state is gone).
 */
export async function loadReal(entry, extraOverrides = {}) {
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

export class MemoryStorage {
  constructor() { this.map = new Map(); }
  get length() { return this.map.size; }
  key(index) { return [...this.map.keys()][index] ?? null; }
  getItem(key) { return this.map.has(key) ? this.map.get(key) : null; }
  setItem(key, value) { this.map.set(key, String(value)); }
  removeItem(key) { this.map.delete(key); }
  clear() { this.map.clear(); }
}
/** Storage that refuses every access, like a browser with site data blocked. */
export const blockedStorage = {
  getItem() { throw new Error("SecurityError: storage blocked"); },
  setItem() { throw new Error("SecurityError: storage blocked"); },
  removeItem() { throw new Error("SecurityError: storage blocked"); },
};
export function setGlobal(name, value) {
  Object.defineProperty(globalThis, name, { value, configurable: true, writable: true });
}
setGlobal("sessionStorage", new MemoryStorage());
setGlobal("localStorage", new MemoryStorage());
setGlobal("window", { addEventListener() {}, removeEventListener() {}, dispatchEvent() {}, confirm: () => true });
setGlobal("requestAnimationFrame", (callback) => setTimeout(callback, 0));
globalThis.__PARKINGAI_CONFIG__ = { API_URL: "" };

export async function settle(root, rounds = 40) {
  for (let round = 0; round < rounds; round += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    if (root.dirty) root.commit();
  }
}
export function findAll(root, predicate) {
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
export function textOf(node) {
  if (node == null || typeof node === "boolean") return "";
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (typeof node !== "object") return String(node);
  return textOf(node.children);
}
/** React-style bubbling: the handler runs on the node, then on every host ancestor. */
export function fire(node, handler, event = {}) {
  let stopped = false;
  const synthetic = { target: node, nativeEvent: {}, preventDefault() {}, stopPropagation() { stopped = true; }, ...event };
  for (let current = node; current && !stopped; current = current.parent) {
    const callback = current.props?.[handler];
    if (callback) callback({ ...synthetic, currentTarget: current });
  }
}
export const buttonsNamed = (root, text) => findAll(root, (node) => node.type === "button" && (node.props["aria-label"] === text || textOf(node).trim() === text));
export const countCalls = (predicate) => fakeApi.calls.filter(predicate).length;
/** Header cells and body rows of the first table that follows a section titled `title`. */
export function tableUnder(root, title) {
  const section = findAll(root, (node) => node.type === "section" && findAll({ tree: node }, (child) => child.type === "h2" && textOf(child).trim() === title).length)[0];
  if (!section) return null;
  const table = findAll({ tree: section }, (node) => node.type === "table")[0];
  if (!table) return null;
  const headers = findAll({ tree: table }, (node) => node.type === "th").map((cell) => textOf(cell).trim());
  const rows = findAll({ tree: table }, (node) => node.type === "tbody")[0];
  const body = findAll({ tree: rows }, (node) => node.type === "tr").map((row) => findAll({ tree: row }, (node) => node.type === "td").map((cell) => textOf(cell).trim()));
  return { headers, rows: body };
}
