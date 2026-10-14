"""Add article daily views

  article_daily_views   views per article per day, behind the running total
                        on articles.view_count, for the article trend panel

New table only; nothing existing altered. Row level security on, like every
table in the public schema (see a1c4e7b90d22).

Revision ID: a2d6f8b1c934
Revises: f5a1c8d3e742
Create Date: 2026-10-14 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a2d6f8b1c934"
down_revision = "f5a1c8d3e742"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "article_daily_views",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", "day"),
    )
    with op.batch_alter_table("article_daily_views", schema=None) as batch_op:
        batch_op.create_index("ix_article_daily_views_article_id", ["article_id"], unique=False)

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.article_daily_views ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_table("article_daily_views")
