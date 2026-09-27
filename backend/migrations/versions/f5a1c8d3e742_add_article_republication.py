"""Add article republication

  articles.republication   JSON describing the original publication, for
                           articles republished under a licence that allows it

Nullable, no backfill, nothing existing altered. Adding a column grants
nothing, so the lockdown in a1c4e7b90d22 is unaffected.

Revision ID: f5a1c8d3e742
Revises: e3f7b2c9d815
Create Date: 2026-09-27 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f5a1c8d3e742"
down_revision = "e3f7b2c9d815"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("articles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("republication", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("articles", schema=None) as batch_op:
        batch_op.drop_column("republication")
