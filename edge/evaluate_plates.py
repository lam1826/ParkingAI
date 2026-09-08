"""Offline, labelled evaluation of the released detector/OCR; never calls the API.

Images, manifests and per-image results belong in backend/artifacts (ignored).
Scoring only strips formatting: it NEVER maps O to 0 or corrects predictions
using the answer key. Crop and full-frame results are reported separately.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from time import perf_counter
from datetime import datetime, timezone


def compact(text):
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def edit_distance(expected, predicted):
    previous = list(range(len(predicted) + 1))
    for index, char in enumerate(expected, 1):
        current = [index]
        for other, candidate in enumerate(predicted, 1):
            current.append(min(current[-1] + 1, previous[other] + 1,
                               previous[other - 1] + (char != candidate)))
        previous = current
    return previous[-1]


def iou(a, b):
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - overlap
    return overlap / union if union else 0.0


def match_boxes(plates, detections, threshold=0.5):
    """Confidence-ordered, one-to-one matching at a FIXED operating point.

    This is precision/recall at IoU 0.5, not mAP/AP across score thresholds.
    """
    available = set(range(len(plates)))
    matches = {}
    for index in sorted(range(len(detections)),
                        key=lambda i: detections[i].get("detector_confidence", 0), reverse=True):
        if not available:
            break
        target = max(available, key=lambda i: iou(plates[i]["box"], detections[index]["box"]))
        if iou(plates[target]["box"], detections[index]["box"]) >= threshold:
            matches[target] = index
            available.remove(target)
    return matches


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def wilson(successes, count):
    if not count:
        return None
    z = 1.959963984540054
    p = successes / count
    center = (p + z * z / (2 * count)) / (1 + z * z / count)
    half = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / (1 + z * z / count)
    return [max(0, center - half), min(1, center + half)]


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def load_manifest(path):
    path = Path(path).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("dataset"), dict):
        raise ValueError("Expected manifest schema_version=1 and dataset metadata")
    for key in ("id", "source", "license", "annotation_source", "selection"):
        if not manifest["dataset"].get(key):
            raise ValueError(f"Missing dataset provenance: {key}")
    samples = manifest.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("Empty evaluation set: there is no accuracy to report")
    ids, hashes = set(), set()
    for sample in samples:
        if not isinstance(sample.get("id"), str) or not sample["id"] or sample["id"] in ids:
            raise ValueError("Missing or duplicate sample ID")
        ids.add(sample["id"])
        relative = Path(sample.get("file", ""))
        target = (path.parent / relative).resolve()
        if relative.is_absolute() or not target.is_relative_to(path.parent) or not target.is_file():
            raise ValueError(f"Image must be an existing file inside the manifest directory: {sample['id']}")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != sample.get("sha256") or digest in hashes:
            raise ValueError(f"Image checksum mismatch or duplicate image: {sample['id']}")
        hashes.add(digest)
        if sample.get("scene") not in {"plate_crop", "full_frame"}:
            raise ValueError("Specify plate_crop or full_frame for every sample")
        width, height = sample.get("width"), sample.get("height")
        if not all(type(v) is int and v > 0 for v in (width, height)):
            raise ValueError("Positive integer dimensions are required in oriented source coordinates")
        plates = sample.get("plates")
        if not isinstance(plates, list) or (sample["scene"] == "plate_crop" and len(plates) != 1):
            raise ValueError("A plate crop must contain exactly one labelled plate")
        for plate in plates:
            label = plate.get("text")
            if label is not None and (not isinstance(label, str) or not compact(label)):
                raise ValueError("Use text=null for an unreadable plate, never an empty label")
            box = plate.get("box")
            if sample["scene"] == "full_frame" or box is not None:
                if not isinstance(box, list) or len(box) != 4 or not all(
                    type(v) in (int, float) and math.isfinite(v) for v in box
                ) or not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
                    raise ValueError(f"Invalid ground-truth box: {sample['id']}")
    return manifest


def score_sample(sample, prediction, oracle_texts):
    plates = sample["plates"]
    detections = prediction.get("detections", [])
    full_frame = sample["scene"] == "full_frame"
    matches = match_boxes(plates, detections) if full_frame else {}
    row = {"id": sample["id"], "scene": sample["scene"], "group": sample.get("group", "unspecified"),
           "readable_plates": 0, "unreadable_plates": 0, "pipeline_exact": 0,
           "oracle_exact": 0, "characters": 0, "pipeline_edits": 0, "oracle_edits": 0,
           "suggestion_evaluable": 0, "suggestion_needs_correction": 0,
           "true_positive": len(matches) if full_frame else None,
           "false_positive": len(detections) - len(matches) if full_frame else None,
           "false_negative": len(plates) - len(matches) if full_frame else None,
           "negative_frame": int(full_frame and not plates),
           "negative_frame_with_detection": int(full_frame and not plates and bool(detections))}
    for index, plate in enumerate(plates):
        if plate.get("text") is None:
            row["unreadable_plates"] += 1
            continue
        expected = compact(plate["text"])
        if full_frame:
            actual = compact(detections[matches[index]].get("plate")) if index in matches else ""
        else:
            actual = compact(prediction.get("suggested_plate"))
        oracle = compact(oracle_texts[index]) if index < len(oracle_texts) else ""
        row["readable_plates"] += 1
        row["pipeline_exact"] += int(expected == actual)
        row["oracle_exact"] += int(expected == oracle)
        row["characters"] += len(expected)
        row["pipeline_edits"] += edit_distance(expected, actual)
        row["oracle_edits"] += edit_distance(expected, oracle)
    if len(plates) == 1 and plates[0].get("text") is not None:
        row["suggestion_evaluable"] = 1
        # Count abstention/no_plate/error as manual work, not as success.
        # On full frames a text guess at the wrong location is not correct.
        row["suggestion_needs_correction"] = int(
            row["pipeline_exact"] != 1 or compact(prediction.get("suggested_plate")) != compact(plates[0]["text"]))
    return row


def summarize(rows):
    def total(key):
        return sum(row.get(key) or 0 for row in rows)
    count = total("readable_plates")
    exact = total("pipeline_exact")
    oracle = total("oracle_exact")
    tp, fp, fn = (total(k) for k in ("true_positive", "false_positive", "false_negative"))
    return {
        "images": len(rows), "readable_plates": count, "unreadable_plates": total("unreadable_plates"),
        "pipeline_whole_plate": {"correct": exact, "total": count, "rate": ratio(exact, count),
                                  "wilson95_descriptive_only": wilson(exact, count)},
        "ocr_on_ground_truth_crop": {"correct": oracle, "total": count, "rate": ratio(oracle, count)},
        "character_error_rate": {"pipeline": ratio(total("pipeline_edits"), total("characters")),
                                 "oracle_crop": ratio(total("oracle_edits"), total("characters"))},
        "suggestion_needs_correction_or_manual_entry": {
            "count": total("suggestion_needs_correction"), "total": total("suggestion_evaluable"),
            "rate": ratio(total("suggestion_needs_correction"), total("suggestion_evaluable"))},
        "detection_at_iou_0_5": {"tp": tp, "fp": fp, "fn": fn,
                                 "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn)}
            if any(row["scene"] == "full_frame" for row in rows) else None,
        "negative_frames": {"count": total("negative_frame"),
                            "with_detection": total("negative_frame_with_detection"),
                            "false_positive_rate": ratio(total("negative_frame_with_detection"), total("negative_frame"))},
        "pipeline_errors": total("pipeline_error"), "oracle_errors": total("oracle_error"),
        "pipeline_seconds": {"p50": percentile([r["pipeline_seconds"] for r in rows if "pipeline_seconds" in r], .5),
                             "p95": percentile([r["pipeline_seconds"] for r in rows if "pipeline_seconds" in r], .95)},
    }


def read_ground_truth_crop(engine, image):
    """Same bounded RapidOCR configuration and reading order, bypassing YOLO.

    This diagnostic uses the annotated crop, so it must never be labelled as
    end-to-end recognition accuracy or be substituted for website predictions.
    """
    import numpy as np
    from expansion.vision_service import _prepare_plate_crop, normalize_candidate
    crop = _prepare_plate_crop(image)
    lines, _ = engine.ocr(np.asarray(crop)[:, :, ::-1].copy(), use_cls=False)
    lines = lines or []
    lines.sort(key=lambda line: (round(min(p[1] for p in line[0]) / 10), min(p[0] for p in line[0])))
    return normalize_candidate("".join(str(line[1]) for line in lines))


def evaluate(manifest_path, model_path, output):
    manifest_path, model_path, output = map(lambda p: Path(p).resolve(), (manifest_path, model_path, output))
    manifest = load_manifest(manifest_path)  # Freeze/check ALL images before any predictions.
    output.mkdir(parents=True, exist_ok=True)
    if (output / "results.json").exists() or (output / "predictions.jsonl").exists():
        raise ValueError("Use a new output directory; evaluation evidence is not overwritten")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "backend"))
    # Importing application models must not even configure a production DB.
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["AI_ENABLED"] = "false"
    from PIL import Image, ImageOps
    from expansion.vision_service import YoloRapidOCR, decode_image
    from vision_model_install import SHA256, REVISION
    model_digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if model_digest != SHA256:
        raise ValueError("This acceptance run requires the pinned production model")
    os.environ["PARKING_VISION_MODEL_SHA256"] = SHA256
    started = perf_counter()
    engine = YoloRapidOCR(model_path)
    initialization_seconds = perf_counter() - started
    rows = []
    with (output / "predictions.jsonl").open("x", encoding="utf-8") as stream:
        for index, original in enumerate(manifest["samples"]):
            sample = json.loads(json.dumps(original))
            prediction = {"detections": [], "suggested_plate": None}
            oracle_texts = [None] * len(sample["plates"])
            pipeline_error = oracle_error = 0
            error_type = None
            start = perf_counter()
            image = None
            try:
                content = (manifest_path.parent / sample["file"]).read_bytes()
                import io
                with Image.open(io.BytesIO(content)) as source:
                    oriented = ImageOps.exif_transpose(source)
                    if oriented.size != (sample["width"], sample["height"]):
                        raise ValueError("Image dimensions differ from annotation coordinates")
                image, _ = decode_image(content, "image/png" if content.startswith(b"\x89PNG") else "image/jpeg")
                sx, sy = image.width / sample["width"], image.height / sample["height"]
                for plate in sample["plates"]:
                    if "box" in plate:
                        plate["box"] = [plate["box"][0] * sx, plate["box"][1] * sy,
                                        plate["box"][2] * sx, plate["box"][3] * sy]
                detections = engine.recognize(image)
                candidates = [d for d in detections if d.get("plate")]
                best = max(candidates, key=lambda d: d["confidence"]) if candidates else None
                prediction = {"detections": detections, "suggested_plate": best["plate"] if best else None}
            except Exception as error:
                pipeline_error = 1
                error_type = type(error).__name__
            pipeline_seconds = perf_counter() - start
            if image is not None:
                for number, plate in enumerate(sample["plates"]):
                    if plate.get("text") is None:
                        continue
                    try:
                        crop = image.crop(tuple(round(v) for v in plate["box"])) if "box" in plate else image
                        oracle_texts[number] = read_ground_truth_crop(engine, crop)
                    except Exception:
                        oracle_error += 1
            else:
                oracle_error = sum(p.get("text") is not None for p in sample["plates"])
            score = score_sample(sample, prediction, oracle_texts)
            score.update(pipeline_seconds=pipeline_seconds, pipeline_error=pipeline_error, oracle_error=oracle_error)
            rows.append(score)
            stream.write(json.dumps({"id": sample["id"], "prediction": prediction, "oracle_texts": oracle_texts,
                                     "score": score, "error_type": error_type}, ensure_ascii=False) + "\n")
            stream.flush()
            if (index + 1) % 25 == 0 or index + 1 == len(manifest["samples"]):
                print(json.dumps({"processed": index + 1, "total": len(manifest["samples"])}), flush=True)
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unavailable"
    result = {
        "schema_version": 1, "measured_at": datetime.now(timezone.utc).isoformat(),
        "dataset": manifest["dataset"], "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "model_sha256": model_digest, "model_revision": REVISION, "checkout_sha": commit,
        "runtime_source_sha256": hashlib.sha256((root / "backend/expansion/vision_service.py").read_bytes()).hexdigest(),
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runtime": {"os": platform.system(), "python": platform.python_version(),
                    "onnxruntime": importlib.metadata.version("onnxruntime"),
                    "rapidocr_onnxruntime": importlib.metadata.version("rapidocr-onnxruntime")},
        "initialization_seconds": initialization_seconds,
        "groups": {f"{scene}/{group}": summarize([r for r in rows if r["scene"] == scene and r["group"] == group])
                   for scene, group in sorted({(r["scene"], r["group"]) for r in rows})},
        "scenes": {scene: summarize([r for r in rows if r["scene"] == scene]) for scene in sorted({r["scene"] for r in rows})},
        "physical_phone_verified": False,
        "limitations": ["Selected-set measurement only; not an accuracy guarantee for Vietnam or a parking lot.",
                        "Public model training data are undocumented; training overlap is unknown.",
                        "Ground-truth-crop OCR bypasses detection. Crop tests do not establish full-frame detection.",
                        "Correction rate includes no result and inference errors, before human edits.",
                        "Wilson intervals are descriptive; correlated frames and stratification limit population inference.",
                        "Local backend preprocessing and inference; not phone capture, client JPEG conversion, or Fly latency."],
    }
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output / "results.json"), "scenes": result["scenes"]}, ensure_ascii=False, indent=2))
    return 2 if any(r["pipeline_error"] or r["oracle_error"] for r in rows) else 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return evaluate(args.manifest, args.model, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
