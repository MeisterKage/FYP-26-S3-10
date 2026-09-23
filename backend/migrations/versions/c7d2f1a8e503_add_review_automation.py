"""Add review automation columns

Three nullable timestamps, no backfill, nothing existing altered.

  articles.auto_published_at        the system published it without review
  articles.review_confirmed_at      an editor confirmed it afterwards
  users.autopublish_suspended_until auto-publish revoked after a correction

Auto-publish is recorded with timestamps rather than a new article status on
purpose: every query that filters on PUBLISHED keeps working unchanged.

Adding columns grants nothing and changes no privileges, so the lockdown in
a1c4e7b90d22 (revoked grants, row level security) is unaffected.

Revision ID: c7d2f1a8e503
Revises: 85460bbd6708
Create Date: 2026-09-23 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c7d2f1a8e503"
down_revision = "85460bbd6708"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("articles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("auto_published_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("review_confirmed_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("autopublish_suspended_until", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("autopublish_suspended_until")

    with op.batch_alter_table("articles", schema=None) as batch_op:
        batch_op.drop_column("review_confirmed_at")
        batch_op.drop_column("auto_published_at")
