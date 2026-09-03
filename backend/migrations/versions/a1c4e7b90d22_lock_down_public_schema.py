"""Lock down the public schema against Supabase's Data API

Supabase exposes every table in `public` over PostgREST at
https://<ref>.supabase.co/rest/v1/, authorised by the `anon` key, which is
public by design and ships inside frontend code. Supabase's default privileges
grant anon and authenticated FULL rights (SELECT/INSERT/UPDATE/DELETE/TRUNCATE)
on every new table, so the moment `flask db upgrade` created our schema, anyone
who knew the project ref could read `users.password_hash`, forge an
administrator by UPDATEing `users.role`, rewrite credibility scores, or TRUNCATE
the lot, without ever touching Flask.

That directly contradicts PDD Section 2.1: "No client ever queries the database
directly." This migration makes the database enforce what the architecture
already claimed.

Three layers, because any one of them can be undone by accident:

  1. REVOKE the existing grants from anon and authenticated.
  2. ALTER DEFAULT PRIVILEGES so tables created by *future* migrations are not
     auto-granted again. Without this, the next migration silently reopens it.
  3. ENABLE ROW LEVEL SECURITY on every table, with no policies. No policy means
     no rows for anyone the policy system applies to, a default-deny backstop
     if the grants ever return.

The Flask connection is unaffected: it connects as `postgres`, which owns these
tables and carries rolbypassrls, so RLS never applies to it. Verified before
this migration was written.

Postgres-only. The test suite runs on SQLite, which has none of these concepts,
so the whole migration is skipped there.

Revision ID: a1c4e7b90d22
Revises: 577ef65ec432
"""
from alembic import op

revision = "a1c4e7b90d22"
down_revision = "577ef65ec432"
branch_labels = None
depends_on = None

#: Roles PostgREST authenticates as. `service_role` is deliberately not listed:
#: it is the secret server-side key and legitimately bypasses RLS.
EXPOSED_ROLES = ("anon", "authenticated")


def _public_tables(conn) -> list[str]:
    return [
        row[0]
        for row in conn.exec_driver_sql(
            "select tablename from pg_tables where schemaname = 'public' order by tablename"
        )
    ]


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    for role in EXPOSED_ROLES:
        # Existing tables.
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}")
        op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role}")
        op.execute(f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM {role}")
        # Nothing should be able to discover the schema either.
        op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role}")

        # Future tables. Supabase installs default privileges as `postgres`;
        # matching that grantor is what makes the revoke actually apply.
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"REVOKE ALL ON TABLES FROM {role}"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"REVOKE ALL ON SEQUENCES FROM {role}"
        )

    # Default-deny backstop. No policies are created on purpose: a table with RLS
    # enabled and zero policies returns no rows to any role the policy system
    # applies to, which is exactly what we want for tables only Flask should read.
    for table in _public_tables(conn):
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')


def downgrade():
    """Reopen the schema.

    Restores Supabase's stock posture. Only useful if you later decide to serve
    this database through PostgREST directly, in which case you must write RLS
    policies before running this, or you reintroduce the hole it closed.
    """
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    for table in _public_tables(conn):
        op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY')

    for role in EXPOSED_ROLES:
        op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        op.execute(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {role}")
        op.execute(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {role}")
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"GRANT ALL ON TABLES TO {role}"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"GRANT ALL ON SEQUENCES TO {role}"
        )
