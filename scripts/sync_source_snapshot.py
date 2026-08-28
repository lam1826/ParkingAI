"""Đồng bộ và kiểm tra bản mirror SourceCode trong hồ sơ bàn giao.

Mặc định script copy các file được Git quản lý và một allowlist hẹp cho source
chưa track. ``--check`` chỉ đọc và trả exit 1 nếu mirror lệch hoặc chứa
artifact/runtime secret. Không bao giờ đi ra ngoài SourceCode cố định.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = (
    ROOT
    / "HoSo_BaoCao_ParkingAI"
    / "03_KT3_TrienKhai_KiemThu"
    / "SourceCode"
)
SNAPSHOT_PREFIX = SNAPSHOT.relative_to(ROOT).as_posix() + "/"
ALLOWED_TOP_LEVEL = {".github", "backend", "docs", "frontend", "scripts", "tests"}
ALLOWED_ROOT_FILES = {"README.md", "package.json", "package-lock.json", "pytest.ini"}
EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "database",
    "dist",
    "node_modules",
    "venv",
}
FORBIDDEN_SUFFIXES = {".db", ".pyc", ".pyo", ".log", ".zip"}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt", ".cer"}
SECRET_EXACT_NAMES = {".npmrc", ".pypirc", "id_rsa", "id_ed25519"}
SECRET_NAME_MARKERS = {"credential", "service-account", "service_account"}
SAFE_UNTRACKED_SUFFIXES = {
    ".bat",
    ".css",
    ".html",
    ".js",
    ".jsx",
    ".md",
    ".ps1",
    ".py",
    ".rst",
    ".scss",
    ".sh",
    ".svg",
    ".ts",
    ".tsx",
}


def _is_sensitive_path(relative: Path) -> bool:
    name = relative.name.lower()
    if name == ".env.example":
        return False
    if name == ".env" or name.startswith(".env."):
        return True
    if name in SECRET_EXACT_NAMES:
        return True
    if relative.suffix.lower() in SECRET_SUFFIXES:
        return True
    return any(marker in name for marker in SECRET_NAME_MARKERS)


def _is_allowed_candidate(relative: Path, *, is_tracked: bool) -> bool:
    posix = relative.as_posix()
    if posix.startswith(SNAPSHOT_PREFIX):
        return False
    if _is_sensitive_path(relative):
        return False
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if relative.suffix.lower() in FORBIDDEN_SUFFIXES:
        return False
    if len(relative.parts) == 1:
        if relative.name not in ALLOWED_ROOT_FILES:
            return False
    elif relative.parts[0] not in ALLOWED_TOP_LEVEL:
        return False
    return is_tracked or relative.suffix.lower() in SAFE_UNTRACKED_SUFFIXES


def _git_paths(*arguments: str) -> set[Path]:
    completed = subprocess.run(
        ["git", *arguments, "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return {
        Path(raw.decode("utf-8"))
        for raw in completed.stdout.split(b"\0")
        if raw
    }


def _candidate_paths() -> set[Path]:
    tracked = _git_paths("ls-files", "--cached")
    untracked = _git_paths("ls-files", "--others", "--exclude-standard")
    result: set[Path] = set()
    for relative in tracked | untracked:
        if not _is_allowed_candidate(relative, is_tracked=relative in tracked):
            continue
        # `git ls-files --cached` vẫn liệt kê file tracked vừa bị xóa trong
        # working tree; mirror phải phản ánh filesystem/source hiện tại.
        if not (ROOT / relative).is_file():
            continue
        result.add(relative)
    return result


def _snapshot_files() -> set[Path]:
    if not SNAPSHOT.exists():
        return set()
    return {
        path.relative_to(SNAPSHOT)
        for path in SNAPSHOT.rglob("*")
        if path.is_file()
    }


def _is_forbidden(relative: Path) -> bool:
    return (
        _is_sensitive_path(relative)
        or relative.suffix.lower() in FORBIDDEN_SUFFIXES
        or any(part == "__pycache__" for part in relative.parts)
    )


def _differences(expected: set[Path]) -> tuple[list[Path], list[Path], list[Path]]:
    actual = _snapshot_files()
    missing_or_changed = [
        relative
        for relative in sorted(expected)
        if not (SNAPSHOT / relative).is_file()
        or (ROOT / relative).read_bytes() != (SNAPSHOT / relative).read_bytes()
    ]
    unexpected = sorted(actual - expected)
    forbidden = sorted(relative for relative in actual if _is_forbidden(relative))
    return missing_or_changed, unexpected, forbidden


def sync() -> None:
    expected = _candidate_paths()
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    missing_or_changed, unexpected, _ = _differences(expected)

    for relative in missing_or_changed:
        destination = (SNAPSHOT / relative).resolve()
        if SNAPSHOT.resolve() not in destination.parents:
            raise RuntimeError(f"Đường dẫn snapshot không an toàn: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)

    for relative in unexpected:
        target = (SNAPSHOT / relative).resolve()
        if SNAPSHOT.resolve() not in target.parents:
            raise RuntimeError(f"Đường dẫn xóa không an toàn: {target}")
        target.unlink()

    for directory in sorted(
        (path for path in SNAPSHOT.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            pass

    print(
        f"Snapshot synchronized: {len(expected)} files; "
        f"copied {len(missing_or_changed)}, removed {len(unexpected)}."
    )


def check() -> int:
    expected = _candidate_paths()
    missing_or_changed, unexpected, forbidden = _differences(expected)
    for label, paths in (
        ("missing/changed", missing_or_changed),
        ("unexpected", unexpected),
        ("forbidden", forbidden),
    ):
        for relative in paths:
            print(f"{label}: {relative.as_posix()}", file=sys.stderr)
    if missing_or_changed or unexpected or forbidden:
        return 1
    print(f"Snapshot parity OK: {len(expected)} files, no runtime artifacts.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Chỉ kiểm tra, không sửa")
    args = parser.parse_args()
    if args.check:
        return check()
    sync()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
