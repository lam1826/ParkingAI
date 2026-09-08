"""Compatibility entry point for the shared, pinned model installer."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "backend/vision_model_install.py"), run_name="__main__")
