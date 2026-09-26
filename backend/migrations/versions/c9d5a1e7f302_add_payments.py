"""Add payments

  payments                 one row per order, checkout to outcome
  payment_webhook_events   provider events already acted on (idempotency)

Both tables get row level security, and through the default privileges set in
a1c4e7b90d22 no grants to anon or authenticated. Existing tables, including
subscriptions and its gateway_ref column, are untouched.

Revision ID: c9d5a1e7f302
Revises: b4f2e8a6c931
Create Date: 2026-09-26 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c9d5a1e7f302"
down_revision = "b4f2e8a6c931"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("contributor_id", sa.Integer(), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_ref", sa.String(length=255), nullable=True),
        sa.Column("failure_reason", sa.String(length=300), nullable=True),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contributor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_ref"),
    )
    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.create_index("ix_payments_user_id", ["user_id"], unique=False)
        batch_op.create_index("ix_payments_status", ["status"], unique=False)

    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "event_id"),
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.payment_webhook_events ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_table("payment_webhook_events")
    op.drop_table("payments")
