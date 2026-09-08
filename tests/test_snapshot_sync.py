from pathlib import Path

import pytest

import scripts.sync_source_snapshot as snapshot
from scripts.sync_source_snapshot import _is_allowed_candidate

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_snapshot_candidate_policy_allows_source_but_blocks_local_secrets() -> None:
    assert _is_allowed_candidate(Path("backend/db_rollout.py"), is_tracked=False)
    assert _is_allowed_candidate(
        Path("frontend/src/pages/Example.jsx"),
        is_tracked=False,
    )
    assert _is_allowed_candidate(Path("backend/.env.example"), is_tracked=True)
    assert _is_allowed_candidate(
        Path(".github/workflows/delivery.yml"), is_tracked=False
    )
    assert _is_allowed_candidate(
        Path("deploy/compose.blue-green.yml"), is_tracked=False
    )

    blocked = (
        "frontend/.env",
        "frontend/.env.production",
        "backend/service-account.json",
        "backend/credentials.json",
        "backend/private-key.pem",
        "backend/signing.key",
        "frontend/.npmrc",
        "backend/local-data.json",
        "backend/local-settings.yaml",
        "backend/local-settings.toml",
    )
    for relative in blocked:
        assert not _is_allowed_candidate(Path(relative), is_tracked=False), relative


def test_local_verify_runs_snapshot_parity_gate_but_ci_does_not() -> None:
    """HoSo_BaoCao_ParkingAI/ is gitignored, so a CI checkout never holds the
    mirror: a CI step would be permanently red (before) or permanently green
    (with the skip). The parity gate lives in scripts/verify.ps1 only."""
    verify_script = (PROJECT_ROOT / "scripts" / "verify.ps1").read_text(
        encoding="utf-8",
    )
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8",
    )

    assert "sync_source_snapshot.py" in verify_script
    assert "--check" in verify_script
    assert "sync_source_snapshot" not in workflow


def test_demo_snapshot_includes_reproducible_setup_but_never_runtime_data():
    for path in ("edge/download_vision_model.py", "backend/requirements-vision.txt", "scripts/demo_server.py", "plan.md"):
        assert _is_allowed_candidate(Path(path), is_tracked=False), path
    for path in ("backend/artifacts/demo/scratch.db.demo.json", "backend/artifacts/vision/MODEL_PROVENANCE.json", "backend/model.onnx", "edge/weights.pt"):
        assert not _is_allowed_candidate(Path(path), is_tracked=True), path


@pytest.fixture
def fake_dossier(tmp_path, monkeypatch):
    dossier = tmp_path / "HoSo_BaoCao_ParkingAI"
    mirror = dossier / "03_KT3_TrienKhai_KiemThu" / "SourceCode"
    monkeypatch.setattr(snapshot, "DOSSIER_ROOT", dossier)
    monkeypatch.setattr(snapshot, "SNAPSHOT", mirror)
    monkeypatch.setattr(snapshot, "_candidate_paths", lambda: {Path("README.md")})
    return dossier, mirror


def test_check_skips_with_exit_0_when_dossier_is_absent(fake_dossier, capsys):
    """CI checkouts and fresh clones never contain the gitignored dossier."""
    assert snapshot.check() == 0
    captured = capsys.readouterr()
    assert snapshot.SKIP_NOTICE in captured.out
    assert captured.err == ""


def test_check_fails_when_dossier_present_but_mirror_never_synced(fake_dossier, capsys):
    dossier, _ = fake_dossier
    dossier.mkdir()
    assert snapshot.check() == 1
    assert (
        "missing: HoSo_BaoCao_ParkingAI/03_KT3_TrienKhai_KiemThu/SourceCode/"
        in capsys.readouterr().err
    )


def test_check_fails_on_stale_mirror_and_passes_when_in_sync(fake_dossier):
    _, mirror = fake_dossier
    mirror.mkdir(parents=True)
    assert snapshot.check() == 1
    (mirror / "README.md").write_bytes(b"stale")
    assert snapshot.check() == 1
    (mirror / "README.md").write_bytes((snapshot.ROOT / "README.md").read_bytes())
    assert snapshot.check() == 0


def test_check_still_rejects_forbidden_files_in_mirror(fake_dossier):
    _, mirror = fake_dossier
    mirror.mkdir(parents=True)
    (mirror / "README.md").write_bytes((snapshot.ROOT / "README.md").read_bytes())
    (mirror / "leaked.db").write_bytes(b"x")
    assert snapshot.check() == 1
