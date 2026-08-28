from pathlib import Path

from scripts.sync_source_snapshot import _is_allowed_candidate


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


def test_local_verify_runs_the_same_snapshot_parity_gate_as_ci() -> None:
    project_root = Path(__file__).resolve().parents[1]
    verify_script = (project_root / "scripts" / "verify.ps1").read_text(
        encoding="utf-8",
    )

    assert "sync_source_snapshot.py" in verify_script
    assert "--check" in verify_script
