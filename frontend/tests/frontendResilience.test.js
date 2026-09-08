import assert from "node:assert/strict";
import test from "node:test";

import { shouldAttachAuthorization } from "../src/services/credentialRequestPolicy.js";
import { isChunkLoadError, recoverChunkError } from "../src/utils/chunkRecovery.js";
import { isMenuPathSelected } from "../src/utils/navigationState.js";
import { newOrderDraft } from "../src/pages/Expansion/portalState.js";

test("login and registration never carry an existing bearer token", () => {
  assert.equal(shouldAttachAuthorization("/api/auth/login"), false);
  assert.equal(shouldAttachAuthorization("https://api.example.test/api/auth/login"), false);
  assert.equal(shouldAttachAuthorization("/api/auth/register"), false);
  assert.equal(shouldAttachAuthorization("/api/auth/me"), true);
});

test("a failed dynamic import reloads once and then falls through to the boundary", () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  const location = { href: "https://parking.example/vision", reloads: 0, reload() { this.reloads++; } };
  const error = new TypeError("Failed to fetch dynamically imported module");
  assert.equal(isChunkLoadError(error), true);
  assert.equal(recoverChunkError(error, { storage, location }), true);
  assert.equal(recoverChunkError(error, { storage, location }), false);
  assert.equal(location.reloads, 1);
});

test("sidebar selection matches path segments instead of shared prefixes", () => {
  assert.equal(isMenuPathSelected("/portal-admin", "/portal"), false);
  assert.equal(isMenuPathSelected("/portal/orders", "/portal"), true);
  assert.equal(isMenuPathSelected("/", "/"), true);
  assert.equal(isMenuPathSelected("/sites", "/"), false);
});

test("new order action preserves selections and rotates the idempotency key", () => {
  const previous = { plan_id: "2", vehicle_id: "7", idempotency_key: "old" };
  assert.deepEqual(newOrderDraft(previous, () => "new"), {
    plan_id: "2",
    vehicle_id: "7",
    idempotency_key: "new",
  });
});
