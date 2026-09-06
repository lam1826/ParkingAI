const PREFIX = "parking_ai_chat_messages";
const keyFor = (userId) => `${PREFIX}:v2:${userId}`;
const validMessage = (item) => item && typeof item.id === "string"
  && ["user", "assistant"].includes(item.role) && typeof item.content === "string";

export function readAIChat(storage, userId) {
  if (userId == null) return [];
  try {
    const parsed = JSON.parse(storage.getItem(keyFor(userId)));
    return Array.isArray(parsed) ? parsed.filter(validMessage) : [];
  } catch { return []; }
}

export function saveAIChat(storage, userId, messages) {
  if (userId == null) return;
  try { storage.setItem(keyFor(userId), JSON.stringify(messages.filter(validMessage).slice(-100))); }
  catch { /* Storage quota/private mode must never interrupt gate operations. */ }
}

export function clearAIChat(storage = globalThis.sessionStorage, eventTarget = globalThis.window) {
  try {
    for (let index = storage.length - 1; index >= 0; index -= 1) {
      const key = storage.key(index);
      if (key === PREFIX || key?.startsWith(`${PREFIX}:`)) storage.removeItem(key);
    }
  } catch { /* In-memory chat is still cleared through the event. */ }
  eventTarget?.dispatchEvent(new Event("parking-ai-clear-chat"));
}
