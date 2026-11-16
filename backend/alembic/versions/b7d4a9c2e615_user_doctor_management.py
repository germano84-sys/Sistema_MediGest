"""Add site-scoped roles and physician administration.

Revision ID: b7d4a9c2e615
Revises: c6a9e3f417b2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d4a9c2e615"
down_revision: Union[str, None] = "c6a9e3f417b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES = (
    "membership_site_roles",
    "doctor_specialties",
    "doctor_availability",
)


def upgrade() -> None:
    op.create_table(
        "membership_site_roles",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_membership_site_roles_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "site_id"],
            ["sites.tenant_id", "sites.id"],
            name="fk_membership_site_roles_tenant_site_sites",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["memberships.tenant_id", "memberships.id"],
            name="fk_membership_site_roles_tenant_membership_memberships",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_membership_site_roles_role_id_roles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "site_id",
            "membership_id",
            "role_id",
            name="pk_membership_site_roles",
        ),
    )
    op.create_index(
        "ix_membership_site_roles_tenant_site_membership",
        "membership_site_roles",
        ["tenant_id", "site_id", "membership_id"],
    )

    op.create_table(
        "doctor_specialties",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("specialty_id", sa.Uuid(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
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
            name="fk_doctor_specialties_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "doctor_id"],
            ["doctors.tenant_id", "doctors.id"],
            name="fk_doctor_specialties_tenant_doctor_doctors",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["specialty_id"],
            ["specialties.id"],
            name="fk_doctor_specialties_specialty_id_specialties",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_doctor_specialties"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_doctor_specialties_tenant_id_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "doctor_id",
            "specialty_id",
            name="uq_doctor_specialties_tenant_doctor_specialty",
        ),
    )
    op.create_index(
        "uq_doctor_specialties_one_primary",
        "doctor_specialties",
        ["tenant_id", "doctor_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )
    op.create_index(
        "ix_doctor_specialties_tenant_specialty",
        "doctor_specialties",
        ["tenant_id", "specialty_id"],
    )
    op.execute(
        """
        INSERT INTO public.doctor_specialties
            (id, tenant_id, doctor_id, specialty_id, is_primary)
        SELECT gen_random_uuid(), tenant_id, id, specialty_id, true
        FROM public.doctors
        ON CONFLICT (tenant_id, doctor_id, specialty_id) DO NOTHING
        """
    )

    op.create_table(
        "doctor_availability",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.Time(), nullable=False),
        sa.Column("ends_at", sa.Time(), nullable=False),
        sa.Column("is_available", sa.Boolean(), server_default="true", nullable=False),
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
            "weekday BETWEEN 0 AND 6", name="ck_doctor_availability_weekday_range"
        ),
        sa.CheckConstraint(
            "ends_at > starts_at", name="ck_doctor_availability_valid_interval"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_doctor_availability_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "doctor_id"],
            ["doctors.tenant_id", "doctors.id"],
            name="fk_doctor_availability_tenant_doctor_doctors",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "site_id"],
            ["sites.tenant_id", "sites.id"],
            name="fk_doctor_availability_tenant_site_sites",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_doctor_availability"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_doctor_availability_tenant_id_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "doctor_id",
            "site_id",
            "weekday",
            "starts_at",
            name="uq_doctor_availability_doctor_site_weekday_start",
        ),
    )
    op.create_index(
        "ix_doctor_availability_tenant_site_weekday",
        "doctor_availability",
        ["tenant_id", "site_id", "weekday"],
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

    op.execute(
        "GRANT SELECT, INSERT, DELETE ON TABLE "
        "public.membership_site_roles TO medigest_app"
    )
    op.execute(
        "GRANT SELECT, INSERT, DELETE ON TABLE "
        "public.doctor_specialties TO medigest_app"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
        "public.doctor_availability TO medigest_app"
    )


def downgrade() -> None:
    for table_name in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY tenant_isolation ON public.{table_name}")
        op.execute(f"ALTER TABLE public.{table_name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_doctor_availability_tenant_site_weekday",
        table_name="doctor_availability",
    )
    op.drop_table("doctor_availability")
    op.drop_index(
        "ix_doctor_specialties_tenant_specialty",
        table_name="doctor_specialties",
    )
    op.drop_index("uq_doctor_specialties_one_primary", table_name="doctor_specialties")
    op.drop_table("doctor_specialties")
    op.drop_index(
        "ix_membership_site_roles_tenant_site_membership",
        table_name="membership_site_roles",
    )
    op.drop_table("membership_site_roles")
