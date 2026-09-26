"""Add source ratings

Adds to article_sources the rating each cited source receives
(app/source_rating.py) and an editor's verdict on it. All nullable except
`flagged`, which defaults to false. Existing sources stay unrated until
`flask rate-sources` runs; until then they score as before.

Adding columns grants nothing and changes no privileges, so the lockdown in
a1c4e7b90d22 is unaffected.

Revision ID: d8e2f6a4b193
Revises: c9d5a1e7f302
Create Date: 2026-09-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d8e2f6a4b193"
down_revision = "c9d5a1e7f302"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("article_sources", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tier", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("points", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("rating_reason", sa.String(length=400), nullable=True))
        batch_op.add_column(sa.Column("flagged", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.add_column(sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("editor_verdict", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("editor_reason", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("editor_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("verdict_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key("fk_article_sources_editor_id", "users", ["editor_id"], ["id"])


def downgrade():
    with op.batch_alter_table("article_sources", schema=None) as batch_op:
        batch_op.drop_constraint("fk_article_sources_editor_id", type_="foreignkey")
        for column in ("verdict_at", "editor_id", "editor_reason", "editor_verdict",
                       "rated_at", "flagged", "rating_reason", "points", "tier"):
            batch_op.drop_column(column)
