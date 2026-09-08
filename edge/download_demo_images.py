"""Explicitly download two CC0 photos for reproducible detector/OCR smoke checks.

These public foreign plates are not a Vietnamese accuracy benchmark. The API
never imports this downloader or accepts arbitrary image URLs.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

SAMPLES = [
    {"name": "rolls-royce-cc0.jpg", "author": "Paulo César Santos", "license": "CC0-1.0",
     "source": "https://commons.wikimedia.org/wiki/File:Rolls_Royce_in_Porto_Amboim,_Angola.JPG",
     "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Rolls_Royce_in_Porto_Amboim%2C_Angola.JPG/1280px-Rolls_Royce_in_Porto_Amboim%2C_Angola.JPG",
     "sha256": "90cfa1c05f5dd21ba337f938f7b3a638fa546207253c29c5fe0d9cb7f495ae3f",
     "human_reading": "LD-45-58-BI", "note": "Full car photograph resized by Wikimedia to 1280px; OCR may be incorrect."},
    {"name": "colorado-cc0.jpg", "author": "SuperSonic337", "license": "CC0-1.0",
     "source": "https://commons.wikimedia.org/wiki/File:Colorado_license_plate.jpg",
     "url": "https://upload.wikimedia.org/wikipedia/commons/1/13/Colorado_license_plate.jpg",
     "sha256": "28bfc42854374dc7f611b702e73cfca551cfb6bf3a6ea8ab8c54f128fc5d708c",
     "note": "Phone JPEG with MPO gain map; negative detector example in current smoke check."},
]


def download_samples(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    for sample in SAMPLES:
        destination = directory / sample["name"]
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).hexdigest() != sample["sha256"]:
                raise ValueError(f"Existing {sample['name']} differs; not overwritten")
            continue
        temporary = directory / f"{sample['name']}.{uuid4().hex}.partial"
        try:
            request = Request(sample["url"], headers={"User-Agent": "ParkingAI-Student-Demo/1.0"})
            with urlopen(request, timeout=30) as response:
                content = response.read(2 * 1024 * 1024 + 1)
            if len(content) > 2 * 1024 * 1024 or hashlib.sha256(content).hexdigest() != sample["sha256"]:
                raise ValueError("Sample changed or exceeded bound; refusing unverified image")
            temporary.write_bytes(content)
            temporary.rename(destination)
        finally:
            temporary.unlink(missing_ok=True)
    (directory / "SAMPLE_PROVENANCE.json").write_text(json.dumps(SAMPLES, indent=2), encoding="utf-8")
    return [str(directory / sample["name"]) for sample in SAMPLES]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "backend/artifacts/vision")
    print(json.dumps(download_samples(parser.parse_args().output), ensure_ascii=False, indent=2))
