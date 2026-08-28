import pytest

from scripts.production_rbac_probe import (
    PROBE_CASES,
    credential_env_names,
    validate_base_url,
)


def test_rbac_probe_only_uses_read_only_endpoints():
    assert PROBE_CASES
    assert all(case.method == "GET" for case in PROBE_CASES)
    assert all(case.path.startswith("/api/") for case in PROBE_CASES)


def test_rbac_probe_covers_privilege_boundaries():
    by_name = {case.name: case.expected_status for case in PROBE_CASES}

    assert by_name["own profile"] == {
        "customer": 200,
        "staff": 200,
        "manager": 200,
        "admin": 200,
    }
    assert by_name["staff zone list"] == {
        "customer": 403,
        "staff": 200,
        "manager": 200,
        "admin": 200,
    }
    assert by_name["manager user list"] == {
        "customer": 403,
        "staff": 403,
        "manager": 200,
        "admin": 200,
    }
    assert by_name["manager role list"] == by_name["manager user list"]


def test_credential_names_are_role_scoped_and_do_not_contain_values():
    username, password = credential_env_names("manager")

    assert username == "PARKINGAI_PROBE_MANAGER_USERNAME"
    assert password == "PARKINGAI_PROBE_MANAGER_PASSWORD"


def test_validate_base_url_requires_https_and_has_no_path():
    assert validate_base_url("https://api.parkingai.am/") == "https://api.parkingai.am"

    with pytest.raises(ValueError, match="HTTPS"):
        validate_base_url("http://api.parkingai.am")
    with pytest.raises(ValueError, match="origin"):
        validate_base_url("https://api.parkingai.am/api")
