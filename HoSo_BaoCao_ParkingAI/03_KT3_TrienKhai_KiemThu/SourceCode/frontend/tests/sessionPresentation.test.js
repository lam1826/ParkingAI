import assert from "node:assert/strict";
import test from "node:test";

import {
  formatParkingDuration,
  getSessionStatusPresentation,
} from "../src/pages/ParkingSession/sessionPresentation.js";


test("trạng thái cancelled hiển thị là Đã hủy, không phải Đã ra", () => {
  assert.deepEqual(getSessionStatusPresentation("cancelled"), {
    label: "Đã hủy",
    color: "warning",
    variant: "outlined",
  });
});


test("trạng thái phiên chuẩn có nhãn tường minh và trạng thái lạ fail closed", () => {
  assert.equal(getSessionStatusPresentation("active").label, "Đang gửi");
  assert.equal(getSessionStatusPresentation("completed").label, "Đã ra");
  assert.equal(getSessionStatusPresentation("other").label, "Không xác định");
});


test("thời gian gửi được định dạng từ phút đã persist", () => {
  assert.equal(formatParkingDuration(150, "completed"), "2 giờ 30 phút");
  assert.equal(formatParkingDuration(60, "completed"), "1 giờ");
  assert.equal(formatParkingDuration(30, "completed"), "30 phút");
  assert.equal(formatParkingDuration(0, "completed"), "Dưới 1 phút");
  assert.equal(formatParkingDuration(null, "active"), "Đang gửi");
  assert.equal(formatParkingDuration(null, "cancelled"), "—");
});
