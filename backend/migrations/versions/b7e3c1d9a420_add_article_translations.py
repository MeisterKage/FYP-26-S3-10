"""Add article translations

  article_translations   an article in another language (zh, ms), with a
                         fingerprint of the English it was translated from

New table only; nothing existing altered. Row level security on, like every
table in the public schema (see a1c4e7b90d22).

Revision ID: b7e3c1d9a420
Revises: a2d6f8b1c934
Create Date: 2026-10-14 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b7e3c1d9a420"
down_revision = "a2d6f8b1c934"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "article_translations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("lang", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("points", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("source_hash", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", "lang"),
    )
    with op.batch_alter_table("article_translations", schema=None) as batch_op:
        batch_op.create_index("ix_article_translations_article_id", ["article_id"], unique=False)

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.article_translations ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_table("article_translations")
