"""Existing PAP1 grants and pending money survive additive history rollout."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from expansion import online_payment_service
from expansion.online_payment_models import OnlinePaymentProcessing
from expansion.session_payment_models import SessionFeeCredit, SessionFeeQuote
from expansion.simplified_customer_models import SessionPaymentAccess, SessionPaymentAccessHistory
from expansion.simplified_customer_rollout import migrate_simplified_customer
from expansion.ticket_access_history_guards import TICKET_ACCESS_HISTORY_SQLITE_GUARDS
from test_session_online_payments import (
    parking_online, online, no_external_payment_configuration, portal, quote, link, receive,  # noqa: F401
)
from test_ticket_payer_review_regressions import ticket_payer, reverify_ticket


def test_sqlite_upgrade_preserves_existing_grant_and_pending_payment(parking_online):
    ctx = parking_online
    ticket_payer(ctx)
    access = ctx.db.scalar(select(SessionPaymentAccess))
    original = (access.id, access.created_at, access.expires_at, access.credential_version)
    ctx.clock[0] += timedelta(hours=23, minutes=59)
    proposal = quote(ctx)
    code = link(ctx, proposal)
    ctx.clock[0] += timedelta(seconds=30)
    identity = receive(ctx, code)
    ctx.db.commit()
    # Simulate the exact predecessor: existing tables, no archive table/triggers.
    engine = ctx.db.get_bind()
    with engine.begin() as connection:
        for name in TICKET_ACCESS_HISTORY_SQLITE_GUARDS:
            connection.exec_driver_sql(f'DROP TRIGGER {name}')
        connection.exec_driver_sql('DROP TABLE session_payment_access_history')
    migrate_simplified_customer(engine)
    migrate_simplified_customer(engine)
    ctx.db.expire_all()
    access = ctx.db.scalar(select(SessionPaymentAccess))
    assert (access.id, access.created_at, access.expires_at, access.credential_version) == original
    assert ctx.db.get(SessionFeeQuote, proposal['id']).status == 'pending'
    assert ctx.db.scalar(select(func.count()).select_from(SessionPaymentAccessHistory)) == 0
    ctx.clock[0] += timedelta(seconds=60)
    reverify_ticket(ctx)
    historical = ctx.db.scalar(select(SessionPaymentAccessHistory))
    assert (historical.access_id, historical.created_at, historical.expires_at, historical.credential_version) == original
    online_payment_service.process_inbox(ctx.db, identity, ctx.config, ctx.fee_gateway)
    assert ctx.db.get(OnlinePaymentProcessing, identity).status == 'processed'
    assert ctx.db.scalar(select(func.count()).select_from(SessionFeeCredit)) == 1


@pytest.mark.parametrize('mutation', ['extend', 'delete', 'replace', 'unrevoke', 'invent'])
def test_archived_grant_cannot_be_changed_or_reinstated(parking_online, mutation):
    ctx = parking_online
    ticket_payer(ctx)
    ctx.clock[0] += timedelta(hours=25)
    reverify_ticket(ctx)
    if mutation == 'unrevoke':
        access = ctx.db.scalar(select(SessionPaymentAccess))
        access.revoked_at = ctx.clock[0]
        ctx.db.commit()
        reverify_ticket(ctx)
    statements = {
        'extend': "UPDATE session_payment_access_history SET expires_at=datetime(expires_at,'+1 day')",
        'delete': 'DELETE FROM session_payment_access_history',
        'replace': 'INSERT OR REPLACE INTO session_payment_access_history SELECT * FROM session_payment_access_history',
        'unrevoke': 'UPDATE session_payment_access_history SET revoked_at=NULL',
        'invent': """INSERT INTO session_payment_access_history
            (access_id,created_at,expires_at,credential_version,vehicle_id,customer_snapshot_id,revoked_at)
            SELECT access_id,datetime(created_at,'-1 day'),expires_at,credential_version,vehicle_id,customer_snapshot_id,NULL
            FROM session_payment_access_history""",
    }
    with pytest.raises(IntegrityError, match='ticket access history'):
        with ctx.db.begin_nested():
            ctx.db.execute(text(statements[mutation]))
    assert ctx.db.scalar(select(func.count()).select_from(SessionPaymentAccessHistory)) == 1


def test_history_postgres_migration_is_frozen_additive_and_matches_model():
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable
    from expansion.ticket_access_history_guards import TICKET_ACCESS_HISTORY_POSTGRES_SQL
    from test_simplified_flow_migration import frozen
    import postgres_readiness as readiness
    migration = frozen('20260927_10')
    assert migration['down_revision'] == '20260923_09'
    assert str(CreateTable(SessionPaymentAccessHistory.__table__).compile(dialect=postgresql.dialect())).strip() in migration['UPGRADE_SQL']
    assert TICKET_ACCESS_HISTORY_POSTGRES_SQL in migration['UPGRADE_SQL']
    assert 'session_payment_access_history' in readiness.REQUIRED_TABLES
    assert {'trg_ticket_access_archive', 'trg_ticket_access_history_revoke', 'trg_ticket_access_history_guard'} <= readiness.REQUIRED_TRIGGERS
    assert not any(sql.lstrip().upper().startswith(('UPDATE ', 'DELETE ', 'DROP ', 'ALTER ')) for sql in migration['UPGRADE_SQL'])
