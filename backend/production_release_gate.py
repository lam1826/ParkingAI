"""Fail a Fly release before rollout if production PostgreSQL is unsafe."""

from database import engine
from postgres_readiness import (
    assert_postgres_release_revision,
    check_postgres_readiness,
)


def main() -> int:
    check_postgres_readiness(engine, deep=True)
    assert_postgres_release_revision(engine)
    print("Production PostgreSQL deep readiness and revision verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
