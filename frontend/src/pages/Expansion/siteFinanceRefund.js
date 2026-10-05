// Site Finance direct refunds (review 05/10/2026 #1, #24, #26, #27).
//
// The server decides whether a receipt may be refunded directly: portal
// tickets/monthly periods and receipts with an open customer request go
// through the refund-request workflow. The browser only phrases that block.
//
// A refund attempt whose outcome is unknown (no response, timeout, 5xx, 408,
// 429) keeps its idempotency key per receipt until the server answers
// definitively, so a reopened dialog cannot record a second refund. The key is
// stored before the request is sent and outside SiteFinance's own state, so it
// survives a remount (header "Làm mới", #73), a navigation and a tab reload.
//
// Stored attempts belong to the account that sent them (round 3): AuthProvider
// binds the signed-in account (bindPendingRefundsAccount), only that account's
// attempts are offered, and another account signing in on the tab drops the
// earlier account's drafts. The same account keeps them across logout, 401
// expiry and reload, so its unconfirmed key still protects against a double refund.
import { getErrorMessage } from "../../utils/errorMessage.js";
import { traceSuffix } from "../../services/serverErrorTrace.js";

const REFUND_RETRY_GUIDANCE = "Danh sách chứng từ đã được tải lại: kiểm tra phiếu hoàn trước khi gửi lại. "
  + "Gửi lại từ hộp thoại Hoàn tiền dùng cùng mã yêu cầu nên không ghi hoàn trùng.";
/** No response at all (timeout, network drop): only then is the connection blamed. */
export const UNCERTAIN_REFUND_MESSAGE = "Chưa xác nhận được kết quả hoàn tiền (mất kết nối hoặc quá thời gian chờ). " + REFUND_RETRY_GUIDANCE;
export const PENDING_REFUND_NOTICE = "Lần hoàn trước của chứng từ này chưa được xác nhận. "
  + "Hộp thoại giữ nguyên mã yêu cầu và nội dung cũ; nếu lần trước đã ghi nhận, máy chủ sẽ không ghi thêm.";
export const REFUND_ANSWERED_NOTICE = "Lần hoàn trước của chứng từ này đã có kết quả từ máy chủ nên không gửi lại mã yêu cầu cũ. "
  + "Danh sách chứng từ đã được tải lại: kiểm tra phiếu hoàn, rồi mở lại Hoàn tiền nếu cần hoàn thêm.";
const STORAGE_KEY = "parkingai.siteFinance.pendingRefunds";
const storageKeyFor = (account) => account === null ? STORAGE_KEY : `${STORAGE_KEY}:${account}`;
const isRefundStorageKey = (key) => key === STORAGE_KEY || (typeof key === "string" && key.startsWith(`${STORAGE_KEY}:`));
const accountOf = (accountId) => accountId === undefined || accountId === null || accountId === "" ? null : String(accountId);

/** What the "Thao tác" column offers for one ledger row. */
export function directRefundAction(row, manager) {
  if (!manager || row?.kind !== "receipt" || row.method === "demo" || !(row.refundable_amount > 0)) return { kind: "none", label: "" };
  if (row.direct_refund_blocked_reason) {
    return { kind: "blocked", label: row.direct_refund_blocked_label || "Khoản thu này chỉ hoàn qua yêu cầu hoàn tiền của khách." };
  }
  return { kind: "refund", label: "Hoàn tiền" };
}

/** True when the server may have committed the refund although the browser saw a failure. */
export function refundOutcomeUncertain(error) {
  const status = error?.response?.status;
  return !(status >= 400 && status < 500 && ![408, 429].includes(status));
}

// The same maps for this page load, per account. SiteFinance is remounted by the header "Làm mới"
// (#73), a site switch or a navigation, so its own state cannot hold the key: this copy keeps it across
// a remount even when sessionStorage is blocked, and sessionStorage adds a reload of the tab.
const memoryPending = new Map();
// The signed-in account (null: nobody), and the account each attempt was sent by: a late answer
// settles the attempt for its own account, never for whoever is signed in by then.
let boundAccount = null;
const attemptAccounts = new Map();
// Keys the server confirmed during this page load: a late timeout of an older request with the same
// key must not bring such a key back (the next refund would replay instead of being recorded).
const confirmedKeys = new Set();
// Mounted SiteFinance instances: an attempt sent by an instance that has since been replaced (header
// "Làm mới", navigation) settles late, and the visible instance must reload its lists.
const settledListeners = new Set();

/** Subscribe to settled attempts ({ receiptId, key, outcome }); returns the unsubscribe function. */
export function onRefundSettled(listener) {
  settledListeners.add(listener);
  return () => { settledListeners.delete(listener); };
}

function readStoredRefunds(storage, account) {
  try {
    const value = JSON.parse(storage?.getItem(storageKeyFor(account)) || "{}");
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  } catch {
    return {};
  }
}

const accountPending = (account, storage) => ({ ...readStoredRefunds(storage, account), ...memoryPending.get(account) });

/**
 * The account signed in on this tab (AuthProvider: its profile id when loaded, null on every session
 * reset). Binding a different account drops every other account's drafts from memory and storage:
 * the next manager is never offered (or left holding) the previous manager's key, amount and reason.
 */
