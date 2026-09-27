"""Delayed lookup must not replace an operator's newer vehicle selection."""
from pathlib import Path
from plate_lookup_regression import main, ROOT

if __name__ == '__main__':
    raise SystemExit(main(Path(__file__).with_suffix('.js'), ROOT / 'backend/artifacts/dual-review-20260927'))
