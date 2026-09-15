"""Offline scorer contracts on generated images, not a real-camera benchmark."""
import json

import pytest

from scripts.evaluate_occupancy import evaluate_manifest
from test_occupancy_engine import frame, REGIONS


def dataset(tmp_path):
    (tmp_path / "reference.png").write_bytes(frame())
    (tmp_path / "occupied.png").write_bytes(frame(vehicle=True))
    (tmp_path / "dark.png").write_bytes(frame(flat=0))
    body = {"schema_version": 1, "split": "held_out", "synthetic": True, "label_source": "synthetic",
        "cases": [{"id": "empty", "reference": "reference.png", "source": "reference.png", "regions": REGIONS, "labels": {"1": "empty"}},
                  {"id": "occupied", "reference": "reference.png", "source": "occupied.png", "regions": REGIONS, "labels": {"1": "occupied"}},
                  {"id": "dark", "reference": "reference.png", "source": "dark.png", "regions": REGIONS, "labels": {"1": "occupied"}}]}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path, body


def test_offline_matrix_includes_unknown_and_distinguishes_synthetic_evidence(tmp_path):
    path, _ = dataset(tmp_path)
    result = evaluate_manifest(path)
    assert result["total_regions"] == 3
    assert result["confusion_matrix"] == {"empty": {"empty": 1, "occupied": 0, "unknown": 0}, "occupied": {"empty": 0, "occupied": 1, "unknown": 1}}
    assert result["decided_coverage"] == pytest.approx(2 / 3)
    assert result["accuracy_on_decided"] == 1
    assert result["dataset_kind"] == "synthetic_contract_cases"
    assert result["label_independence_verified"] is False
    assert "reference.png" not in json.dumps(result)


@pytest.mark.parametrize("change", ["unlabeled", "extra_label", "outside", "network", "wrong_split", "duplicate_case", "false_provenance"])
def test_manifest_rejects_misaligned_labels_and_nonlocal_data(tmp_path, change):
    path, body = dataset(tmp_path)
    if change == "unlabeled":
        body["cases"][0]["labels"] = {}
    elif change == "extra_label":
        body["cases"][0]["labels"]["2"] = "occupied"
    elif change == "outside":
        body["cases"][0]["source"] = "../outside.png"
    elif change == "network":
        body["cases"][0]["source"] = "https://example.invalid/image.png"
    elif change == "wrong_split":
        body["split"] = "training"
    elif change == "duplicate_case":
        body["cases"][1]["id"] = body["cases"][0]["id"]
    else:
        body["synthetic"] = False
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ValueError):
        evaluate_manifest(path)


def test_all_unknown_does_not_fabricate_decided_accuracy(tmp_path):
    path, body = dataset(tmp_path)
    body["cases"] = [body["cases"][-1]]
    path.write_text(json.dumps(body), encoding="utf-8")
    result = evaluate_manifest(path)
    assert result["decided_coverage"] == 0 and result["accuracy_on_decided"] is None
