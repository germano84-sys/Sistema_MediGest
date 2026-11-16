"""Allow row-scoped removal of unreferenced sites.

Revision ID: c6a9e3f417b2
Revises: e64b7c2d901f
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c6a9e3f417b2"
down_revision: Union[str, None] = "e64b7c2d901f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("GRANT DELETE ON TABLE public.sites TO medigest_app")


def downgrade() -> None:
    op.execute("REVOKE DELETE ON TABLE public.sites FROM medigest_app")
