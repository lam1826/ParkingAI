"""Batch presentation of verified credits without recomputing historical fees."""
from expansion.session_payment_service import credit_snapshot, credit_snapshots_many


def credit_details(session, snapshot):
    return {"online_paid": snapshot["total"], "paid_through": snapshot["paid_through"],
        "balance_due": max(session.parking_fee - snapshot["total"], 0)
            if session.status == "completed" and session.parking_fee is not None else None}


def credit_details_many(db, sessions):
    values = credit_snapshots_many(db, [row.id for row in sessions])
    return {row.id: credit_details(row, values[row.id]) for row in sessions}


def credit_details_one(db, session):
    return credit_details(session, credit_snapshot(db, session.id))
