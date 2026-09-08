"""Run inside a network-disabled, memory-limited Linux release container.

Uses a caller-supplied CC0 fixture, not production images or a database. This
checks resource stability only; it does not measure license-plate accuracy.
"""
import argparse
import io
import json
import resource
from pathlib import Path
from time import perf_counter

from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument("--image", type=Path, required=True)
parser.add_argument("--model", type=Path, required=True)
args = parser.parse_args()

# Account for the API's imported modules, not just an empty OCR process.
import main  # noqa: E402,F401
from expansion.vision_service import YoloRapidOCR, decode_image  # noqa: E402

runtime = YoloRapidOCR(args.model)
source = args.image.read_bytes()
samples = []
for index in range(6):
    data = source
    if index % 2:
        encoded = io.BytesIO()
        with Image.open(io.BytesIO(source)) as image:
            image.save(encoded, "JPEG", quality=88)
        data = encoded.getvalue()
    clean, _ = decode_image(data, "image/jpeg")
    started = perf_counter()
    detections = runtime.recognize(clean)
    assert detections, "Known fixture must exercise OCR, not just an empty detector"
    peak_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    samples.append({"seconds": round(perf_counter() - started, 3), "peak_mib": round(peak_mib, 1)})
    assert peak_mib < 512, "OCR plus API imports exceeded the 512 MiB release budget"
print(json.dumps({"passed": True, "samples": samples, "accuracy_measured": False}))
