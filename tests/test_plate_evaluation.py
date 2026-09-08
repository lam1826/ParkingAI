"""Answer-key fixtures for the offline benchmark, independent of model outputs."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("plate_eval", Path(__file__).resolve().parents[1] / "edge/evaluate_plates.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def sample(scene="full_frame"):
    return {"id": "fixture", "scene": scene, "plates": [{"text": "30A-123.45", "box": [0, 0, 100, 50]}]}


def detection(text="30A12345", box=None, confidence=.9):
    return {"plate": text, "box": box or [0, 0, 100, 50], "detector_confidence": confidence}


def prediction(*detections, suggested="30A12345"):
    return {"detections": list(detections), "suggested_plate": suggested}


def test_formatting_is_ignored_but_ambiguous_characters_are_not_repaired():
    assert evaluation.compact(" 30a-123.45 ") == "30A12345"
    assert evaluation.compact("3OA12345") != evaluation.compact("30A12345")
    assert evaluation.edit_distance("30A12345", "3OA12345") == 1
    assert evaluation.edit_distance("30A12345", "") == 8


def test_known_edit_distance_and_iou():
    assert evaluation.edit_distance("kitten", "sitting") == 3
    assert evaluation.iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(1 / 3)
    assert evaluation.iou([0, 0, 10, 10], [10, 0, 20, 10]) == 0


def test_one_ground_truth_cannot_match_two_predictions():
    row = evaluation.score_sample(sample(), prediction(detection(), detection(confidence=.8)), ["30A12345"])
    assert (row["true_positive"], row["false_positive"], row["false_negative"]) == (1, 1, 0)
    assert row["pipeline_exact"] == 1


def test_one_prediction_cannot_match_two_plates():
    item = sample()
    item["plates"].append(copy.deepcopy(item["plates"][0]))
    row = evaluation.score_sample(item, prediction(detection()), ["30A12345", "30A12345"])
    assert (row["true_positive"], row["false_negative"], row["pipeline_exact"]) == (1, 1, 1)


def test_correct_text_at_wrong_location_is_not_end_to_end_success():
    row = evaluation.score_sample(sample(), prediction(detection(box=[200, 200, 300, 250])), ["30A12345"])
    assert row["pipeline_exact"] == 0
    assert row["oracle_exact"] == 1
    assert row["pipeline_edits"] == row["characters"] == 8
    assert row["suggestion_needs_correction"] == 1


def test_missed_detection_and_no_result_stay_in_denominator():
    row = evaluation.score_sample(sample(), prediction(suggested=None), [None])
    summary = evaluation.summarize([row])
    assert summary["pipeline_whole_plate"]["rate"] == 0
    assert summary["pipeline_whole_plate"]["total"] == 1
    assert summary["suggestion_needs_correction_or_manual_entry"]["rate"] == 1
    assert summary["character_error_rate"]["pipeline"] == 1
    assert summary["detection_at_iou_0_5"]["recall"] == 0
    assert summary["detection_at_iou_0_5"]["precision"] is None


def test_wrong_highest_suggestion_is_counted_even_if_another_candidate_is_right():
    result = prediction(detection(), detection(text="OTHER", box=[200, 200, 300, 250]), suggested="OTHER")
    row = evaluation.score_sample(sample(), result, ["30A12345"])
    assert row["pipeline_exact"] == 1  # spatial plate metric
    assert row["suggestion_needs_correction"] == 1  # actual UI suggestion


def test_crop_metrics_do_not_masquerade_as_full_frame_detection():
    row = evaluation.score_sample(sample("plate_crop"), prediction(detection()), ["30A12345"])
    assert evaluation.summarize([row])["detection_at_iou_0_5"] is None


def test_unreadable_plate_counts_for_detection_only():
    item = sample()
    item["plates"][0]["text"] = None
    row = evaluation.score_sample(item, prediction(detection()), [None])
    summary = evaluation.summarize([row])
    assert summary["unreadable_plates"] == 1
    assert summary["pipeline_whole_plate"]["rate"] is None
    assert summary["detection_at_iou_0_5"]["recall"] == 1


def test_negative_frame_does_not_inflate_text_accuracy():
    item = sample()
    item["plates"] = []
    row = evaluation.score_sample(item, prediction(detection()), [])
    summary = evaluation.summarize([row])
    assert summary["negative_frames"]["false_positive_rate"] == 1
    assert summary["pipeline_whole_plate"]["rate"] is None
    assert summary["detection_at_iou_0_5"]["fp"] == 1


def test_aggregate_errors_and_intervals_have_known_values():
    good = evaluation.score_sample(sample(), prediction(detection()), ["30A12345"])
    bad = evaluation.score_sample(sample(), prediction(suggested=None), [None])
    bad["pipeline_error"] = 1
    summary = evaluation.summarize([good, bad])
    assert summary["pipeline_whole_plate"]["rate"] == .5
    assert summary["pipeline_errors"] == 1
    assert summary["character_error_rate"]["pipeline"] == .5
    assert evaluation.wilson(50, 100) == pytest.approx([.4038315, .5961685], abs=1e-6)
    assert evaluation.wilson(0, 0) is None
    assert evaluation.percentile([1, 2, 3, 4, 5], .95) == pytest.approx(4.8)


def manifest_fixture(tmp_path):
    image = tmp_path / "fixture.jpg"
    image.write_bytes(b"not decoded during metadata preflight")
    item = sample()
    item.update(file=image.name, sha256=hashlib.sha256(image.read_bytes()).hexdigest(), width=100, height=50)
    data = {"schema_version": 1, "dataset": {"id": "fixture", "source": "unit-test",
            "license": "test-only", "annotation_source": "answer-key", "selection": "all"}, "samples": [item]}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    return path, data


@pytest.mark.parametrize("case", ["empty", "duplicate_id", "duplicate_image", "checksum", "escape", "box", "nan", "provenance", "empty_text"])
def test_manifest_rejects_invalid_or_biased_inputs(tmp_path, case):
    path, data = manifest_fixture(tmp_path)
    item = data["samples"][0]
    if case == "empty":
        data["samples"] = []
    elif case in {"duplicate_id", "duplicate_image"}:
        other = copy.deepcopy(item)
        if case == "duplicate_image":
            other["id"] = "different-id"
        data["samples"].append(other)
    elif case == "checksum":
        item["sha256"] = "0" * 64
    elif case == "escape":
        item["file"] = "../outside.jpg"
    elif case == "box":
        item["plates"][0]["box"] = [0, 0, 101, 50]
    elif case == "nan":
        item["plates"][0]["box"] = [0, 0, float("nan"), 50]
    elif case == "provenance":
        del data["dataset"]["license"]
    elif case == "empty_text":
        item["plates"][0]["text"] = "---"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        evaluation.load_manifest(path)


def test_valid_manifest_is_checked_before_inference(tmp_path):
    path, data = manifest_fixture(tmp_path)
    assert evaluation.load_manifest(path) == data
