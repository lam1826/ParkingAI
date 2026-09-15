"""Offline evaluation of the raw single-frame baseline on explicitly labeled data.

No database, camera, remote images, weights download or application mutation.
This does not evaluate temporal confirmation, freshness or business matching.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from expansion import occupancy_engine as engine
from expansion.occupancy_schemas import OccupancySettings, SlotRegion


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    reference: str = Field(min_length=1, max_length=256)
    source: str = Field(min_length=1, max_length=256)
    regions: list[SlotRegion] = Field(min_length=1, max_length=64)
    labels: dict[str, Literal["empty", "occupied"]]

    @model_validator(mode="after")
    def labels_match_regions(self):
        ids = [str(region.slot_id) for region in self.regions]
        if len(set(ids)) != len(ids) or set(ids) != set(self.labels):
            raise ValueError("Each region needs exactly one independent empty/occupied label")
        return self


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    split: Literal["held_out"]
    synthetic: bool
    label_source: Literal["human", "synthetic"]
    settings: OccupancySettings = Field(default_factory=OccupancySettings)
    cases: list[EvaluationCase] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def provenance(self):
        if self.synthetic != (self.label_source == "synthetic"):
            raise ValueError("Synthetic data and independently human-labeled images must be distinguished")
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Case identifiers must be unique")
        return self


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate manifest JSON key")
        result[key] = value
    return result


def _local_image(root, name):
    relative = Path(name)
    if relative.is_absolute() or relative.drive or ".." in relative.parts or name.startswith(("\\", "/")) or ":" in name:
        raise ValueError("Image paths must be relative files inside the manifest directory")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > engine.MAX_BYTES:
        raise ValueError("Image missing, outside the dataset, or larger than 2 MB")
    return path.read_bytes()


def evaluate_manifest(path):
    path = Path(path).resolve()
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Manifest exceeds 2 MB")
    manifest = Manifest.model_validate(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object))
    if not engine.status()["available"]:
        raise ValueError("Install the optional local OpenCV/NumPy runtime before evaluating")
    settings = manifest.settings.model_dump()
    matrix = {actual: {predicted: 0 for predicted in ("empty", "occupied", "unknown")} for actual in ("empty", "occupied")}
    cases = []
    for case in manifest.cases:
        reference = _local_image(path.parent, case.reference)
        source = _local_image(path.parent, case.source)
        regions = [region.model_dump(mode="json") for region in case.regions]
        # Invalid/overlapping calibration is a dataset error, not a true negative.
        engine.validate_reference(reference, regions, settings)
        result = engine.analyze(reference, source, regions, settings)
        observations = []
        for reading in result["readings"]:
            actual = case.labels[str(reading["slot_id"])]
            predicted = reading["raw_state"]
            matrix[actual][predicted] += 1
            observations.append({"slot_id": reading["slot_id"], "actual": actual,
                "predicted": predicted, "reason": reading["reason"], "change_ratio": reading["change_ratio"]})
        cases.append({"id": case.id, "reference_sha256": hashlib.sha256(reference).hexdigest(),
            "source_sha256": hashlib.sha256(source).hexdigest(), "quality": result["quality"], "observations": observations})
    total = sum(sum(row.values()) for row in matrix.values())
    unknown = sum(row["unknown"] for row in matrix.values())
    decided = total - unknown
    correct = matrix["empty"]["empty"] + matrix["occupied"]["occupied"]
    return {"engine": engine.ENGINE, "evaluation_scope": "raw_single_frame_only",
        "dataset_kind": "synthetic_contract_cases" if manifest.synthetic else "user_labeled_held_out",
        "label_source": manifest.label_source, "split": manifest.split, "label_independence_verified": False,
        "note": "Synthetic results do not measure real-world accuracy." if manifest.synthetic else
            "Metrics describe only the supplied labels; independent labeling, camera conditions and held-out separation require human verification.",
        "settings": settings, "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "total_regions": total, "confusion_matrix": matrix,
        "unknown_count": unknown, "decided_coverage": decided / total,
        "accuracy_on_decided": correct / decided if decided else None,
        "false_empty_count": matrix["occupied"]["empty"], "false_occupied_count": matrix["empty"]["occupied"],
        "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_manifest(args.manifest)
    if args.output.resolve() == args.manifest.resolve() or args.output.exists():
        raise ValueError("Output must be a new file, separate from the input manifest")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"dataset_kind": result["dataset_kind"], "total_regions": result["total_regions"],
        "unknown_count": result["unknown_count"], "output": str(args.output)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
