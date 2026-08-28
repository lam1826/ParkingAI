from pathlib import Path


def test_jwt_stack_avoids_unfixed_python_ecdsa_dependency() -> None:
    requirements = (
        Path(__file__).resolve().parents[1] / "backend" / "requirements.txt"
    ).read_text(encoding="utf-8").lower().splitlines()

    assert "pyjwt==2.13.0" in requirements
    assert "cryptography==50.0.1" in requirements
    assert not any(line.startswith("python-jose==") for line in requirements)
    assert not any(line.startswith("ecdsa==") for line in requirements)