export function bindPendingRefundsAccount(accountId, storage = globalThis.sessionStorage) {
  const account = accountOf(accountId);
  boundAccount = account;
  if (account === null) return;
  for (const owner of [...memoryPending.keys()]) if (owner !== account) memoryPending.delete(owner);
  try {
    for (let index = (storage?.length ?? 0) - 1; index >= 0; index -= 1) {
      const key = storage.key(index);
      if (isRefundStorageKey(key) && key !== storageKeyFor(account)) storage.removeItem(key);
    }
  } catch {
    // Blocked storage holds no drafts; the in-memory copies were dropped above.
  }
}

/**
 * Attempts of the signed-in account with an unknown outcome. Keeping an extra key is safe for that
 * account (the server replays it); losing one is not.
 */
export function loadPendingRefunds(storage = globalThis.sessionStorage) {
  return accountPending(boundAccount, storage);
}

function savePendingRefunds(pending, storage, account) {
  memoryPending.set(account, { ...pending });
  try {
    storage?.setItem(storageKeyFor(account), JSON.stringify(pending));
  } catch {
    // Private mode or blocked storage: the in-memory copy still protects this page load.
  }
}

const storedAttempt = (attempt) => ({ key: attempt.key, amount: attempt.amount, method: attempt.method, reason: attempt.reason });

/**
 * Store an attempt BEFORE it is sent: until the server answers definitively its outcome is unknown,
 * so a reload, a navigation or a header "Làm mới" remount while the request is in flight still finds
 * the same key (and content) for the next attempt.
 */
export function beginRefundAttempt(pending, receiptId, attempt, storage = globalThis.sessionStorage) {
  attemptAccounts.set(attempt.key, boundAccount);
  const next = { ...(pending || {}), [receiptId]: storedAttempt(attempt) };
  savePendingRefunds(next, storage, boundAccount);
  return next;
}

/** Key and form values for (re)opening the refund dialog of one receipt. */
export function refundDialogState(pending, receiptId, makeKey) {
  const attempt = pending?.[receiptId];
  if (attempt?.key) {
    return { key: attempt.key, amount: String(attempt.amount ?? ""), method: attempt.method || "cash", reason: attempt.reason || "", uncertain: true };
  }
  return { key: makeKey(), amount: "", method: "cash", reason: "", uncertain: false };
}

/**
 * Record the outcome of one attempt. Success or a definitive 4xx refusal forgets
 * the key; an uncertain outcome keeps key and content for the next attempt. Only
 * the attempt that owns the stored key settles it: a late answer for an older
 * key never drops or replaces a newer attempt's key, and a late timeout never
 * brings back a key the server confirmed. The attempt is settled for the account
 * that sent it: after an account switch the caller's map is not that account's.
 */
export function settleRefundAttempt(pending, receiptId, attempt, error, storage = globalThis.sessionStorage) {
  const account = attemptAccounts.has(attempt.key) ? attemptAccounts.get(attempt.key) : boundAccount;
  const next = { ...((account === boundAccount ? pending : accountPending(account, storage)) || {}) };
  const stored = next[receiptId];
  const outcome = error === undefined ? "confirmed" : refundOutcomeUncertain(error) ? "uncertain" : "refused";
  if (outcome === "confirmed") confirmedKeys.add(attempt.key);
  let changed = false;
  if (outcome !== "uncertain") {
    if (stored?.key === attempt.key) { delete next[receiptId]; changed = true; }
  } else if (!stored && !confirmedKeys.has(attempt.key) && (boundAccount === null || boundAccount === account)) {
    // Its entry was cleared by another answer for this key that did not confirm it: keeping an extra
    // key is safe (the server replays it), losing one is not. Not after another account signed in:
    // that switch dropped this account's drafts on purpose.
    next[receiptId] = storedAttempt(attempt);
    changed = true;
  }
  if (changed) savePendingRefunds(next, storage, account);
  for (const listener of [...settledListeners]) listener({ receiptId, key: attempt.key, outcome });
  return next;
}

/** True when the dialog retries an attempt whose outcome has meanwhile become known. */
export function refundRetryAnswered(dialog, pending) {
  return !!dialog?.uncertain && pending?.[dialog.row?.id]?.key !== dialog.key;
}

const sentence = (text) => /[.!?…]$/.test(text) ? text : `${text}.`;

/**
 * Error shown to the manager: uncertain outcomes never surface a raw axios message. Without any
 * response the connection is blamed; a 5xx/408/429 answer keeps the same "not confirmed" guidance
 * but shows what the server said, including the 'Mã truy vết' the user quotes to support (#64).
 */
export function refundFailure(error) {
  if (!refundOutcomeUncertain(error)) return error;
  const status = Number(error?.response?.status);
  if (!(status > 0)) return new Error(UNCERTAIN_REFUND_MESSAGE);
  let detail = getErrorMessage(error, "").trim();
  const traceId = typeof error?.traceId === "string" ? error.traceId.trim() : "";
  if (traceId && !detail.includes(traceId)) detail = detail ? `${sentence(detail)} ${traceSuffix(traceId)}` : traceSuffix(traceId);
  const said = detail ? ` Máy chủ báo: ${sentence(detail)}` : "";
  return new Error(`Chưa xác nhận được kết quả hoàn tiền: máy chủ trả lỗi ${status}.${said} ${REFUND_RETRY_GUIDANCE}`);
}
