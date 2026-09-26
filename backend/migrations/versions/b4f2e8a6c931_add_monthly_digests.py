"""Add monthly digests

  digest_editions        one per (month, topic[, country])
  digest_entries         an edition's ranked articles, fixed at compile time
  digest_subscriptions   who gets notified when an edition is published

All three tables get row level security, and through the default privileges
set in a1c4e7b90d22 no grants to anon or authenticated. Nothing existing is
altered.

Revision ID: b4f2e8a6c931
Revises: a7e3c9d1f205
Create Date: 2026-09-26 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b4f2e8a6c931"
down_revision = "a7e3c9d1f205"
branch_labels = None
depends_on = None

TABLES = ("digest_editions", "digest_entries", "digest_subscriptions")


def upgrade():
    op.create_table(
        "digest_editions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False, server_default=""),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("compiled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("month", "key"),
    )
    with op.batch_alter_table("digest_editions", schema=None) as batch_op:
        batch_op.create_index("ix_digest_editions_month", ["month"], unique=False)

    op.create_table(
        "digest_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edition_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score_at_compile", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["edition_id"], ["digest_editions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("edition_id", "article_id"),
    )
    with op.batch_alter_table("digest_entries", schema=None) as batch_op:
        batch_op.create_index("ix_digest_entries_edition_id", ["edition_id"], unique=False)

    op.create_table(
        "digest_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "category_id", "country_code"),
    )
    with op.batch_alter_table("digest_subscriptions", schema=None) as batch_op:
        batch_op.create_index("ix_digest_subscriptions_user_id", ["user_id"], unique=False)

    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")


def downgrade():
    for table in reversed(TABLES):
        op.drop_table(table)
