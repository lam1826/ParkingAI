"""Additive demo import: same contract on SQLite and restored PostgreSQL."""
from sqlalchemy import func, select
import pytest

from expansion.showcase_seed import ACCOUNTS, preview, seed
from models import ParkingSession, User
from models.payment import Payment


def test_showcase_dry_run_and_replay_preserve_existing_data(db_session, test_user):
    original = (test_user.id, test_user.username, test_user.password_hash, test_user.role_id)
    before = db_session.scalar(select(func.count()).select_from(User))
    planned = preview(db_session, "demoround3")
    assert planned["planned"]["accounts"] == 7
    assert db_session.scalar(select(func.count()).select_from(User)) == before
    hashes = {name: "$2b$12$" + chr(65+i)*53 for i, name in enumerate(ACCOUNTS)}
    first = seed(db_session, "demoround3", hashes)
    db_session.commit()
    session_count = db_session.scalar(select(func.count()).select_from(ParkingSession))
    assert first["created"]["users"] == 7 and first["created"]["parking_sites"] == 2
    assert session_count > 2000
    second = seed(db_session, "demoround3", hashes)
    db_session.commit()
    assert second["created"] == {}
    assert second["ids"] == first["ids"]
    assert db_session.scalar(select(func.count()).select_from(Payment)) == 0
    db_session.refresh(test_user)
    assert (test_user.id, test_user.username, test_user.password_hash, test_user.role_id) == original
    hashes["admin"] = "$2b$12$" + "Z"*53
    with pytest.raises(ValueError, match="not overwritten"):
        seed(db_session, "demoround3", hashes)
    db_session.rollback()


def test_showcase_rejects_non_namespaced_import(db_session):
    with pytest.raises(ValueError, match="Namespace"):
        preview(db_session, "production")
