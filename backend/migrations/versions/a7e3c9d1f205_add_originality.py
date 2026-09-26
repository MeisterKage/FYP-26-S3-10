"""Add originality checking

  article_fingerprints            winnowed text fingerprints, looked up by hash
  source_snapshots                cited pages as they were when checked
  articles.originality_percent    latest result, read by review ordering
  articles.originality_report     full report with matched passages (JSON)
  articles.originality_checked_at when it was produced

Both new tables get row level security, and through the default privileges set
in a1c4e7b90d22 no grants to anon or authenticated. Existing columns are
untouched; fingerprints for existing articles are built by
`flask index-originality`.

Revision ID: a7e3c9d1f205
Revises: f1a4d8c3b627
Create Date: 2026-09-26 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a7e3c9d1f205"
down_revision = "f1a4d8c3b627"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "article_fingerprints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("hash", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("article_fingerprints", schema=None) as batch_op:
        batch_op.create_index("ix_article_fingerprints_hash", ["hash"], unique=False)
        batch_op.create_index("ix_article_fingerprints_article_id", ["article_id"], unique=False)

    op.create_table(
        "source_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("source_snapshots", schema=None) as batch_op:
        batch_op.create_index("ix_source_snapshots_url_hash", ["url_hash"], unique=True)

    with op.batch_alter_table("articles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("originality_percent", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("originality_report", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("originality_checked_at", sa.DateTime(timezone=True), nullable=True)
        )

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.article_fingerprints ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.source_snapshots ENABLE ROW LEVEL SECURITY")


def downgrade():
    with op.batch_alter_table("articles", schema=None) as batch_op:
        batch_op.drop_column("originality_checked_at")
        batch_op.drop_column("originality_report")
        batch_op.drop_column("originality_percent")

    with op.batch_alter_table("source_snapshots", schema=None) as batch_op:
        batch_op.drop_index("ix_source_snapshots_url_hash")
    op.drop_table("source_snapshots")

    with op.batch_alter_table("article_fingerprints", schema=None) as batch_op:
        batch_op.drop_index("ix_article_fingerprints_article_id")
        batch_op.drop_index("ix_article_fingerprints_hash")
    op.drop_table("article_fingerprints")
