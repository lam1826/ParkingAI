"""Real React lookup state transitions with isolated API fixtures.

Run from the project virtualenv. Chrome and the existing Vite dependencies must
be installed. No production requests, login credentials or payment writes.
"""
from pathlib import Path

from plate_lookup_regression import ROOT, main


if __name__ == "__main__":
    raise SystemExit(main(
        Path(__file__).with_suffix(".js"),
        ROOT / "backend/artifacts/lookup-refresh-regression",
    ))
