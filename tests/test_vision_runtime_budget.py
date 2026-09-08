"""Optional real-runtime checks: set PARKING_VISION_TEST_MODEL to the pinned ONNX.

No model downloads. General CI can omit the optional OCR runtime; the release
resource check runs this with the packaged models before enabling online OCR.
"""
import os
from pathlib import Path

import pytest
from PIL import Image


@pytest.mark.parametrize("size", [(20, 1600), (1600, 8), (60, 30), (640, 480)])
def test_plate_crop_bounds_both_dimensions_without_losing_image(size):
    from expansion.vision_service import _prepare_plate_crop
    result = _prepare_plate_crop(Image.new("RGB", size, "black"))
    assert 32 <= min(result.size) <= max(result.size) <= 640
    assert result.getpixel((result.width // 2, result.height // 2)) == (0, 0, 0)


def test_narrow_plate_ocr_tensor_has_bounded_longest_side():
    np = pytest.importorskip("numpy")
    pytest.importorskip("rapidocr_onnxruntime")
    model = os.getenv("PARKING_VISION_TEST_MODEL")
    if not model or not Path(model).is_file():
        pytest.skip("requires the locally verified plate ONNX model")
    from expansion.vision_service import YoloRapidOCR

    runtime = YoloRapidOCR(model)
    class TensorCaptured(Exception):
        pass
    tensors = []
    def capture(tensor):
        tensors.append(tensor.shape)
        raise TensorCaptured
    runtime.ocr.text_det.infer = capture
    # Narrow plate crops previously expanded their shortest side to 736,
    # producing tensors thousands of pixels wide and exhausting a 1 GB VM.
    for height, width in [(32, 320), (80, 320), (320, 32), (640, 1600)]:
        with pytest.raises(TensorCaptured):
            runtime.ocr(np.ones((height, width, 3), dtype=np.uint8), use_cls=False)
        assert max(tensors[-1][2:]) <= 640
