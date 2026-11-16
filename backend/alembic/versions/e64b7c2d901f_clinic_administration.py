"""Add tenant-scoped clinic administration resources.

Revision ID: e64b7c2d901f
Revises: 9c4e7a1b2d6f
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e64b7c2d901f"
down_revision: Union[str, None] = "9c4e7a1b2d6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = (
    "clinic_rooms",
    "site_hours",
    "tenant_settings",
    "tenant_specialties",
)


def upgrade() -> None:
    op.create_table(
        "clinic_rooms",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "room_type",
            sa.String(length=40),
            server_default="consultation",
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_clinic_rooms_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "site_id"],
            ["sites.tenant_id", "sites.id"],
            name="fk_clinic_rooms_tenant_id_site_id_sites",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clinic_rooms"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_clinic_rooms_tenant_id_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "site_id",
            "code",
            name="uq_clinic_rooms_tenant_id_site_id_code",
        ),
    )
    op.create_index(
        "ix_clinic_rooms_tenant_site_active",
        "clinic_rooms",
        ["tenant_id", "site_id", "is_active"],
    )

    op.create_table(
        "site_hours",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=True),
        sa.Column("closes_at", sa.Time(), nullable=True),
        sa.Column("is_closed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "weekday BETWEEN 0 AND 6", name="ck_site_hours_weekday_range"
        ),
        sa.CheckConstraint(
            "is_closed OR (opens_at IS NOT NULL AND closes_at IS NOT NULL "
            "AND closes_at > opens_at)",
            name="ck_site_hours_valid_opening_interval",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_site_hours_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "site_id"],
            ["sites.tenant_id", "sites.id"],
            name="fk_site_hours_tenant_id_site_id_sites",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_site_hours"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_site_hours_tenant_id_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "site_id",
            "weekday",
            name="uq_site_hours_tenant_id_site_id_weekday",
        ),
    )

    op.create_table(
        "tenant_settings",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(key) BETWEEN 1 AND 100", name="ck_tenant_settings_key_length"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_settings_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenant_settings"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_tenant_settings_tenant_id_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "key", name="uq_tenant_settings_tenant_id_key"
        ),
    )
    op.create_index(
        "ix_tenant_settings_tenant_key", "tenant_settings", ["tenant_id", "key"]
    )

    op.create_table(
        "tenant_specialties",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("specialty_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_specialties_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["specialty_id"],
            ["specialties.id"],
            name="fk_tenant_specialties_specialty_id_specialties",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenant_specialties"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_tenant_specialties_tenant_id_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "specialty_id",
            name="uq_tenant_specialties_tenant_id_specialty_id",
        ),
    )

    op.execute(
        """
        CREATE FUNCTION app_private.current_platform_access()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, app_private
        AS $function$
            SELECT COALESCE(
                pg_catalog.current_setting('app.platform_signature', true)
                    = pg_catalog.encode(
                        public.hmac(
                            pg_catalog.convert_to('medigest:platform', 'UTF8'),
                            key.secret,
                            'sha256'
                        ),
                        'hex'
                    ),
                false
            )
            FROM app_private.tenant_context_keys AS key
            WHERE key.id = 1
        $function$
        """
    )
    op.execute(
        """
        CREATE FUNCTION app_private.set_platform_context(requested_signature text)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, app_private
        AS $function$
        BEGIN
            IF requested_signature IS NULL
               OR requested_signature !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'Invalid platform context' USING ERRCODE = '42501';
            END IF;

            PERFORM pg_catalog.set_config(
                'app.platform_signature',
                requested_signature,
                true
            );
            IF NOT app_private.current_platform_access() THEN
                RAISE EXCEPTION 'Invalid platform context' USING ERRCODE = '42501';
            END IF;
        END
        $function$
        """
    )
    op.execute(
        "ALTER FUNCTION app_private.current_platform_access() "
        "OWNER TO medigest_policy_owner"
    )
    op.execute(
        "ALTER FUNCTION app_private.set_platform_context(text) "
        "OWNER TO medigest_policy_owner"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app_private.current_platform_access() FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app_private.set_platform_context(text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION app_private.current_platform_access() "
        "TO medigest_app"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION app_private.set_platform_context(text) "
        "TO medigest_app"
    )

    op.execute("DROP POLICY tenant_isolation ON public.tenants")
    op.execute(
        "CREATE POLICY tenant_isolation ON public.tenants FOR ALL TO medigest_app "
        "USING (id = app_private.current_tenant_id() "
        "OR app_private.current_platform_access()) "
        "WITH CHECK (id = app_private.current_tenant_id() "
        "OR app_private.current_platform_access())"
    )
    op.execute("DROP POLICY tenant_isolation ON public.audit_events")
    op.execute(
        "CREATE POLICY tenant_isolation ON public.audit_events FOR ALL TO medigest_app "
        "USING (tenant_id = app_private.current_tenant_id() "
        "OR app_private.current_platform_access()) "
        "WITH CHECK (tenant_id = app_private.current_tenant_id() "
        "OR app_private.current_platform_access())"
    )

    for table_name in TENANT_TABLES:
        op.execute(
            f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY"
        )
        op.execute(
            f"ALTER TABLE public.{table_name} FORCE ROW LEVEL SECURITY"
        )
        op.execute(
            f"CREATE POLICY tenant_isolation ON public.{table_name} "
            "FOR ALL TO medigest_app "
            "USING (tenant_id = app_private.current_tenant_id()) "
            "WITH CHECK (tenant_id = app_private.current_tenant_id())"
        )

    op.execute("ALTER TABLE public.specialties ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.specialties FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY specialties_catalog_read ON public.specialties "
        "FOR SELECT TO medigest_app USING (true)"
    )
    op.execute(
        "CREATE POLICY specialties_platform_manage ON public.specialties "
        "FOR ALL TO medigest_app "
        "USING (app_private.current_platform_access()) "
        "WITH CHECK (app_private.current_platform_access())"
    )

    for table_name in TENANT_TABLES:
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
            f"public.{table_name} TO medigest_app"
        )
    op.execute(
        "GRANT INSERT, UPDATE, DELETE ON TABLE public.specialties TO medigest_app"
    )


def downgrade() -> None:
    for table_name in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY tenant_isolation ON public.{table_name}")
        op.execute(
            f"ALTER TABLE public.{table_name} NO FORCE ROW LEVEL SECURITY"
        )
        op.execute(
            f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY"
        )
    op.drop_index("ix_tenant_settings_tenant_key", table_name="tenant_settings")
    op.drop_index("ix_clinic_rooms_tenant_site_active", table_name="clinic_rooms")
    for table_name in reversed(TENANT_TABLES):
        op.drop_table(table_name)

    op.execute("DROP POLICY specialties_platform_manage ON public.specialties")
    op.execute("DROP POLICY specialties_catalog_read ON public.specialties")
    op.execute("ALTER TABLE public.specialties NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.specialties DISABLE ROW LEVEL SECURITY")
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE ON TABLE public.specialties FROM medigest_app"
    )

    op.execute("DROP POLICY tenant_isolation ON public.tenants")
    op.execute(
        "CREATE POLICY tenant_isolation ON public.tenants FOR ALL TO medigest_app "
        "USING (id = app_private.current_tenant_id()) "
        "WITH CHECK (id = app_private.current_tenant_id())"
    )
    op.execute("DROP POLICY tenant_isolation ON public.audit_events")
    op.execute(
        "CREATE POLICY tenant_isolation ON public.audit_events FOR ALL TO medigest_app "
        "USING (tenant_id = app_private.current_tenant_id()) "
        "WITH CHECK (tenant_id = app_private.current_tenant_id())"
    )
    op.execute(
        "DROP FUNCTION app_private.set_platform_context(text)"
    )
    op.execute(
        "DROP FUNCTION app_private.current_platform_access()"
    )
