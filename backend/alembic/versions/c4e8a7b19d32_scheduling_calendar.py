"""Add scheduling details and site holiday calendar.

Revision ID: c4e8a7b19d32
Revises: a1b6c3e8d902
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8a7b19d32"
down_revision: Union[str, None] = "a1b6c3e8d902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        schema="public",
    )
    op.add_column(
        "appointments",
        sa.Column("operational_notes", sa.Text(), nullable=True),
        schema="public",
    )
    op.create_table(
        "site_holidays",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
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
            name="fk_site_holidays_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "site_id"],
            ["sites.tenant_id", "sites.id"],
            name="fk_site_holidays_tenant_site_sites",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_site_holidays"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_site_holidays_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "site_id",
            "holiday_date",
            name="uq_site_holidays_tenant_site_date",
        ),
        schema="public",
    )
    op.execute("ALTER TABLE public.site_holidays ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.site_holidays FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON public.site_holidays "
        "FOR ALL TO medigest_app "
        "USING (tenant_id = app_private.current_tenant_id()) "
        "WITH CHECK (tenant_id = app_private.current_tenant_id())"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON TABLE public.site_holidays TO medigest_app"
    )


def downgrade() -> None:
    op.execute("REVOKE ALL ON TABLE public.site_holidays FROM medigest_app")
    op.execute("DROP POLICY tenant_isolation ON public.site_holidays")
    op.execute("ALTER TABLE public.site_holidays NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.site_holidays DISABLE ROW LEVEL SECURITY")
    op.drop_table("site_holidays", schema="public")
    op.drop_column("appointments", "operational_notes", schema="public")
    op.drop_column("appointments", "reason", schema="public")
