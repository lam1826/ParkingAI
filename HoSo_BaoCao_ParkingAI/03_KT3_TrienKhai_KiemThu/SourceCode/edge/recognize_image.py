"""Run the real local detector/OCR on one owned or appropriately licensed photo."""
import argparse
import json
import os
import sys
import time
from pathlib import Path


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Save measured JSON evidence, including unsuccessful recognition")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    os.environ["PARKING_VISION_ENGINE"] = "yolo_rapidocr"
    os.environ["PARKING_VISION_MODEL"] = str(args.model.resolve())
    from expansion.vision_service import decode_image, recognize_image
    content = args.image.read_bytes()
    mime = "image/png" if content.startswith(b"\x89PNG") else "image/jpeg"
    image, _ = decode_image(content, mime)
    started = time.perf_counter()
    result = recognize_image(image)
    result.update(elapsed_seconds=round(time.perf_counter() - started, 3), image_width=image.width, image_height=image.height,
                  benchmark_claim=False, human_confirmation_required=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return int(result["ocr_status"] in {"error", "unavailable"})


if __name__ == "__main__":
    raise SystemExit(main())
