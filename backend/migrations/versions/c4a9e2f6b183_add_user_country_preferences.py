"""Add user country preferences

  user_country_preferences   a country whose news a reader follows, beside
                             the sections in user_category_preferences

New table only; nothing existing altered. Row level security on, like every
table in the public schema (see a1c4e7b90d22).

Revision ID: c4a9e2f6b183
Revises: b7e3c1d9a420
Create Date: 2026-10-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c4a9e2f6b183"
down_revision = "b7e3c1d9a420"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_country_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "country_code"),
    )
    with op.batch_alter_table("user_country_preferences", schema=None) as batch_op:
        batch_op.create_index("ix_user_country_preferences_user_id", ["user_id"], unique=False)

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.user_country_preferences ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_table("user_country_preferences")
