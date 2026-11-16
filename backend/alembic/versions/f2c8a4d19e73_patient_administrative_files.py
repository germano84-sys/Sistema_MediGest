"""Add site-scoped administrative patient files and encrypted documents.

Revision ID: f2c8a4d19e73
Revises: d8a1f4c72b90
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2c8a4d19e73"
down_revision: Union[str, None] = "d8a1f4c72b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enable_tenant_rls(table_name: str) -> None:
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
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table_name} "
        "TO medigest_app"
    )


def _disable_tenant_rls(table_name: str) -> None:
    op.execute(f"REVOKE ALL ON TABLE public.{table_name} FROM medigest_app")
    op.execute(f"DROP POLICY tenant_isolation ON public.{table_name}")
    op.execute(f"ALTER TABLE public.{table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.create_table(
        "patient_administrative_files",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("record_code", sa.String(length=80), nullable=False),
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
            name="fk_patient_administrative_files_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "site_id"],
            ["sites.tenant_id", "sites.id"],
            name="fk_patient_administrative_files_tenant_site_sites",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "patient_id"],
            ["patients.tenant_id", "patients.id"],
            name="fk_patient_administrative_files_tenant_patient_patients",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_patient_administrative_files",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_patient_administrative_files_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "site_id",
            "patient_id",
            name="uq_patient_administrative_files_tenant_id_site_id_patient_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "site_id",
            "record_code",
            name="uq_patient_administrative_files_tenant_id_site_id_record_code",
        ),
        schema="public",
    )
    op.create_index(
        "ix_patient_administrative_files_tenant_site_patient",
        "patient_administrative_files",
        ["tenant_id", "site_id", "patient_id"],
        schema="public",
    )
    op.create_table(
        "patient_administrative_documents",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("administrative_file_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256_digest", sa.String(length=64), nullable=False),
        sa.Column("encrypted_content", sa.LargeBinary(), nullable=False),
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
            "size_bytes BETWEEN 1 AND 10485760",
            name="ck_patient_administrative_documents_valid_size",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_patient_administrative_documents_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "administrative_file_id"],
            [
                "patient_administrative_files.tenant_id",
                "patient_administrative_files.id",
            ],
            name="fk_patient_admin_docs_tenant_file_admin_files",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_patient_administrative_documents",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_patient_administrative_documents_tenant_id_id",
        ),
        schema="public",
    )
    op.create_index(
        "ix_patient_administrative_documents_tenant_file",
        "patient_administrative_documents",
        ["tenant_id", "administrative_file_id"],
        schema="public",
    )
    _enable_tenant_rls("patient_administrative_files")
    _enable_tenant_rls("patient_administrative_documents")


def downgrade() -> None:
    _disable_tenant_rls("patient_administrative_documents")
    _disable_tenant_rls("patient_administrative_files")
    op.drop_index(
        "ix_patient_administrative_documents_tenant_file",
        table_name="patient_administrative_documents",
        schema="public",
    )
    op.drop_table("patient_administrative_documents", schema="public")
    op.drop_index(
        "ix_patient_administrative_files_tenant_site_patient",
        table_name="patient_administrative_files",
        schema="public",
    )
    op.drop_table("patient_administrative_files", schema="public")
