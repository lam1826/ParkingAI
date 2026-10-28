"""Catalog display names: vehicle types and zones (review 28/10/2026 A-09)."""
import unicodedata


def collapse_name(value: str) -> str:
    """NFC text without surrounding whitespace and with inner runs of spaces collapsed to one."""
    return " ".join(unicodedata.normalize("NFC", value).split())


def name_key(value: str) -> str:
    """Comparison key: case, Vietnamese accents (đ as d) and spacing never make two names different.

    "Xe may DEMO" next to "Xe máy DEMO" or "xe   xc" next to "xe xc" would read
    as the same type or zone on every screen and receipt.
    """
    text = unicodedata.normalize("NFD", collapse_name(value).casefold().replace("đ", "d"))
    return "".join(char for char in text if not unicodedata.combining(char))


def lock_catalog_names(db, table: str) -> None:
    """Serialize the name check and the write of one catalog until commit (review round 2, BD-2).

    The database index only folds case, so two near-duplicate names created at
    the same time would both pass the check above. PostgreSQL takes a
    transaction advisory lock per catalog; SQLite's no-op write takes its single
    writer lock. Take it before reading the names and before any catalog row lock.
    """
    from sqlalchemy import text
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"catalog-names:{table}"})
    elif dialect == "sqlite":
        db.execute(text(f"UPDATE {table} SET id = id WHERE 0"))
