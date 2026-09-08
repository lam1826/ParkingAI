"""Fail a Fly release before rollout if production PostgreSQL is unsafe."""

from core.config import settings
from database import engine
from postgres_readiness import (
    assert_postgres_release_revision,
    check_postgres_readiness,
)
from services.checkout_service import validate_checkout_signing_configuration


def validate_trusted_edge_proxy_configuration() -> None:
    if not settings.TRUSTED_EDGE_PROXY:
        raise RuntimeError("Production must enable TRUSTED_EDGE_PROXY behind the Fly proxy")


def main() -> int:
    validate_checkout_signing_configuration()
    validate_trusted_edge_proxy_configuration()
    check_postgres_readiness(engine, deep=True)
    assert_postgres_release_revision(engine)
    print("Production proxy, checkout signing, PostgreSQL deep readiness and revision verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
