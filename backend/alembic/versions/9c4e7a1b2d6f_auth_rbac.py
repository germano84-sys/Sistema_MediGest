"""Seed the MediGest role and permission catalog for OIDC-backed RBAC.

Revision ID: 9c4e7a1b2d6f
Revises: 7f3a2c91d4e6
"""
from typing import Sequence, Union
from uuid import UUID, NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "9c4e7a1b2d6f"
down_revision: Union[str, None] = "7f3a2c91d4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = (
    ("superadmin", "Superadministrador", "Administra la plataforma SaaS."),
    ("administrator", "Administrador", "Administra un establecimiento."),
    ("doctor", "Médico", "Accede a las funciones clínicas autorizadas."),
    ("service", "Servicio", "Gestiona operaciones de servicio."),
    ("receptionist", "Ventanilla", "Gestiona admisión y agenda."),
)

PERMISSIONS = (
    ("platform:manage", "Administra la plataforma SaaS."),
    ("tenant:manage", "Administra la configuración del establecimiento."),
    ("users:manage", "Administra usuarios y membresías."),
    ("patients:manage", "Gestiona pacientes administrativos."),
    ("appointments:manage", "Crea y actualiza citas."),
    ("appointments:read", "Consulta citas autorizadas."),
    ("clinical:read", "Consulta información clínica autorizada."),
    ("clinical:write", "Registra información clínica autorizada."),
    ("operations:manage", "Gestiona tareas operativas."),
)

ROLE_PERMISSIONS = {
    "superadmin": ("platform:manage", "tenant:manage", "users:manage"),
    "administrator": (
        "tenant:manage",
        "users:manage",
        "patients:manage",
        "appointments:manage",
        "appointments:read",
        "operations:manage",
    ),
    "doctor": ("appointments:read", "clinical:read", "clinical:write"),
    "service": ("appointments:read", "operations:manage"),
    "receptionist": (
        "patients:manage",
        "appointments:manage",
        "appointments:read",
    ),
}


def _insert_catalog(
    table_name: str,
    code: str,
    name: str,
    description: str,
) -> UUID:
    connection = op.get_bind()
    existing_id = connection.scalar(
        sa.text(f"SELECT id FROM public.{table_name} WHERE code = :code"),
        {"code": code},
    )
    if existing_id is not None:
        return existing_id

    row_id = uuid5(NAMESPACE_URL, f"medigest:{table_name}:{code}")
    if table_name == "roles":
        connection.execute(
            sa.text(
                "INSERT INTO public.roles (id, code, name, description) "
                "VALUES (:id, :code, :name, :description) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"id": row_id, "code": code, "name": name, "description": description},
        )
    else:
        connection.execute(
            sa.text(
                "INSERT INTO public.permissions (id, code, description) "
                "VALUES (:id, :code, :description) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"id": row_id, "code": code, "description": description},
        )
    return connection.scalar(
        sa.text(f"SELECT id FROM public.{table_name} WHERE code = :code"),
        {"code": code},
    )


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("platform_role_id", sa.Uuid(), nullable=True),
        schema="public",
    )
    op.create_foreign_key(
        "fk_users_platform_role_id_roles",
        "users",
        "roles",
        ["platform_role_id"],
        ["id"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
    )

    role_ids = {
        code: _insert_catalog("roles", code, name, description)
        for code, name, description in ROLES
    }
    permission_ids = {
        code: _insert_catalog("permissions", code, code, description)
        for code, description in PERMISSIONS
    }
    connection = op.get_bind()
    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        for permission_code in permission_codes:
            connection.execute(
                sa.text(
                    "INSERT INTO public.role_permissions (role_id, permission_id) "
                    "VALUES (:role_id, :permission_id) ON CONFLICT DO NOTHING"
                ),
                {
                    "role_id": role_ids[role_code],
                    "permission_id": permission_ids[permission_code],
                },
            )

    op.execute("REVOKE INSERT, UPDATE ON TABLE public.users FROM medigest_app")
    op.execute(
        "GRANT INSERT (id, identity_provider_subject, email, display_name, is_active) "
        "ON TABLE public.users TO medigest_app"
    )
    op.execute(
        "GRANT UPDATE (email, display_name, updated_at) "
        "ON TABLE public.users TO medigest_app"
    )


def downgrade() -> None:
    connection = op.get_bind()
    permission_codes = tuple(code for code, _ in PERMISSIONS)
    role_ids = {
        code: connection.scalar(
            sa.text("SELECT id FROM public.roles WHERE code = :code"),
            {"code": code},
        )
        for code, _, _ in ROLES
    }
    permission_ids = {
        code: connection.scalar(
            sa.text("SELECT id FROM public.permissions WHERE code = :code"),
            {"code": code},
        )
        for code, _ in PERMISSIONS
    }
    for role_code, permission_codes_for_role in ROLE_PERMISSIONS.items():
        for permission_code in permission_codes_for_role:
            connection.execute(
                sa.text(
                    "DELETE FROM public.role_permissions "
                    "WHERE role_id = :role_id AND permission_id = :permission_id"
                ),
                {
                    "role_id": role_ids[role_code],
                    "permission_id": permission_ids[permission_code],
                },
            )
    for role_code in role_ids:
        connection.execute(
            sa.text("DELETE FROM public.roles WHERE id = :role_id"),
            {"role_id": role_ids[role_code]},
        )
    connection.execute(
        sa.text(
            "DELETE FROM public.permissions p "
            "WHERE p.code = ANY(:codes) "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM public.role_permissions rp "
            "  WHERE rp.permission_id = p.id"
            ")"
        ),
        {"codes": list(permission_codes)},
    )

    op.drop_constraint(
        "fk_users_platform_role_id_roles",
        "users",
        schema="public",
        type_="foreignkey",
    )
    op.drop_column("users", "platform_role_id", schema="public")
    op.execute("REVOKE INSERT, UPDATE ON TABLE public.users FROM medigest_app")
    op.execute(
        "GRANT INSERT, UPDATE ON TABLE public.users TO medigest_app"
    )
