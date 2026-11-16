"""Add encrypted patient contact data and emergency contacts.

Revision ID: d8a1f4c72b90
Revises: b7d4a9c2e615
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8a1f4c72b90"
down_revision: Union[str, None] = "b7d4a9c2e615"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "patients",
        sa.Column("contact_data_encrypted", sa.LargeBinary(), nullable=True),
        schema="public",
    )
    op.create_table(
        "patient_emergency_contacts",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("encrypted_data", sa.LargeBinary(), nullable=False),
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
            name="fk_patient_emergency_contacts_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "patient_id"],
            ["patients.tenant_id", "patients.id"],
            name="fk_patient_emergency_contacts_tenant_patient_patients",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_patient_emergency_contacts",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_patient_emergency_contacts_tenant_id_id",
        ),
    )
    op.create_index(
        "ix_patient_emergency_contacts_tenant_patient",
        "patient_emergency_contacts",
        ["tenant_id", "patient_id"],
    )
    op.execute(
        """
        UPDATE public.patient_identifiers AS older
        SET is_primary = false
        WHERE older.is_primary
          AND EXISTS (
              SELECT 1
              FROM public.patient_identifiers AS newer
              WHERE newer.tenant_id = older.tenant_id
                AND newer.patient_id = older.patient_id
                AND newer.is_primary
                AND (newer.created_at, newer.id) > (older.created_at, older.id)
          )
        """
    )
    op.create_index(
        "uq_patient_identifiers_one_primary",
        "patient_identifiers",
        ["tenant_id", "patient_id"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("is_primary"),
    )

    op.execute(
        "ALTER TABLE public.patient_emergency_contacts "
        "ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE public.patient_emergency_contacts "
        "FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        "CREATE POLICY tenant_isolation "
        "ON public.patient_emergency_contacts FOR ALL TO medigest_app "
        "USING (tenant_id = app_private.current_tenant_id()) "
        "WITH CHECK (tenant_id = app_private.current_tenant_id())"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON TABLE public.patient_emergency_contacts TO medigest_app"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE ALL ON TABLE public.patient_emergency_contacts FROM medigest_app"
    )
    op.execute(
        "DROP POLICY tenant_isolation ON public.patient_emergency_contacts"
    )
    op.execute(
        "ALTER TABLE public.patient_emergency_contacts "
        "NO FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE public.patient_emergency_contacts "
        "DISABLE ROW LEVEL SECURITY"
    )
    op.drop_index(
        "uq_patient_identifiers_one_primary",
        table_name="patient_identifiers",
        schema="public",
    )
    op.drop_index(
        "ix_patient_emergency_contacts_tenant_patient",
        table_name="patient_emergency_contacts",
    )
    op.drop_table("patient_emergency_contacts")
    op.drop_column("patients", "contact_data_encrypted", schema="public")
