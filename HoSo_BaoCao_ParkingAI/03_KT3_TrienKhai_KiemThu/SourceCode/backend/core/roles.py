"""Canonical authorization roles shared by API validation and RBAC checks."""

ROLE_HIERARCHY: dict[str, int] = {
    "customer": 0,
    "staff": 1,
    "manager": 2,
    "admin": 3,
}

CANONICAL_ROLE_NAMES = frozenset(ROLE_HIERARCHY)
