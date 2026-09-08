"""Explicit one-time download of a pinned plate-specific YOLO ONNX artifact.

Never imported by the API. This command downloads data, never remote Python.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

REVISION = "8062e8e86734e272c60fa9a819433327ebdb66d7"
SOURCE = "https://huggingface.co/ml-debi/yolov8-license-plate-detection"
URL = f"{SOURCE}/resolve/{REVISION}/best.onnx"
SHA256 = "85d236280a1301ad98907947d284951dd2b20c23a6786ff50f7e6a8ec515bd50"


def download(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / "license-plate-yolov8n.onnx"
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != SHA256:
            raise ValueError("Existing model has a different digest; it was not overwritten")
        _provenance(output, destination.stat().st_size)
        return destination
    temporary = output / f"license-plate-yolov8n.{uuid4().hex}.partial"
    digest = hashlib.sha256()
    total = 0
    try:
        with urlopen(URL, timeout=60) as response, temporary.open("xb") as stream:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 16 * 1024 * 1024:
                    raise ValueError("Model exceeds expected size bound")
                digest.update(chunk)
                stream.write(chunk)
        if digest.hexdigest() != SHA256:
            raise ValueError("Model SHA256 does not match publisher artifact")
        temporary.rename(destination)
    finally:
        temporary.unlink(missing_ok=True)
    _provenance(output, total)
    return destination


def _provenance(output, total):
    (output / "MODEL_PROVENANCE.json").write_text(json.dumps({"publisher": "ml-debi", "source": SOURCE,
        "revision": REVISION, "sha256": SHA256, "bytes": total, "architecture": "YOLOv8n custom plate detector",
        "publisher_license_label": "MIT", "training_dataset": "not documented by publisher",
        "embedded_model_license": "AGPL-3.0 https://ultralytics.com/license",
        "license_note": "Publisher card and embedded license conflict; do not assume unrestricted MIT weights. Respect AGPL terms and clarify rights before commercial redistribution.",
        "limitations": "No measured Vietnamese plate accuracy; student pilot with mandatory human confirmation.",
        "ultralytics_license_reference": "https://www.ultralytics.com/license"}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "artifacts/vision")
    print(download(parser.parse_args().output))
