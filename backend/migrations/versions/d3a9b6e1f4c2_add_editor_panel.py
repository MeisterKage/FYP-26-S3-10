"""Add editor panel columns

Two nullable text columns on users, no backfill, nothing existing altered.

  users.editor_title        e.g. "Senior Politics Editor"
  users.editor_credentials  a short statement of experience

Both are shown on the public editor panel and set only by an administrator.

Adding columns grants nothing and changes no privileges, so the lockdown in
a1c4e7b90d22 (revoked grants, row level security) is unaffected.

Revision ID: d3a9b6e1f4c2
Revises: c7d2f1a8e503
Create Date: 2026-09-23 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d3a9b6e1f4c2"
down_revision = "c7d2f1a8e503"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("editor_title", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("editor_credentials", sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("editor_credentials")
        batch_op.drop_column("editor_title")
