// CL-AUTH #66: a render error on one /portal?tab=... view no longer blocks the
// other customer destinations that share the /portal pathname.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { pageBoundaryResetKey, shouldResetErrorBoundary } from "../src/components/common/errorBoundaryReset.js";

// Minimal model of React's class-boundary lifecycle (getDerivedStateFromError,
// then componentDidUpdate) driven by the same reset decision as ErrorBoundary.
function boundary(throwsFor) {
  let props = { resetKey: undefined };
  let state = { hasError: false };
  let shown = null;
  const render = (nextProps) => {
    const prevProps = props;
    const prevState = state;
    props = nextProps;
    if (!state.hasError && throwsFor(props.resetKey)) state = { hasError: true };
    shown = state.hasError ? "error-card" : props.resetKey;
    if (shouldResetErrorBoundary({ prevResetKey: prevProps.resetKey, resetKey: props.resetKey, hadError: prevState.hasError, hasError: state.hasError })) {
      state = { hasError: false };
      render(props); // setState in componentDidUpdate re-renders with the same props
    }
    return shown;
  };
  return render;
}

const at = (url) => { const parsed = new URL(url, "http://parkingai.invalid"); return { pathname: parsed.pathname, search: parsed.search, hash: parsed.hash }; };

test("the boundary resets on another /portal tab but keeps showing a view that fails", () => {
  const render = boundary((key) => key === "/portal?tab=fees");
  assert.equal(render({ resetKey: pageBoundaryResetKey(at("/portal?tab=fees")) }), "error-card");
  assert.equal(render({ resetKey: pageBoundaryResetKey(at("/portal?tab=support")) }), "/portal?tab=support");
  assert.equal(render({ resetKey: pageBoundaryResetKey(at("/portal?tab=tickets")) }), "/portal?tab=tickets");
  // Navigating back to the broken view shows the card again, without a loop.
  assert.equal(render({ resetKey: pageBoundaryResetKey(at("/portal?tab=fees")) }), "error-card");
  assert.equal(render({ resetKey: pageBoundaryResetKey(at("/portal?tab=fees")) }), "error-card");
});

test("a re-render without navigation, or a #hash jump, keeps the error card", () => {
  assert.equal(shouldResetErrorBoundary({ prevResetKey: "/portal", resetKey: "/portal", hadError: true, hasError: true }), false);
  assert.equal(shouldResetErrorBoundary({ prevResetKey: "/portal", resetKey: "/portal?tab=support", hadError: false, hasError: true }), false);
  assert.equal(pageBoundaryResetKey(at("/portal?tab=fees#main-content")), pageBoundaryResetKey(at("/portal?tab=fees")));
  // The root boundary (no resetKey) never resets by itself.
  assert.equal(shouldResetErrorBoundary({ prevResetKey: undefined, resetKey: undefined, hadError: true, hasError: true }), false);
});

test("MainLayout passes the location as resetKey and ErrorBoundary honours it", async () => {
  const layout = await readFile(new URL("../src/layouts/MainLayout.jsx", import.meta.url), "utf8");
  assert.match(layout, /<ErrorBoundary key=\{location\.pathname\} resetKey=\{pageBoundaryResetKey\(location\)\}>/);
  const component = await readFile(new URL("../src/components/common/ErrorBoundary.jsx", import.meta.url), "utf8");
  assert.match(component, /componentDidUpdate\(prevProps, prevState\)/);
  assert.match(component, /shouldResetErrorBoundary\(\{\s*prevResetKey: prevProps\.resetKey,\s*resetKey: this\.props\.resetKey,\s*hadError: prevState\.hasError,\s*hasError: this\.state\.hasError,/);
});
