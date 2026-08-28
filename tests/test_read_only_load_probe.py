import pytest

from scripts.read_only_load_probe import percentile, validate_target


def test_load_probe_only_allows_read_only_health_paths() -> None:
    assert validate_target("https://api.parkingai.am", "/ready") == (
        "https://api.parkingai.am/ready"
    )
    assert validate_target("https://api.parkingai.am/", "/") == (
        "https://api.parkingai.am/"
    )

    with pytest.raises(ValueError, match="read-only"):
        validate_target("https://api.parkingai.am", "/api/v1/users")


def test_load_probe_requires_https_except_explicit_localhost() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        validate_target("http://api.parkingai.am", "/ready")

    assert validate_target(
        "http://127.0.0.1:8000",
        "/ready",
        allow_http_localhost=True,
    ) == "http://127.0.0.1:8000/ready"


def test_percentile_is_nearest_rank_and_deterministic() -> None:
    assert percentile([10, 20, 30, 40, 50], 0.95) == 50
    assert percentile([50, 10, 30, 20, 40], 0.5) == 30
