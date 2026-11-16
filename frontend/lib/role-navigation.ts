export type RoleNavigationItem = {
  permission: string;
  label: string;
  description: string;
  sectionId: string;
};

const permissionDefinitions: Record<string, Omit<RoleNavigationItem, "permission">> = {
  "platform:manage": {
    label: "Plataforma",
    description: "Administración global de la plataforma",
    sectionId: "platform-manage",
  },
  "tenant:manage": {
    label: "Dashboard",
    description: "Indicadores administrativos del establecimiento",
    sectionId: "admin-dashboard",
  },
  "users:manage": {
    label: "Usuarios",
    description: "Administración de usuarios y acceso",
    sectionId: "users-manage",
  },
  "patients:manage": {
    label: "Pacientes",
    description: "Gestión administrativa de pacientes",
    sectionId: "patients-manage",
  },
  "appointments:read": {
    label: "Agenda",
    description: "Consulta de agenda",
    sectionId: "appointments",
  },
  "appointments:manage": {
    label: "Ventanilla",
    description: "Recepción y seguimiento operativo de citas",
    sectionId: "reception",
  },
  "clinical:read": {
    label: "Dashboard médico",
    description: "Agenda y atenciones clínicas autorizadas",
    sectionId: "doctor-dashboard",
  },
  "clinical:write": {
    label: "Atenciones",
    description: "Gestión de atenciones clínicas",
    sectionId: "clinical-write",
  },
  "operations:manage": {
    label: "Servicio",
    description: "Cola, salas y preparación de consulta",
    sectionId: "service-queue",
  },
  "reports:read": {
    label: "Reportes",
    description: "Consulta de reportes",
    sectionId: "reports-read",
  },
};

export const roleLabels: Record<string, string> = {
  superadmin: "Superadministración",
  administrator: "Administración",
  doctor: "Médico",
  service: "Servicio",
  receptionist: "Ventanilla",
};

export function getRoleNavigation(
  permissions: readonly string[],
): RoleNavigationItem[] {
  const permissionSet = new Set(permissions);
  return [...permissionSet]
    .filter((permission) => permission in permissionDefinitions)
    .filter(
      (permission) =>
        permission !== "appointments:read" ||
        !permissionSet.has("appointments:manage"),
    )
    .sort((left, right) =>
      permissionDefinitions[left].label.localeCompare(
        permissionDefinitions[right].label,
        "es",
      ),
    )
    .map((permission) => ({
      permission,
      ...permissionDefinitions[permission],
    }));
}
