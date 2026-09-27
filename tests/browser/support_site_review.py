"""Support forms must send the configured site in a multi-site database."""
from pathlib import Path
from plate_lookup_regression import main, ROOT

if __name__ == '__main__':
    raise SystemExit(main(Path(__file__).with_suffix('.js'), ROOT / 'backend/artifacts/dual-review-20260927'))
