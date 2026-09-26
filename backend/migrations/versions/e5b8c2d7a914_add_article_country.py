"""Add article country

One nullable column plus an index, no backfill, nothing existing altered.

  articles.country_code   ISO 3166-1 alpha-2, the country the article is about

NULL means international. Existing articles stay NULL until tagged. The list of
valid codes lives in app/countries.py, not in a table: it is a fixed standard,
not something an administrator edits.

Adding a column grants nothing and changes no privileges, so the lockdown in
a1c4e7b90d22 (revoked grants, row level security) is unaffected.

Revision ID: e5b8c2d7a914
Revises: d3a9b6e1f4c2
Create Date: 2026-09-26 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e5b8c2d7a914"
down_revision = "d3a9b6e1f4c2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("articles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("country_code", sa.String(length=2), nullable=True))
        batch_op.create_index("ix_articles_country_code", ["country_code"], unique=False)


def downgrade():
    with op.batch_alter_table("articles", schema=None) as batch_op:
        batch_op.drop_index("ix_articles_country_code")
        batch_op.drop_column("country_code")
