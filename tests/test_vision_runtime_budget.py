"""Optional real-runtime checks: set PARKING_VISION_TEST_MODEL to the pinned ONNX.

No model downloads. General CI can omit the optional OCR runtime; the release
resource check runs this with the packaged models before enabling online OCR.
"""
import os
from pathlib import Path

import pytest
from PIL import Image


def test_ocr_preserves_left_to_right_order_for_sloped_single_row():
    np = pytest.importorskip("numpy")
    from types import SimpleNamespace
    from expansion.vision_service import YoloRapidOCR
    runtime = YoloRapidOCR.__new__(YoloRapidOCR)
    runtime.input = SimpleNamespace(name="image")
    runtime.plate_classes = [0]
    # One detected plate; the right text box is higher but overlaps the left
    # box vertically. It still belongs to the same physical line of text.
    runtime.detector = SimpleNamespace(run=lambda *_args: [np.array([[[320], [320], [600], [160], [.95]]])])
    runtime.ocr = lambda *_args, **_kwargs: ([
        [[[10, 8], [90, 8], [90, 28], [10, 28]], "51A", .99],
        [[[100, 2], [220, 2], [220, 22], [100, 22]], "12345", .98],
    ], None)
    assert runtime.recognize(Image.new("RGB", (640, 640)))[0]["plate"] == "51A-123.45"


@pytest.mark.parametrize("scale", [0.5, 1, 4])
def test_ocr_groups_two_rows_by_geometry_without_mutating_results(scale):
    from copy import deepcopy
    from expansion.vision_service import order_plate_text_lines
    def line(x, y, text):
        return [[[px * scale, py * scale] for px, py in
                 [(x, y), (x + 30, y), (x + 30, y + 20), (x, y + 20)]], text, .95]
    detected = [line(70, 46, "45"), line(70, 2, "A1"), line(10, 40, "123"), line(10, 8, "59")]
    before = deepcopy(detected)
    ordered = order_plate_text_lines(detected)
    assert [part[1] for part in ordered] == ["59", "A1", "123", "45"]
    assert detected == before


def test_ocr_empty_and_single_text_box_keep_their_meaning():
    from expansion.vision_service import order_plate_text_lines
    assert order_plate_text_lines([]) == []
    line = [[[0, 0], [100, 0], [100, 20], [0, 20]], "51A12345", .9]
    assert order_plate_text_lines([line]) == [line]


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
