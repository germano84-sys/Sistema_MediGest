"""Enable signed tenant context and row-level security.

Revision ID: 7f3a2c91d4e6
Revises: 60b458284510
"""
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7f3a2c91d4e6"
down_revision: Union[str, None] = "60b458284510"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = (
    "tenants",
    "sites",
    "memberships",
    "membership_roles",
    "doctors",
    "services",
    "patients",
    "patient_identifiers",
    "appointments",
    "clinical_records",
    "encounters",
    "diagnoses",
    "prescriptions",
    "medical_orders",
    "audit_events",
)

READ_WRITE_TABLES = (
    "sites",
    "memberships",
    "doctors",
    "services",
    "patients",
    "patient_identifiers",
    "appointments",
    "clinical_records",
    "encounters",
    "diagnoses",
    "prescriptions",
    "medical_orders",
)


def upgrade() -> None:
    secret = os.environ.get("TENANT_CONTEXT_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError("TENANT_CONTEXT_SECRET must contain at least 32 bytes")

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public")
    op.execute(
        "CREATE SCHEMA app_private AUTHORIZATION medigest_policy_owner"
    )
    op.create_table(
        "tenant_context_keys",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("secret", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("id = 1", name="single_key"),
        schema="app_private",
    )
    op.execute(
        "ALTER TABLE app_private.tenant_context_keys "
        "OWNER TO medigest_policy_owner"
    )
    op.get_bind().execute(
        sa.text(
            "INSERT INTO app_private.tenant_context_keys (id, secret) "
            "VALUES (1, :secret)"
        ),
        {"secret": secret.encode("utf-8")},
    )
    op.execute(
        """
        CREATE FUNCTION app_private.current_tenant_id()
        RETURNS uuid
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, app_private
        AS $function$
        DECLARE
            context_tenant uuid;
            context_signature text;
            context_secret bytea;
        BEGIN
            BEGIN
                context_tenant :=
                    NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid;
            EXCEPTION WHEN invalid_text_representation THEN
                RETURN NULL;
            END;

            context_signature :=
                NULLIF(pg_catalog.current_setting('app.tenant_signature', true), '');
            IF context_tenant IS NULL
               OR context_signature IS NULL
               OR context_signature !~ '^[0-9a-f]{64}$' THEN
                RETURN NULL;
            END IF;

            SELECT secret INTO context_secret
            FROM app_private.tenant_context_keys
            WHERE id = 1;

            IF context_secret IS NULL
               OR pg_catalog.encode(
                    public.hmac(
                        pg_catalog.convert_to(context_tenant::text, 'UTF8'),
                        context_secret,
                        'sha256'
                    ),
                    'hex'
               ) <> context_signature THEN
                RETURN NULL;
            END IF;

            RETURN context_tenant;
        END
        $function$
        """
    )
    op.execute(
        """
        CREATE FUNCTION app_private.set_tenant_context(
            requested_tenant uuid,
            requested_signature text
        )
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, app_private
        AS $function$
        BEGIN
            IF requested_tenant IS NULL
               OR requested_signature IS NULL
               OR requested_signature !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'Invalid tenant context' USING ERRCODE = '42501';
            END IF;

            PERFORM pg_catalog.set_config(
                'app.tenant_id',
                requested_tenant::text,
                true
            );
            PERFORM pg_catalog.set_config(
                'app.tenant_signature',
                requested_signature,
                true
            );

            IF app_private.current_tenant_id() IS DISTINCT FROM requested_tenant THEN
                RAISE EXCEPTION 'Invalid tenant context' USING ERRCODE = '42501';
            END IF;
        END
        $function$
        """
    )
    op.execute(
        "ALTER FUNCTION app_private.current_tenant_id() "
        "OWNER TO medigest_policy_owner"
    )
    op.execute(
        "ALTER FUNCTION app_private.set_tenant_context(uuid, text) "
        "OWNER TO medigest_policy_owner"
    )

    op.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    op.execute("REVOKE CREATE ON SCHEMA public FROM medigest_app")
    op.execute("GRANT USAGE ON SCHEMA public TO medigest_app")
    op.execute("GRANT USAGE ON SCHEMA public TO medigest_policy_owner")
    op.execute("GRANT USAGE ON SCHEMA app_private TO medigest_app")
    op.execute("REVOKE ALL ON SCHEMA app_private FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON TABLE app_private.tenant_context_keys "
        "FROM PUBLIC, medigest_app"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app_private.current_tenant_id() FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app_private.set_tenant_context(uuid, text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION app_private.current_tenant_id() "
        "TO medigest_app"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "app_private.set_tenant_context(uuid, text) TO medigest_app"
    )
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC")

    for table_name in TENANT_TABLES:
        op.execute(
            f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY"
        )
        op.execute(
            f"ALTER TABLE public.{table_name} FORCE ROW LEVEL SECURITY"
        )
        tenant_expression = (
            "id = app_private.current_tenant_id()"
            if table_name == "tenants"
            else "tenant_id = app_private.current_tenant_id()"
        )
        op.execute(
            f"CREATE POLICY tenant_isolation ON public.{table_name} "
            f"FOR ALL TO medigest_app "
            f"USING ({tenant_expression}) "
            f"WITH CHECK ({tenant_expression})"
        )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE "
        + ", ".join(f"public.{name}" for name in READ_WRITE_TABLES)
        + " TO medigest_app"
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE public.audit_events TO medigest_app"
    )
    op.execute(
        "GRANT SELECT, INSERT, DELETE ON TABLE public.membership_roles "
        "TO medigest_app"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE public.tenants TO medigest_app"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE public.users TO medigest_app"
    )
    op.execute(
        "GRANT SELECT ON TABLE public.roles, public.permissions, "
        "public.role_permissions, public.specialties TO medigest_app"
    )

    op.execute(
        "ALTER ROLE medigest_app NOSUPERUSER NOCREATEDB NOCREATEROLE "
        "NOINHERIT NOBYPASSRLS"
    )
    op.execute("ALTER ROLE medigest_app SET row_security = on")
    op.execute(
        "ALTER ROLE medigest_policy_owner NOLOGIN NOSUPERUSER "
        "NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
    )


def downgrade() -> None:
    for table_name in reversed(TENANT_TABLES):
        op.execute(
            f"DROP POLICY tenant_isolation ON public.{table_name}"
        )
        op.execute(
            f"ALTER TABLE public.{table_name} NO FORCE ROW LEVEL SECURITY"
        )
        op.execute(
            f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY"
        )

    op.execute(
        "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM medigest_app"
    )
    op.execute("REVOKE USAGE ON SCHEMA app_private FROM medigest_app")
    op.execute(
        "DROP FUNCTION app_private.set_tenant_context(uuid, text)"
    )
    op.execute("DROP FUNCTION app_private.current_tenant_id()")
    op.drop_table("tenant_context_keys", schema="app_private")
    op.execute("DROP SCHEMA app_private")
    op.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
