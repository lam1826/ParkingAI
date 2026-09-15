"""CPU reference-frame difference baseline. No IO, models, DB writes or accuracy claim."""
import importlib.util
import io

from PIL import Image

ENGINE = "reference-diff-v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 1600 * 1600
MAX_EDGE = 640


def status():
    available = all(importlib.util.find_spec(module) is not None for module in ("cv2", "numpy"))
    return {"engine": ENGINE, "available": available, "accuracy_measured": False,
            "reason": "So sánh ảnh nền cục bộ; cần kiểm chứng trên ảnh bãi thực tế." if available else "Cần cài runtime OpenCV và NumPy cục bộ."}


def _decode(content):
    import cv2
    import numpy as np
    if not content or len(content) > MAX_BYTES:
        raise ValueError("Ảnh CV phải có dữ liệu và không vượt quá 2 MB.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {"JPEG", "PNG"} or min(image.size) < 64 or image.width * image.height > MAX_PIXELS:
                raise ValueError("Ảnh CV cần từ 64 pixel mỗi chiều và không quá 1600 × 1600 pixel.")
            dimensions = image.size
            image.verify()
        frame = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Không giải mã được ảnh.")
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValueError("Ảnh tham chiếu hoặc ảnh hiện tại không hợp lệ.") from error
    scale = min(1, MAX_EDGE / max(dimensions))
    if scale < 1:
        frame = cv2.resize(frame, (max(1, round(dimensions[0] * scale)), max(1, round(dimensions[1] * scale))), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), dimensions


def _masks(regions, shape):
    import cv2
    import numpy as np
    masks = []
    interiors = []
    height, width = shape
    for region in regions:
        mask = np.zeros(shape, dtype=np.uint8)
        points = np.array([[round(x * (width - 1)), round(y * (height - 1))] for x, y in region["polygon"]], dtype=np.int32)
        cv2.fillPoly(mask, [points], 1)
        area = int(mask.sum())
        if area < 100:
            raise ValueError("Vùng chỗ đỗ quá nhỏ sau khi thu ảnh; hãy khoanh vùng lớn hơn.")
        interior = cv2.erode(mask, np.ones((3, 3), dtype=np.uint8))
        for previous in interiors:
            if int((interior & previous).sum()) / max(1, min(int(interior.sum()), int(previous.sum()))) > 0.02:
                raise ValueError("Các vùng chỗ đỗ chồng lấn; hãy khoanh lại từng chỗ.")
        interiors.append(interior)
        masks.append(mask.astype(bool))
    return masks


def _quality(gray, settings):
    import cv2
    import numpy as np
    brightness = float(np.median(gray))
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    clipped = float(np.mean((gray <= 5) | (gray >= 250)))
    reason = "too_dark" if brightness < 20 else "too_bright" if brightness > 235 else "obscured" if clipped > 0.8 else "blurred" if blur < settings["min_blur_variance"] else None
    return {"reason": reason, "brightness": round(brightness, 3), "blur_variance": round(blur, 3)}


def validate_reference(content, regions, settings):
    gray, dimensions = _decode(content)
    _masks(regions, gray.shape)
    quality = _quality(gray, settings)
    if quality["reason"]:
        raise ValueError("Ảnh nền quá tối, sáng hoặc mờ. Chọn ảnh rõ và xác nhận các chỗ đã khoanh đang trống.")
    return {"width": dimensions[0], "height": dimensions[1], "quality": quality}


def unknown(regions, reason, **quality):
    return {"quality": {"reason": reason, **quality}, "readings": [
        {"slot_id": region["slot_id"], "raw_state": "unknown", "state": "unknown", "change_ratio": None, "reason": reason} for region in regions]}


def analyze(reference, current, regions, settings):
    import cv2
    import numpy as np
    ref, ref_dimensions = _decode(reference)
    frame, dimensions = _decode(current)
    if ref_dimensions != dimensions:
        return unknown(regions, "frame_geometry_changed")
    masks = _masks(regions, ref.shape)
    ref_quality, quality = _quality(ref, settings), _quality(frame, settings)
    if ref_quality["reason"]:
        return unknown(regions, "reference_quality")
    if quality["reason"]:
        return unknown(regions, quality["reason"], brightness=quality["brightness"], blur_variance=quality["blur_variance"])
    shift = float(np.median(frame.astype(np.int16) - ref.astype(np.int16)))
    quality["lighting_shift"] = round(shift, 3)
    if abs(shift) > settings["max_lighting_shift"]:
        return unknown(regions, "lighting_changed", lighting_shift=round(shift, 3))
    corrected = np.clip(frame.astype(np.float32) - shift, 0, 255).astype(np.uint8)
    changed = cv2.absdiff(corrected, ref) >= settings["pixel_delta"]
    if float(changed.mean()) > 0.85:
        return unknown(regions, "scene_changed")
    readings = []
    for region, mask in zip(regions, masks):
        ratio = float(changed[mask].mean())
        clipped = float(np.mean((frame[mask] <= 5) | (frame[mask] >= 250)))
        state = "unknown" if clipped > 0.85 else "empty" if ratio <= settings["empty_ratio"] else "occupied" if ratio >= settings["occupied_ratio"] else "unknown"
        reason = "region_obscured" if clipped > 0.85 else "ambiguous_change" if state == "unknown" else None
        readings.append({"slot_id": region["slot_id"], "raw_state": state, "state": state, "change_ratio": round(ratio, 6), "reason": reason})
    return {"quality": quality, "readings": readings}
