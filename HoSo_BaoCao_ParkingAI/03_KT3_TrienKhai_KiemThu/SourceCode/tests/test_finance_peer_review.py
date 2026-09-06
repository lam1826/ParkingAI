"""Independent guard review: closed balances must be valid on every write path."""
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from core.clock import business_now
from models.cash_shift import CashShift


def test_direct_closed_shift_insert_cannot_fabricate_expected_cash(db_session, test_user):
    now = business_now()
    # No payment exists, so expected cash must equal the 100 VND opening cash.
    db_session.add(CashShift(staff_id=test_user.id, opened_at=now - timedelta(hours=1),
        closed_at=now, status="closed", opening_cash=100, counted_cash=0,
        expected_cash=0, difference=0))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
