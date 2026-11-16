"""Restrict administrative document categories and media types.

Revision ID: a1b6c3e8d902
Revises: f2c8a4d19e73
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1b6c3e8d902"
down_revision: Union[str, None] = "f2c8a4d19e73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_patient_administrative_documents_authorized_type",
        "patient_administrative_documents",
        "document_type IN "
        "('identity', 'proof_of_address', 'administrative_form', 'other')",
        schema="public",
    )
    op.create_check_constraint(
        "ck_patient_administrative_documents_authorized_content_type",
        "patient_administrative_documents",
        "content_type IN ('application/pdf', 'image/jpeg', 'image/png')",
        schema="public",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_patient_administrative_documents_authorized_content_type",
        "patient_administrative_documents",
        type_="check",
        schema="public",
    )
    op.drop_constraint(
        "ck_patient_administrative_documents_authorized_type",
        "patient_administrative_documents",
        type_="check",
        schema="public",
    )
