// A one-off webcam photograph is reviewed like a phone upload. Only the
// explicit automatic loop sends frames to the live ingress endpoint.
export async function playCameraPreview(video, timeoutMs = 10000) {
  if (!video) throw new Error("Chưa có khung hiển thị camera.");
  let timer;
  try {
    await Promise.race([
      video.play(),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("Camera chưa có hình. Kiểm tra thiết bị rồi thử lại.")), timeoutMs);
      }),
    ]);
    if (video.readyState < 2 || !video.videoWidth || !video.videoHeight) {
      throw new Error("Camera chưa có hình. Kiểm tra thiết bị rồi thử lại.");
    }
  } finally { clearTimeout(timer); }
}

export async function captureCameraPhoto(video, createCanvas = () => document.createElement("canvas")) {
  if (!video || video.readyState < 2 || !video.videoWidth || !video.videoHeight) {
    throw new Error("Camera chưa có hình để quét. Đợi hình xuất hiện rồi thử lại.");
  }
  const capturedAt = new Date().toISOString();
  const scale = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight));
  const canvas = createCanvas();
  canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
  canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Trình duyệt chưa chụp được khung hình. Hãy chọn ảnh từ thiết bị.");
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", .88));
  if (!blob || blob.size > 2 * 1024 * 1024) {
    throw new Error("Chưa chụp được ảnh phù hợp. Đưa biển số gần camera và thử lại.");
  }
  return { file: new File([blob], "webcam.jpg", { type: "image/jpeg" }), capturedAt };
}

export function cameraRecognitionMessage(observation) {
  if (!observation) return null;
  if (observation.ocr_status === "recognized" && observation.suggested_plate) {
    const score = Number.isFinite(observation.confidence) ? ` Điểm nhận diện: ${observation.confidence.toFixed(2)}.` : "";
    return { severity: "info", title: `Biển số gợi ý: ${observation.suggested_plate}`, detail: `Đối chiếu với ảnh và sửa biển số bên dưới nếu cần.${score}` };
  }
  if (observation.ocr_status === "no_plate") {
    return { severity: "warning", title: "Chưa đọc được biển số trong ảnh", detail: "Đưa biển số gần hơn, giữ đủ sáng và không bị lóa, rồi quét lại. Có thể nhập biển số bên dưới." };
  }
  if (observation.ocr_status === "unavailable") {
    return { severity: "warning", title: "Bộ nhận diện chưa sẵn sàng", detail: "Ảnh đã được lưu nhưng máy chủ chưa bật bộ nhận diện. Báo quản lý kiểm tra cấu hình hoặc nhập biển số bên dưới." };
  }
  return { severity: "error", title: "Nhận diện ảnh gặp lỗi", detail: "Ảnh đã được lưu. Hãy quét lại hoặc nhập biển số bên dưới để tiếp tục." };
}
