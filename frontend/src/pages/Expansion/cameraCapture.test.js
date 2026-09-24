import test from "node:test";
import assert from "node:assert/strict";
import { captureCameraPhoto, cameraRecognitionMessage, playCameraPreview } from "./cameraCapture.js";

test("camera preview with no frames times out instead of leaving startup stuck", async () => {
  await assert.rejects(playCameraPreview({ play: () => new Promise(() => {}) }, 5), /Camera chưa có hình/);
});

test("playing preview must contain a usable frame before automation can start", async () => {
  await assert.rejects(playCameraPreview({ play: async () => {}, readyState: 0, videoWidth: 0, videoHeight: 0 }), /Camera chưa có hình/);
  await playCameraPreview({ play: async () => {}, readyState: 4, videoWidth: 1280, videoHeight: 720 });
});

test("camera capture rejects absent, loading and zero-size video instead of uploading blank frames", async () => {
  for (const video of [null, { readyState: 1, videoWidth: 1280, videoHeight: 720 }, { readyState: 2, videoWidth: 0, videoHeight: 720 }]) {
    await assert.rejects(captureCameraPhoto(video, () => { throw new Error("Should not create canvas"); }), /chưa có hình/);
  }
});

test("portrait and landscape camera frames retain aspect ratio within API pixel and byte limits", async () => {
  for (const [width, height, expectedWidth, expectedHeight] of [[3840, 2160, 1600, 900], [1080, 1920, 900, 1600], [640, 480, 640, 480]]) {
    const video = { readyState: 2, videoWidth: width, videoHeight: height };
    let drawn;
    const canvas = { getContext: () => ({ drawImage: (...args) => { drawn = args; } }), toBlob: callback => callback(new Blob(["jpeg"], { type: "image/jpeg" })) };
    const started = Date.now();
    const photo = await captureCameraPhoto(video, () => canvas);
    assert.deepEqual([canvas.width, canvas.height], [expectedWidth, expectedHeight]);
    assert.deepEqual(drawn, [video, 0, 0, expectedWidth, expectedHeight]);
    assert.equal(photo.file.type, "image/jpeg");
    assert.equal(photo.file.name, "webcam.jpg");
    assert.ok(Date.parse(photo.capturedAt) >= started && Date.parse(photo.capturedAt) <= Date.now());
  }
});

test("camera capture reports encoding failure and overlarge files", async () => {
  const video = { readyState: 2, videoWidth: 1280, videoHeight: 720 };
  for (const blob of [null, { size: 2 * 1024 * 1024 + 1 }]) {
    await assert.rejects(captureCameraPhoto(video, () => ({ getContext: () => ({ drawImage() {} }), toBlob: callback => callback(blob) })), /Chưa chụp được/);
  }
});

test("OCR unavailable, errors and no detection are different visible outcomes", () => {
  assert.equal(cameraRecognitionMessage(null), null);
  assert.match(cameraRecognitionMessage({ ocr_status: "no_plate" }).title, /Chưa đọc được/);
  assert.match(cameraRecognitionMessage({ ocr_status: "unavailable" }).title, /chưa sẵn sàng/);
  assert.equal(cameraRecognitionMessage({ ocr_status: "error" }).severity, "error");
  assert.equal(cameraRecognitionMessage({ ocr_status: "recognized", suggested_plate: null }).severity, "error");
});

test("recognized text remains a suggestion with honest score and human review", () => {
  const message = cameraRecognitionMessage({ ocr_status: "recognized", suggested_plate: "51A-123.45", confidence: .5642 });
  assert.match(message.title, /51A-123\.45/);
  assert.match(message.detail, /Đối chiếu/);
  assert.match(message.detail, /0\.56/);
  assert.doesNotMatch(message.detail, /%|chính xác/);
});
