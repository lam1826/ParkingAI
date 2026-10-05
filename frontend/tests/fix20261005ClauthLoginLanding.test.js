// CL-AUTH #37: internal roles never land on the customer-only portal because of
// a customer continuation; customers still resume the flow they chose.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { postLoginDestination } from "../src/pages/Login/loginDestination.js";

const source = (path) => readFile(new URL(`../src/${path}`, import.meta.url), "utf8");

test("customer continuations are ignored for internal roles", () => {
  for (const role of ["admin", "manager", "staff"]) {
    assert.equal(postLoginDestination("/portal", role), "/");
    assert.equal(postLoginDestination("/portal?tab=purchase&kind=hourly", role), "/");
    assert.equal(postLoginDestination("/reservations", role), "/");
    assert.equal(postLoginDestination("/portal/", role), "/");
  }
});

test("customers and internal deep links keep their continuation", () => {
  assert.equal(postLoginDestination("/portal", "customer"), "/portal");
  assert.equal(postLoginDestination("/portal?tab=tickets", "customer"), "/portal?tab=tickets");
  assert.equal(postLoginDestination("/sites?site=2&plate=51A12345", "staff"), "/sites?site=2&plate=51A12345");
  assert.equal(postLoginDestination("/audit-logs", "manager"), "/audit-logs");
});

test("unsafe or missing continuations fall back to the role landing", () => {
  assert.equal(postLoginDestination(null, "customer"), "/portal");
  assert.equal(postLoginDestination("//evil.example", "staff"), "/");
  assert.equal(postLoginDestination("https://evil.example/portal", "customer"), "/portal");
  assert.equal(postLoginDestination("/login", "admin"), "/");
});

test("the public header login button carries no customer continuation", async () => {
  const page = await source("pages/Public/PublicSitePage.jsx");
  assert.doesNotMatch(page, /to=\{`\/login\?next=\$\{encodeURIComponent\("\/portal"\)\}`\}/);
  assert.match(page, /to="\/login"/);
  // Self-registration creates customer accounts, so /register keeps next=/portal.
  assert.match(page, /\/register\?next=\$\{encodeURIComponent\("\/portal"\)\}/);
  const context = await source("context/AuthContext.jsx");
  assert.match(context, /postLoginDestination\(/);
});
