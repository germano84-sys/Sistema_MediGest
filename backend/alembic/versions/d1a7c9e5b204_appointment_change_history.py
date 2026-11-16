"""Add appointment optimistic locking and immutable change history.

Revision ID: d1a7c9e5b204
Revises: c4e8a7b19d32
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "d1a7c9e5b204"
down_revision: Union[str, None] = "c4e8a7b19d32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        schema="public",
    )
    op.create_table(
        "appointment_history",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("changes", JSONB(), nullable=False),
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
            "action IN ('created', 'confirmed', 'cancelled', 'rescheduled')",
            name="ck_appointment_history_valid_action",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_appointment_history_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "appointment_id"],
            ["appointments.tenant_id", "appointments.id"],
            name="fk_appointment_history_tenant_appointment_appointments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_appointment_history_actor_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_appointment_history"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_appointment_history_tenant_id_id",
        ),
        schema="public",
    )
    op.create_index(
        "ix_appointment_history_tenant_appointment_created",
        "appointment_history",
        ["tenant_id", "appointment_id", "created_at"],
        schema="public",
    )
    op.execute("ALTER TABLE public.appointment_history ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.appointment_history FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON public.appointment_history "
        "FOR ALL TO medigest_app "
        "USING (tenant_id = app_private.current_tenant_id()) "
        "WITH CHECK (tenant_id = app_private.current_tenant_id())"
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE public.appointment_history TO medigest_app"
    )


def downgrade() -> None:
    op.execute("REVOKE ALL ON TABLE public.appointment_history FROM medigest_app")
    op.execute("DROP POLICY tenant_isolation ON public.appointment_history")
    op.execute("ALTER TABLE public.appointment_history NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.appointment_history DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_appointment_history_tenant_appointment_created",
        table_name="appointment_history",
        schema="public",
    )
    op.drop_table("appointment_history", schema="public")
    op.drop_column("appointments", "version", schema="public")
