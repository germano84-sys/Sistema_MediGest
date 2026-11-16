"""Add room assignment and service workflow timings to appointments.

Revision ID: 4a7c2d8e913f
Revises: 3eb5d7a1c902
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4a7c2d8e913f"
down_revision: Union[str, None] = "3eb5d7a1c902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_clinic_rooms_tenant_site_id",
        "clinic_rooms",
        ["tenant_id", "site_id", "id"],
        schema="public",
    )
    op.add_column(
        "appointments",
        sa.Column(
            "service_status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        schema="public",
    )
    op.add_column(
        "appointments",
        sa.Column("service_room_id", sa.Uuid(), nullable=True),
        schema="public",
    )
    for column_name in (
        "preparation_started_at",
        "ready_at",
        "attention_started_at",
        "attention_completed_at",
    ):
        op.add_column(
            "appointments",
            sa.Column(column_name, sa.DateTime(timezone=True), nullable=True),
            schema="public",
        )
    op.create_index(
        "ix_appointments_tenant_site_queue_entered",
        "appointments",
        ["tenant_id", "site_id", "queue_entered_at"],
        schema="public",
    )
    op.create_foreign_key(
        "fk_appointments_tenant_site_room_clinic_rooms",
        "appointments",
        "clinic_rooms",
        ["tenant_id", "site_id", "service_room_id"],
        ["tenant_id", "site_id", "id"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_appointments_service_status",
        "appointments",
        "service_status IN ('pending', 'preparing', 'ready', 'completed')",
        schema="public",
    )
    op.create_check_constraint(
        "ck_appointments_preparation_time_required",
        "appointments",
        "service_status NOT IN ('preparing', 'ready', 'completed') "
        "OR preparation_started_at IS NOT NULL",
        schema="public",
    )
    op.create_check_constraint(
        "ck_appointments_ready_time_required",
        "appointments",
        "service_status NOT IN ('ready', 'completed') OR ready_at IS NOT NULL",
        schema="public",
    )
    op.create_check_constraint(
        "ck_appointments_completion_time_required",
        "appointments",
        "service_status != 'completed' OR attention_completed_at IS NOT NULL",
        schema="public",
    )
    op.create_check_constraint(
        "ck_appointments_preparation_requires_queue",
        "appointments",
        "preparation_started_at IS NULL OR queue_entered_at IS NOT NULL",
        schema="public",
    )
    op.create_check_constraint(
        "ck_appointments_ready_requires_preparation",
        "appointments",
        "ready_at IS NULL OR preparation_started_at IS NOT NULL",
        schema="public",
    )
    op.create_check_constraint(
        "ck_appointments_attention_requires_ready",
        "appointments",
        "attention_started_at IS NULL OR ready_at IS NOT NULL",
        schema="public",
    )
    op.create_check_constraint(
        "ck_appointments_completion_requires_attention",
        "appointments",
        "attention_completed_at IS NULL OR attention_started_at IS NOT NULL",
        schema="public",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_appointments_completion_requires_attention",
        "appointments",
        schema="public",
        type_="check",
    )
    op.drop_constraint(
        "ck_appointments_attention_requires_ready",
        "appointments",
        schema="public",
        type_="check",
    )
    op.drop_constraint(
        "ck_appointments_ready_requires_preparation",
        "appointments",
        schema="public",
        type_="check",
    )
    op.drop_constraint(
        "ck_appointments_preparation_requires_queue",
        "appointments",
        schema="public",
        type_="check",
    )
    op.drop_constraint(
        "ck_appointments_completion_time_required",
        "appointments",
        schema="public",
        type_="check",
    )
    op.drop_constraint(
        "ck_appointments_ready_time_required",
        "appointments",
        schema="public",
        type_="check",
    )
    op.drop_constraint(
        "ck_appointments_preparation_time_required",
        "appointments",
        schema="public",
        type_="check",
    )
    op.drop_constraint(
        "ck_appointments_service_status",
        "appointments",
        schema="public",
        type_="check",
    )
    op.drop_constraint(
        "fk_appointments_tenant_site_room_clinic_rooms",
        "appointments",
        schema="public",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_appointments_tenant_site_queue_entered",
        table_name="appointments",
        schema="public",
    )
    op.drop_column("appointments", "attention_completed_at", schema="public")
    op.drop_column("appointments", "attention_started_at", schema="public")
    op.drop_column("appointments", "ready_at", schema="public")
    op.drop_column("appointments", "preparation_started_at", schema="public")
    op.drop_column("appointments", "service_room_id", schema="public")
    op.drop_column("appointments", "service_status", schema="public")
    op.drop_constraint(
        "uq_clinic_rooms_tenant_site_id",
        "clinic_rooms",
        schema="public",
        type_="unique",
    )
