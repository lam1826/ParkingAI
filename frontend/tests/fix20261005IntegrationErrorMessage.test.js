// Integration round 2 (PORTAL), CL-LEDGER request 3: an axios failure without a
// server answer (timeout, network drop, cancel) shows the caller's fallback, so
// useAction's "Chưa xác nhận được kết quả…" appears instead of raw axios text.
import test from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import axios, { AxiosError } from "axios";
import { getErrorMessage } from "../src/utils/errorMessage.js";

const UNCONFIRMED = "Chưa xác nhận được kết quả. Làm mới để kiểm tra trước khi gửi lại.";
const DEFAULT = "Không thể thực hiện yêu cầu. Vui lòng thử lại.";

async function realTimeout() {
  // A local server that never answers: no external network is used.
  const server = createServer(() => {});
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    await axios.post(`http://127.0.0.1:${server.address().port}/api/v2/sites/2/finance/refunds`, {}, { timeout: 50 });
    assert.fail("the request must time out");
  } catch (error) {
    return error;
  } finally {
    server.closeAllConnections?.();
    await new Promise((resolve) => server.close(resolve));
  }
}

test("a real axios timeout shows the caller's 'not confirmed' fallback", async () => {
  const timeout = await realTimeout();
  assert.equal(timeout.response, undefined);
  assert.match(timeout.message, /timeout/);
  assert.equal(getErrorMessage(timeout, UNCONFIRMED), UNCONFIRMED);
  assert.equal(getErrorMessage(timeout), DEFAULT);
});

test("network drops and cancellations without a response show the fallback", () => {
  const failures = [
    new AxiosError("Network Error", AxiosError.ERR_NETWORK, {}, {}),
    new AxiosError("timeout of 10000ms exceeded", AxiosError.ECONNABORTED, {}, {}),
    new AxiosError("canceled", AxiosError.ERR_CANCELED, {}),
    // Plain shapes used by other tests: a request without a response, or only a transport code.
    { message: "Network Error", request: {} },
    Object.assign(new Error("timeout of 10000ms exceeded"), { code: "ECONNABORTED" }),
  ];
  for (const failure of failures) assert.equal(getErrorMessage(failure, UNCONFIRMED), UNCONFIRMED, failure.message);
});

test("server details and local validation messages keep their wording", () => {
  assert.equal(getErrorMessage({ message: "Request failed with status code 409", response: { status: 409, data: { detail: "Số tiền hoàn vượt quá" } } }, UNCONFIRMED), "Số tiền hoàn vượt quá");
  assert.equal(getErrorMessage({ response: { status: 422, data: { detail: [{ msg: "Thiếu lý do" }, { msg: "Thiếu lý do" }] } } }, UNCONFIRMED), "Thiếu lý do");
  // A response without a usable detail still uses the fallback, as before.
  assert.equal(getErrorMessage({ message: "Request failed with status code 502", response: { status: 502, data: "<html>" } }, UNCONFIRMED), UNCONFIRMED);
  // Errors thrown by the page itself (no request was involved) keep their message.
  assert.equal(getErrorMessage(new Error("Phiên đăng nhập đã thay đổi."), UNCONFIRMED), "Phiên đăng nhập đã thay đổi.");
  assert.equal(getErrorMessage(new Error("   "), UNCONFIRMED), UNCONFIRMED);
  assert.equal(getErrorMessage(null, UNCONFIRMED), UNCONFIRMED);
  assert.equal(getErrorMessage(undefined), DEFAULT);
});

test("useAction passes the 'not confirmed' fallback that a transport failure now shows", () => {
  const shared = readFileSync(new URL("../src/pages/Expansion/shared.jsx", import.meta.url), "utf8");
  assert.ok(shared.includes(`setError(getErrorMessage(failure, "${UNCONFIRMED}"))`));
});
