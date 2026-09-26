"""Add article images

  article_images                one row per upload, stored already processed
  articles.cover_image_id       the cover image, SET NULL if the image goes
  articles.cover_image_alt      description for screen readers
  articles.cover_image_credit   who took it, or where it came from

The new table is created with row level security enabled and, through the
default privileges set in a1c4e7b90d22, no grants to anon or authenticated, so
Supabase's Data API cannot read uploaded images around Flask. Existing columns
are untouched and there is no backfill.

Revision ID: f1a4d8c3b627
Revises: e5b8c2d7a914
Create Date: 2026-09-26 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f1a4d8c3b627"
down_revision = "e5b8c2d7a914"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "article_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("large", sa.LargeBinary(), nullable=False),
        sa.Column("thumb", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("article_images", schema=None) as batch_op:
        batch_op.create_index("ix_article_images_key", ["key"], unique=True)
        batch_op.create_index("ix_article_images_owner_id", ["owner_id"], unique=False)

    with op.batch_alter_table("articles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cover_image_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cover_image_alt", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("cover_image_credit", sa.String(length=300), nullable=True))
        batch_op.create_foreign_key(
            "fk_articles_cover_image_id", "article_images",
            ["cover_image_id"], ["id"], ondelete="SET NULL",
        )

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.article_images ENABLE ROW LEVEL SECURITY")


def downgrade():
    with op.batch_alter_table("articles", schema=None) as batch_op:
        batch_op.drop_constraint("fk_articles_cover_image_id", type_="foreignkey")
        batch_op.drop_column("cover_image_credit")
        batch_op.drop_column("cover_image_alt")
        batch_op.drop_column("cover_image_id")

    with op.batch_alter_table("article_images", schema=None) as batch_op:
        batch_op.drop_index("ix_article_images_owner_id")
        batch_op.drop_index("ix_article_images_key")
    op.drop_table("article_images")
