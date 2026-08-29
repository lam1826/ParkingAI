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
    assert "%{time_total}" in workflow
    assert "Readiness latency exceeded" in workflow
    assert "issues: write" in workflow
    assert "Production monitor failed" in workflow
    assert "needs.public-contract.result" in workflow
    assert "--request POST" not in workflow
    assert "--request PUT" not in workflow
    assert "--request DELETE" not in workflow


def test_untrusted_cors_probe_accepts_the_expected_http_rejection() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "production-monitor.yml"
    ).read_text(encoding="utf-8")

    origin_marker = "--header 'Origin: https://evil.example'"
    origin_index = workflow.index(origin_marker)
    probe_start = workflow.rfind("curl ", 0, origin_index)
    status_check_end = workflow.index("\n          fi", origin_index)
    probe_end = workflow.index("\n          fi", status_check_end + 1)
    untrusted_probe = workflow[probe_start:probe_end]

    assert "--fail" not in untrusted_probe
    assert "--write-out '%{http_code}'" in untrusted_probe
    assert 'test "$evil_status" = "400"' in untrusted_probe
    assert "^access-control-allow-origin:" in untrusted_probe.lower()
