"""Synthetic contract checks, not measured accuracy on real parking images."""
import io

import pytest
from PIL import Image
from pydantic import ValidationError

from expansion import occupancy_engine as engine
from expansion.occupancy_schemas import CalibrationCreate, OccupancySettings, SlotRegion

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")
REGIONS = [{"slot_id": 1, "polygon": [[.1, .1], [.45, .1], [.45, .8], [.1, .8]]}]
SETTINGS = OccupancySettings().model_dump()


def frame(*, vehicle=False, shift=0, flat=None, size=160):
    yy, xx = np.indices((size, size))
    pixels = np.where((xx // 4 + yy // 4) % 2, 100, 125).astype(np.int16)
    if vehicle:
        pixels[30:115, 22:64] = 190
    pixels = np.clip(pixels + shift, 0, 255).astype(np.uint8)
    if flat is not None:
        pixels[:] = flat
    output = io.BytesIO()
    Image.fromarray(pixels).save(output, "PNG")
    return output.getvalue()


@pytest.mark.parametrize(("vehicle", "state"), [(False, "empty"), (True, "occupied")])
def test_baseline_uses_pixels_inside_polygon(vehicle, state):
    result = engine.analyze(frame(), frame(vehicle=vehicle), REGIONS, SETTINGS)
    assert result["readings"][0]["state"] == state
    assert engine.status()["accuracy_measured"] is False


@pytest.mark.parametrize(("options", "reason"), [({"flat": 0}, "too_dark"), ({"flat": 255}, "too_bright"),
    ({"flat": 110}, "blurred"), ({"shift": 50}, "lighting_changed"), ({"size": 180}, "frame_geometry_changed")])
def test_unusable_frames_are_unknown(options, reason):
    result = engine.analyze(frame(), frame(**options), REGIONS, SETTINGS)
    assert result["readings"][0]["state"] == "unknown"
    assert result["quality"]["reason"] == reason


def test_small_global_lighting_shift_is_compensated_without_claiming_accuracy():
    result = engine.analyze(frame(), frame(shift=20), REGIONS, SETTINGS)
    assert result["readings"][0]["state"] == "empty"
    assert result["quality"]["lighting_shift"] == 20


def test_reference_rejects_bad_image_and_nested_polygons_in_either_order():
    with pytest.raises(ValueError):
        engine.validate_reference(b"not an image", REGIONS, SETTINGS)
    outer = {"slot_id": 2, "polygon": [[0, 0], [.9, 0], [.9, .9], [0, .9]]}
    for regions in ([*REGIONS, outer], [outer, *REGIONS]):
        with pytest.raises(ValueError, match="chồng lấn"):
            engine.validate_reference(frame(), regions, SETTINGS)


@pytest.mark.parametrize("points", [
    [[0, 0], [1, 1], [1, 0], [0, 1]], [[0, 0], [0, 0], [.5, .5]],
    [[0, 0], [float("nan"), .5], [.5, .5]], [[0, 0], [1.1, .5], [.5, .5]],
])
def test_invalid_geometry_is_rejected(points):
    with pytest.raises(ValidationError):
        SlotRegion(slot_id=1, polygon=points)


def test_settings_and_explicit_empty_confirmation_are_bounded():
    with pytest.raises(ValidationError):
        OccupancySettings(empty_ratio=.2, occupied_ratio=.21)
    for value in (False, 1, "true"):
        with pytest.raises(ValidationError):
            CalibrationCreate(camera_id=1, reference_observation_id="00000000-0000-4000-8000-000000000000",
                regions=REGIONS, empty_reference_confirmed=value, request_id="test-key-1")
