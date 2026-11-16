"""Record patient reception and queue timestamps on appointments.

Revision ID: 3eb5d7a1c902
Revises: d1a7c9e5b204
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3eb5d7a1c902"
down_revision: Union[str, None] = "d1a7c9e5b204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("arrival_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )
    op.add_column(
        "appointments",
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )
    op.add_column(
        "appointments",
        sa.Column("queue_entered_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )
    op.create_check_constraint(
        "ck_appointments_checkin_requires_arrival",
        "appointments",
        "checked_in_at IS NULL OR arrival_confirmed_at IS NOT NULL",
        schema="public",
    )
    op.create_check_constraint(
        "ck_appointments_queue_requires_checkin",
        "appointments",
        "queue_entered_at IS NULL OR checked_in_at IS NOT NULL",
        schema="public",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_appointments_queue_requires_checkin",
        "appointments",
        schema="public",
        type_="check",
    )
    op.drop_constraint(
        "ck_appointments_checkin_requires_arrival",
        "appointments",
        schema="public",
        type_="check",
    )
    op.drop_column("appointments", "queue_entered_at", schema="public")
    op.drop_column("appointments", "checked_in_at", schema="public")
    op.drop_column("appointments", "arrival_confirmed_at", schema="public")
