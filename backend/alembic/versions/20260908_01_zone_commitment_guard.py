"""Prevent zone deactivation while parking commitments remain.

Revision ID: 20260908_01
Revises: 20260907_02
"""
from alembic import op


revision = "20260908_01"
down_revision = "20260907_02"
branch_labels = None
depends_on = None


ZONE_COMMITMENT_POSTGRES_GUARD_SQL = """
CREATE OR REPLACE FUNCTION parking_zone_commitment_guard() RETURNS trigger AS $$
BEGIN
    IF NOT NEW.is_active AND OLD.is_active AND (
        EXISTS (SELECT 1 FROM parking_reservations r JOIN parking_slots s ON s.id=r.slot_id
                WHERE s.zone_id=OLD.id AND r.status IN ('confirmed','arrived')
                AND r.end_at>CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')
        OR EXISTS (SELECT 1 FROM guaranteed_allocations a JOIN parking_slots s ON s.id=a.slot_id
                   WHERE s.zone_id=OLD.id AND a.status='active'
                   AND a.end_at>CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')) THEN
        RAISE EXCEPTION 'zone has parking commitments' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_zone_commitment_guard BEFORE UPDATE OF is_active ON zones
FOR EACH ROW EXECUTE FUNCTION parking_zone_commitment_guard();
"""


def upgrade():
    op.execute(ZONE_COMMITMENT_POSTGRES_GUARD_SQL)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_zone_commitment_guard ON zones")
    op.execute("DROP FUNCTION IF EXISTS parking_zone_commitment_guard()")
