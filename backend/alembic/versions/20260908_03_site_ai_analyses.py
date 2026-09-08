"""Add scoped AI history; never reassign or rewrite legacy report records."""
from alembic import op
import sqlalchemy as sa

revision = "20260908_03"
down_revision = "20260908_02"
branch_labels = None
depends_on = None


def upgrade():
    if not op.get_context().as_sql:
        inspector = sa.inspect(op.get_bind())
        if inspector.has_table("site_ai_analyses"):
            # An application rollback retains this evidence table. Refuse an
            # unknown shape instead of silently adopting or deleting it.
            expected = {"id", "site_id", "generated_by_id", "request_id", "input_hash", "kind", "model", "context", "content", "created_at"}
            columns = inspector.get_columns("site_ai_analyses")
            if {c["name"] for c in columns} != expected or any(c["nullable"] for c in columns):
                raise RuntimeError("Retained site AI table does not match the known contract")
            checks = inspector.get_unique_constraints("site_ai_analyses")
            if not any(c["name"] == "uq_site_ai_request" and c["column_names"] == ["generated_by_id", "request_id"] for c in checks):
                raise RuntimeError("Retained site AI table lacks request uniqueness")
            if not any(i["name"] == "ix_site_ai_history" for i in inspector.get_indexes("site_ai_analyses")):
                raise RuntimeError("Retained site AI table lacks its history index")
            return
    op.create_table("site_ai_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("parking_sites.id"), nullable=False),
        sa.Column("generated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("generated_by_id", "request_id", name="uq_site_ai_request"))
    op.create_index("ix_site_ai_history", "site_ai_analyses", ["site_id", "created_at"])


def downgrade():
    # Alembic restores the old revision marker, but preserves generated evidence.
    # The previous application ignores this additive table. Re-upgrade validates it.
    pass
