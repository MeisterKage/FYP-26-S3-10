"""Add source domain rules and domain ownership lookups

  source_domain_rules   an administrator's grade for a domain
  domain_lookups        who owns a domain, per Wikidata (a cache)

Both tables get row level security, and through the default privileges set in
a1c4e7b90d22 no grants to anon or authenticated. Nothing existing is altered.

Revision ID: e3f7b2c9d815
Revises: d8e2f6a4b193
Create Date: 2026-09-27 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e3f7b2c9d815"
down_revision = "d8e2f6a4b193"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_domain_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=400), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("source_domain_rules", schema=None) as batch_op:
        batch_op.create_index("ix_source_domain_rules_domain", ["domain"], unique=True)

    op.create_table(
        "domain_lookups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("owner", sa.String(length=300), nullable=True),
        sa.Column("wikidata_id", sa.String(length=20), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("domain_lookups", schema=None) as batch_op:
        batch_op.create_index("ix_domain_lookups_domain", ["domain"], unique=True)

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.source_domain_rules ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.domain_lookups ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_table("domain_lookups")
    op.drop_table("source_domain_rules")
