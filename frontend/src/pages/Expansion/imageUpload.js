// Normalize a phone photograph to the API's private JPEG upload contract.
export async function prepareCameraPhoto(file) {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type) || file.size > 20 * 1024 * 1024) {
    throw new Error("Chọn ảnh JPEG, PNG hoặc WebP không quá 20 MB.");
  }
  const bitmap = await createImageBitmap(file).catch(() => { throw new Error("Không đọc được ảnh. Hãy chụp lại hoặc chọn ảnh JPEG."); });
  try {
    const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext("2d");
    context.fillStyle = "white";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.88));
    if (!blob || blob.size > 2 * 1024 * 1024) throw new Error("Ảnh còn quá lớn. Hãy chụp gần biển số hơn rồi thử lại.");
    return new File([blob], "camera.jpg", { type: "image/jpeg" });
  } finally {
    bitmap.close();
  }
}
