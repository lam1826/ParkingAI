"""Prepare a fixed, real-crop subset from a user-downloaded Kaggle archive.

No network access; no model predictions are used for selection. Images/labels
are written beneath backend/artifacts by default and must remain outside Git.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from PIL import Image

ARCHIVE_SHA256 = "34c5c11d6bd73e9f403a67d8b970c598a144d74a8e4e23689876e3caff9105de"
SOURCE = "https://www.kaggle.com/datasets/topkek69/vietnamese-license-plate-ocr/versions/9"
SELECTION_SEED = "ParkingAI-PARK209-frozen-v1"


def prepare(archive_path, directory):
    archive_path, directory = Path(archive_path).resolve(), Path(directory).resolve()
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Expected the pinned version-9 archive; refusing changed data")
    destination = directory / "manifest-crops.json"
    if destination.exists():
        raise ValueError("Manifest already exists: choose a new directory to preserve evidence")
    samples, seen, counts = [], set(), {"car": 0, "mb": 0}
    with zipfile.ZipFile(archive_path) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read("labels/crop_labels.csv").decode("utf-8-sig"))))
        candidates = [row for row in rows if re.fullmatch(r"(?:car|mb)_\d+\.jpg", row["Name"])]
        candidates.sort(key=lambda row: hashlib.sha256((SELECTION_SEED + "|" + row["Name"]).encode()).hexdigest())
        selected = []
        for row in candidates:
            label = re.sub(r"[^A-Z0-9]", "", row["Label"].upper())
            kind = row["Name"].split("_")[0]
            if not label or label in seen or counts[kind] >= 250:
                continue
            seen.add(label)
            selected.append(row)
            counts[kind] += 1
        if counts != {"car": 250, "mb": 250}:
            raise ValueError("Archive does not provide the expected 500 unique-plate subset")
        (directory / "crops").mkdir(parents=True, exist_ok=True)
        for row in selected:
            member = "cropped/" + row["Name"]
            if archive.getinfo(member).file_size > 2 * 1024 * 1024:
                raise ValueError("Unexpected source image size")
            content = archive.read(member)
            target = directory / "crops" / row["Name"]
            if target.exists() and target.read_bytes() != content:
                raise ValueError("Existing image differs from pinned archive")
            if not target.exists():
                target.write_bytes(content)
            with Image.open(io.BytesIO(content)) as image:
                width, height = image.size
            samples.append({"id": target.stem, "file": target.relative_to(directory).as_posix(),
                            "sha256": hashlib.sha256(content).hexdigest(), "width": width, "height": height,
                            "scene": "plate_crop", "group": "car" if row["Name"].startswith("car_") else "motorbike",
                            "source_member": member, "plates": [{"text": row["Label"]}]})
    manifest = {"schema_version": 1, "dataset": {
        "id": "parkingai-vn-crops-500-v1", "source": SOURCE, "version": 9,
        "license": "Apache-2.0 (publisher Kaggle metadata; source-chain not independently established)",
        "archive_sha256": ARCHIVE_SHA256,
        "annotation_source": "Publisher labels/crop_labels.csv; first 20 selected labels visually checked before inference",
        "selection": "car_ and mb_ only; SHA256(seed|filename) order, first 250 each, unique normalized plates; no generated/ images",
        "selection_seed": SELECTION_SEED, "source_candidates": len(candidates),
        "limitations": ["Already-cropped plates, not full-vehicle photos", "Balanced sample is not natural prevalence",
                        "No tuning in this evaluation; overlap with publisher model training is unknown",
                        "Ground truth comes from publisher; 500 labels have not all been independently re-annotated"],
    }, "samples": samples}
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(destination), "samples": len(samples), "groups": counts,
                      "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}, ensure_ascii=True))
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.archive, args.output)
