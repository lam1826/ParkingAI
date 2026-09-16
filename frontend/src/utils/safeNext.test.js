import assert from "node:assert/strict";
import { test } from "node:test";
import { defaultLanding, nextFromSearch, sanitizeNextPath, withNext } from "./safeNext.js";

test("keeps same-origin app paths with query and hash", () => {
  assert.equal(sanitizeNextPath("/portal?tab=purchase&kind=hourly#top"), "/portal?tab=purchase&kind=hourly#top");
  assert.equal(sanitizeNextPath("/reservations"), "/reservations");
  assert.equal(sanitizeNextPath("/"), "/");
});

test("rejects everything that could leave the origin or loop through auth pages", () => {
  for (const value of ["https://evil.example/x", "//evil.example", "/\\evil.example", "javascript:alert(1)", "portal",
    "/login", "/register?next=/portal", "/login/", "", null, undefined, 42, "/a\nb", "/%0d%0aSet-Cookie:x"]) {
    assert.equal(sanitizeNextPath(value), null, String(value));
  }
});

test("reads and encodes the continuation parameter", () => {
  assert.equal(nextFromSearch("?next=%2Fportal%3Ftab%3Dpurchase"), "/portal?tab=purchase");
  assert.equal(nextFromSearch("?next=https%3A%2F%2Fevil.example"), null);
  assert.equal(withNext("/login", "/portal?tab=purchase"), "/login?next=%2Fportal%3Ftab%3Dpurchase");
  assert.equal(withNext("/login", "//evil"), "/login");
  assert.equal(defaultLanding("customer"), "/portal");
  assert.equal(defaultLanding("manager"), "/");
});
