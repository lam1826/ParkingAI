import test from "node:test";
import assert from "node:assert/strict";
import { requestId } from "./requestId.js";

test("LAN HTTP fallback preserves UUID version and variant without randomUUID", () => {
  const value = requestId({ getRandomValues: (array) => array.fill(255) });
  assert.match(value, /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
});
test("native request IDs and fallback both remain unique between attempts", () => {
  assert.equal(requestId({ randomUUID: () => "native-id" }), "native-id");
  const values = Array.from({ length: 100 }, () => requestId({ getRandomValues: (array) => crypto.getRandomValues(array) }));
  assert.equal(new Set(values).size, values.length);
});
