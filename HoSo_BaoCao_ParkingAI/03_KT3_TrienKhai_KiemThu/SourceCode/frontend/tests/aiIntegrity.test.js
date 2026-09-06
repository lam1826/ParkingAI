import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server";
import { getErrorMessage } from "../src/utils/errorMessage.js";
import { clearAIChat, readAIChat, saveAIChat } from "../src/utils/aiChatStorage.js";
import { buildAIQuestion, questionLimit, readReportContext } from "../src/utils/aiContext.js";
import { requestAI } from "../src/services/aiReportService.js";

function memoryStorage() {
  const entries = new Map();
  return { get length() { return entries.size; }, key: (index) => [...entries.keys()][index],
    getItem: (key) => entries.get(key) ?? null, setItem: (key, value) => entries.set(key, value),
    removeItem: (key) => entries.delete(key) };
}

test("FastAPI validation arrays produce renderable human text", () => {
  const message = getErrorMessage({ response: { data: { detail: [{ loc: ["body", "question"], msg: "String should have at most 1000 characters", input: "sensitive" }] } } });
  const html = renderToString(React.createElement("p", null, message));
  assert.match(html, /1000 characters/);
  assert.doesNotMatch(html, /sensitive|object Object/);
  assert.equal(typeof getErrorMessage({ response: { data: { detail: { unexpected: true } } } }), "string");
});

test("chat is isolated by account, invalid legacy content ignored, logout purges chat only", () => {
  const storage = memoryStorage();
  const messages = [{ id: "1", role: "user", content: "private" }];
  storage.setItem("parking_ai_chat_messages", JSON.stringify(messages));
  storage.setItem("unrelated", "keep");
  assert.deepEqual(readAIChat(storage, 1), []);
  saveAIChat(storage, 1, messages);
  assert.deepEqual(readAIChat(storage, 1), messages);
  assert.deepEqual(readAIChat(storage, 2), []);
  saveAIChat(storage, 2, [{ id: "2", role: "assistant", content: [{ msg: "bad" }] }]);
  assert.deepEqual(readAIChat(storage, 2), []);
  clearAIChat(storage);
  assert.deepEqual(readAIChat(storage, 1), []);
  assert.equal(storage.getItem("parking_ai_chat_messages"), null);
  assert.equal(storage.getItem("unrelated"), "keep");
});

test("contextual question includes prefix in the server limit and oversized request never posts", async () => {
  const label = "Tài khoản của tôi";
  const limit = questionLimit(label);
  assert.equal(buildAIQuestion("a".repeat(limit), label).length, 1000);
  assert.throws(() => buildAIQuestion("a".repeat(limit + 1), label), /tối đa/);
  let called = false;
  const client = { post() { called = true; } };
  await assert.rejects(async () => requestAI(client, "/ai/question", { question: "a".repeat(1001) }), /tối đa/);
  assert.equal(called, false);
});

test("history provenance reads trusted first-line metadata and treats legacy reports honestly", () => {
  assert.deepEqual(readReportContext({ prompt_used: 'PARKINGAI_CONTEXT {"source":"database","start_date":"2026-08-19","end_date":"2026-08-25"}\nprompt' }),
    { source: "Dữ liệu bãi xe", period: "19/08/2026 – 25/08/2026" });
  assert.deepEqual(readReportContext({ prompt_used: "legacy prompt" }), { source: "Chưa ghi nguồn dữ liệu", period: "Chưa ghi kỳ dữ liệu" });
});
