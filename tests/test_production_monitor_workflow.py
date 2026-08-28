from pathlib import Path


def test_production_monitor_is_read_only_and_checks_release_security_and_cors() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "production-monitor.yml"
    ).read_text(encoding="utf-8")

    assert "schedule:" in workflow
    assert "https://parkingai.am" in workflow
    assert "https://api.parkingai.am/ready" in workflow
    assert "release_id" in workflow
    assert "access-control-allow-origin" in workflow.lower()
    assert "content-security-policy" in workflow.lower()
    assert "strict-transport-security" in workflow.lower()
    assert "issues: write" in workflow
    assert "Production monitor failed" in workflow
    assert "needs.public-contract.result" in workflow
    assert "--request POST" not in workflow
    assert "--request PUT" not in workflow
    assert "--request DELETE" not in workflow
