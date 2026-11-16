"use client";

import {
  Activity,
  Bell,
  BookOpenCheck,
  BriefcaseMedical,
  Building2,
  ChevronDown,
  CircleHelp,
  ClipboardList,
  FileHeart,
  LayoutDashboard,
  Menu,
  Search,
  ShieldCheck,
  Stethoscope,
  Users,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AuthActions } from "./auth-actions";
import { AdminDashboard } from "./admin-dashboard";
import { AppointmentCalendar } from "./appointment-calendar";
import { AdministrationPanel } from "./administration-panel";
import { DoctorDashboard } from "./doctor-dashboard";
import { PatientManager } from "./patient-manager";
import { ReceptionDesk } from "./reception-desk";
import { ServiceQueuePanel } from "./service-queue-panel";
import { Badge } from "./ui/badge";
import { Breadcrumbs } from "./ui/breadcrumbs";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Dialog } from "./ui/dialog";
import { EmptyState } from "./ui/empty-state";
import { Input } from "./ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { useToast } from "./ui/toast";
import {
  getRoleNavigation,
  roleLabels,
  type RoleNavigationItem,
} from "../lib/role-navigation";

type IdentityProfile = {
  roles: string[];
  permissions: string[];
  tenant_id: string | null;
  site_id: string | null;
};

type WorkspaceUser = {
  name: string | null;
  email: string | null;
};

type AuthenticatedWorkspaceProps = {
  user: WorkspaceUser;
  keycloakIssuer: string;
  clientId: string;
};

const permissionIcons: Record<string, typeof Building2> = {
  "platform:manage": Building2,
  "tenant:manage": Building2,
  "users:manage": Users,
  "patients:manage": BriefcaseMedical,
  "appointments:read": ClipboardList,
  "appointments:manage": ClipboardList,
  "clinical:read": FileHeart,
  "clinical:write": Stethoscope,
  "operations:manage": Activity,
  "reports:read": BookOpenCheck,
};

const permissionNames: Record<string, string> = {
  "platform:manage": "Administrar plataforma",
  "tenant:manage": "Administrar establecimientos",
  "users:manage": "Administrar usuarios",
  "patients:manage": "Gestionar pacientes",
  "appointments:read": "Consultar agenda",
  "appointments:manage": "Gestionar citas",
  "clinical:read": "Consultar información clínica",
  "clinical:write": "Gestionar atenciones",
  "operations:manage": "Panel de Servicio",
  "reports:read": "Consultar reportes",
};

function initials(value: string) {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toLocaleUpperCase("es"))
    .join("");
}

function sectionForHash(hash: string, navigation: RoleNavigationItem[]) {
  if (!hash || hash === "#overview") return "Resumen";
  if (hash === "#permissions") return "Permisos activos";
  if (hash === "#design-system") return "Componentes";
  return navigation.find((item) => hash === `#${item.sectionId}`)?.label ?? "Resumen";
}

export function AuthenticatedWorkspace({
  user,
  keycloakIssuer,
  clientId,
}: AuthenticatedWorkspaceProps) {
  const { toast } = useToast();
  const [identity, setIdentity] = useState<IdentityProfile | null>(null);
  const [loadingIdentity, setLoadingIdentity] = useState(true);
  const [identityError, setIdentityError] = useState<string | null>(null);
  const [tenantDialogOpen, setTenantDialogOpen] = useState(false);
  const [tenantIdInput, setTenantIdInput] = useState("");
  const [validatingTenant, setValidatingTenant] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [currentSection, setCurrentSection] = useState("Resumen");

  const navigation = useMemo(
    () => {
      const items = getRoleNavigation(identity?.permissions ?? []);
      const scopedRole =
        identity?.roles.includes("service") || identity?.roles.includes("doctor");
      return scopedRole
        ? items.filter((item) => item.permission !== "appointments:read")
        : items;
    },
    [identity?.permissions, identity?.roles],
  );
  const displayName = user.name || user.email || "Usuario";
  const userInitials = initials(displayName) || "MG";
  const filteredNavigation = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("es");
    if (!query) return navigation;
    return navigation.filter((item) =>
      `${item.label} ${item.description}`.toLocaleLowerCase("es").includes(query),
    );
  }, [navigation, search]);

  const fetchIdentity = useCallback(async (tenantId?: string, siteId?: string) => {
    const params = new URLSearchParams();
    if (tenantId) params.set("tenant_id", tenantId);
    if (siteId) params.set("site_id", siteId);
    const query = params.size ? `?${params.toString()}` : "";
    const response = await fetch(`/api/backend/auth/me${query}`, {
      cache: "no-store",
    });
    const body = (await response.json()) as IdentityProfile & { detail?: string };
    if (!response.ok) {
      throw new Error(body.detail ?? "No fue posible consultar tus permisos.");
    }
    return body;
  }, []);

  useEffect(() => {
    let active = true;
    const loadIdentity = async () => {
      const savedTenantId = window.sessionStorage.getItem("medigest.activeTenantId");
      const savedSiteId = window.sessionStorage.getItem("medigest.activeSiteId");
      try {
        const profile = await fetchIdentity(
          savedTenantId ?? undefined,
          savedSiteId ?? undefined,
        );
        if (!active) return;
        setIdentity(profile);
        setIdentityError(null);
      } catch (error) {
        if (!active) return;
        let identityFailure = error;
        if (savedSiteId) {
          window.sessionStorage.removeItem("medigest.activeSiteId");
          try {
            const tenantProfile = await fetchIdentity(savedTenantId ?? undefined);
            if (!active) return;
            setIdentity(tenantProfile);
            setIdentityError(null);
            toast({
              tone: "error",
              title: "Sede no disponible",
              description: "Se quitó el contexto anterior. Selecciona una sede para actualizar tus permisos.",
            });
            return;
          } catch (siteContextError) {
            if (!active) return;
            identityFailure = siteContextError;
          }
        }
        if (savedTenantId) {
          window.sessionStorage.removeItem("medigest.activeTenantId");
          window.sessionStorage.removeItem("medigest.activeSiteId");
          try {
            const globalProfile = await fetchIdentity();
            if (!active) return;
            setIdentity(globalProfile);
            setIdentityError(null);
            toast({
              tone: "error",
              title: "Establecimiento no disponible",
              description: "Se quitó el contexto anterior. Verifica tu membresía para continuar.",
            });
          } catch (fallbackError) {
            if (!active) return;
            setIdentityError(
              fallbackError instanceof Error
                ? fallbackError.message
                : "No fue posible consultar tus permisos.",
            );
          }
        } else {
          setIdentityError(
            identityFailure instanceof Error
              ? identityFailure.message
              : "No fue posible consultar tus permisos.",
          );
        }
      } finally {
        if (active) setLoadingIdentity(false);
      }
    };

    void loadIdentity();
    return () => {
      active = false;
    };
  }, [fetchIdentity, toast]);

  useEffect(() => {
    const updateSection = () => {
      setCurrentSection(sectionForHash(window.location.hash, navigation));
    };
    updateSection();
    window.addEventListener("hashchange", updateSection);
    return () => window.removeEventListener("hashchange", updateSection);
  }, [navigation]);

  const selectTenant = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const tenantId = tenantIdInput.trim();
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(tenantId)) {
      toast({
        tone: "error",
        title: "ID de establecimiento inválido",
        description: "Ingresa un UUID válido para verificar tu membresía.",
      });
      return;
    }

    setValidatingTenant(true);
    try {
      const profile = await fetchIdentity(tenantId);
      setIdentity(profile);
      setIdentityError(null);
      window.sessionStorage.setItem("medigest.activeTenantId", tenantId);
      window.sessionStorage.removeItem("medigest.activeSiteId");
      setTenantDialogOpen(false);
      setTenantIdInput("");
      toast({
        tone: "success",
        title: "Establecimiento verificado",
        description: "El menú se actualizó con los permisos confirmados por MediGest.",
      });
    } catch (error) {
      toast({
        tone: "error",
        title: "No se pudo validar el establecimiento",
        description:
          error instanceof Error
            ? error.message
            : "No fue posible consultar tu membresía.",
      });
    } finally {
      setValidatingTenant(false);
    }
  };

  const activateTenant = async (tenantId: string) => {
    try {
      const profile = await fetchIdentity(tenantId);
      setIdentity(profile);
      setIdentityError(null);
      window.sessionStorage.setItem("medigest.activeTenantId", tenantId);
      window.sessionStorage.removeItem("medigest.activeSiteId");
      toast({
        tone: "success",
        title: "Establecimiento activo",
        description: "El backend verificó los permisos para este contexto.",
      });
    } catch (error) {
      toast({
        tone: "error",
        title: "No se pudo cambiar de establecimiento",
        description:
          error instanceof Error ? error.message : "No fue posible validar tu membresía.",
      });
    }
  };

  const activateSite = async (siteId: string) => {
    const tenantId = identity?.tenant_id;
    if (!tenantId || !siteId) return;
    try {
      const profile = await fetchIdentity(tenantId, siteId);
      setIdentity(profile);
      setIdentityError(null);
      window.sessionStorage.setItem("medigest.activeSiteId", siteId);
    } catch (error) {
      toast({
        tone: "error",
        title: "No se pudo validar la sede",
        description:
          error instanceof Error ? error.message : "No fue posible consultar tus permisos.",
      });
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 border-b border-border bg-white/95 backdrop-blur">
        <div className="flex h-[4.25rem] items-center gap-3 px-4 sm:px-6 lg:px-8">
          <Button
            aria-expanded={mobileMenuOpen}
            aria-label={mobileMenuOpen ? "Cerrar navegación" : "Abrir navegación"}
            className="lg:hidden"
            onClick={() => setMobileMenuOpen((open) => !open)}
            size="icon"
            variant="ghost"
          >
            {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
          </Button>

          <a aria-label="MediGest, resumen" className="flex shrink-0 items-center gap-2.5" href="#overview">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-800 text-white">
              <Stethoscope aria-hidden="true" size={19} />
            </span>
            <span className="text-base font-bold tracking-tight text-ink">MediGest</span>
          </a>

          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <span className="hidden items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-800 md:inline-flex">
              <ShieldCheck aria-hidden="true" size={14} />
              Sesión protegida
            </span>
            <div className="relative">
              <Button
                aria-expanded={notificationOpen}
                aria-haspopup="dialog"
                aria-label="Notificaciones"
                onClick={() => setNotificationOpen((open) => !open)}
                size="icon"
                variant="ghost"
              >
                <Bell aria-hidden="true" size={19} />
              </Button>
              {notificationOpen ? (
                <div
                  aria-label="Notificaciones"
                  className="absolute right-0 top-12 z-50 w-[min(20rem,calc(100vw-2rem))] rounded-2xl border border-border bg-white p-4 shadow-soft"
                  role="dialog"
                >
                  <div className="flex items-center justify-between">
                    <h2 className="text-sm font-semibold">Notificaciones</h2>
                    <Button
                      aria-label="Cerrar notificaciones"
                      onClick={() => setNotificationOpen(false)}
                      size="icon"
                      variant="ghost"
                    >
                      <X aria-hidden="true" size={16} />
                    </Button>
                  </div>
                  <p className="mt-3 rounded-xl bg-slate-50 px-3 py-4 text-center text-sm text-muted-foreground">
                    No hay notificaciones nuevas.
                  </p>
                </div>
              ) : null}
            </div>
            <div className="hidden h-8 w-px bg-border sm:block" />
            <div className="hidden min-w-0 text-right sm:block">
              <p className="max-w-40 truncate text-sm font-semibold text-foreground">
                {displayName}
              </p>
              <p className="max-w-40 truncate text-xs text-muted-foreground">
                {identity?.roles.length
                  ? identity.roles.map((role) => roleLabels[role] ?? role).join(" · ")
                  : "Cuenta institucional"}
              </p>
            </div>
            <span
              aria-hidden="true"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-teal-100 text-xs font-bold text-teal-900"
            >
              {userInitials}
            </span>
            <div className="hidden sm:block">
              <AuthActions
                authenticated
                clientId={clientId}
                keycloakIssuer={keycloakIssuer}
              />
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto flex min-h-[calc(100vh-4.25rem)] max-w-[1600px]">
        {mobileMenuOpen ? (
          <button
            aria-label="Cerrar menú de navegación"
            className="fixed inset-0 z-20 bg-slate-950/30 lg:hidden"
            onClick={() => setMobileMenuOpen(false)}
            type="button"
          />
        ) : null}
        <aside
          aria-label="Navegación principal"
          className={`fixed bottom-0 left-0 top-[4.25rem] z-20 flex w-[min(18rem,85vw)] flex-col border-r border-border bg-white px-4 py-5 transition-transform lg:sticky lg:top-[4.25rem] lg:z-10 lg:h-[calc(100vh-4.25rem)] lg:w-64 lg:translate-x-0 ${
            mobileMenuOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
          }`}
        >
          <div className="mb-5 rounded-2xl bg-teal-50/80 p-3.5">
            <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-teal-800">
              Espacio de trabajo
            </p>
            <p className="mt-1 truncate text-sm font-semibold text-ink">
              {identity?.tenant_id ? "Establecimiento activo" : "Sin establecimiento"}
            </p>
            <button
              className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-teal-800 hover:text-teal-900"
              onClick={() => setTenantDialogOpen(true)}
              type="button"
            >
              {identity?.tenant_id ? "Cambiar contexto" : "Verificar membresía"}
              <ChevronDown aria-hidden="true" size={14} />
            </button>
          </div>

          <label className="relative block">
            <Search
              aria-hidden="true"
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              size={16}
            />
            <Input
              aria-label="Buscar en navegación"
              className="h-10 bg-slate-50 pl-9 text-xs shadow-none"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar sección..."
              value={search}
            />
          </label>

          <nav aria-label="Secciones" className="mt-6 flex-1 space-y-1">
            <p className="px-3 pb-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
              Menú principal
            </p>
            <a
              className={`flex min-h-10 items-center gap-3 rounded-xl px-3 text-sm ${
                currentSection === "Resumen"
                  ? "bg-teal-50 font-semibold text-teal-900"
                  : "text-slate-600 hover:bg-slate-50 hover:text-ink"
              }`}
              href="#overview"
              onClick={() => setMobileMenuOpen(false)}
            >
              <LayoutDashboard aria-hidden="true" size={17} />
              Resumen
            </a>
            {filteredNavigation.map((item) => {
              const Icon = permissionIcons[item.permission] ?? CircleHelp;
              return (
                <a
                  className={`flex min-h-10 items-center gap-3 rounded-xl px-3 text-sm transition ${
                    currentSection === item.label
                      ? "bg-teal-50 font-semibold text-teal-900"
                      : "text-slate-600 hover:bg-slate-50 hover:text-ink"
                  }`}
                  href={`#${item.sectionId}`}
                  key={item.permission}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  <Icon aria-hidden="true" size={17} />
                  <span className="truncate">{item.label}</span>
                </a>
              );
            })}
            {search && filteredNavigation.length === 0 ? (
              <p className="px-3 py-3 text-xs leading-5 text-muted-foreground">
                No hay secciones disponibles que coincidan.
              </p>
            ) : null}
            <div className="!my-4 border-t border-border" />
            <a
              className={`flex min-h-10 items-center gap-3 rounded-xl px-3 text-sm transition ${
                currentSection === "Permisos activos"
                  ? "bg-teal-50 font-semibold text-teal-900"
                  : "text-slate-600 hover:bg-slate-50 hover:text-ink"
              }`}
              href="#permissions"
              onClick={() => setMobileMenuOpen(false)}
            >
              <ShieldCheck aria-hidden="true" size={17} />
              Permisos activos
            </a>
            <a
              className={`flex min-h-10 items-center gap-3 rounded-xl px-3 text-sm transition ${
                currentSection === "Componentes"
                  ? "bg-teal-50 font-semibold text-teal-900"
                  : "text-slate-600 hover:bg-slate-50 hover:text-ink"
              }`}
              href="#design-system"
              onClick={() => setMobileMenuOpen(false)}
            >
              <BookOpenCheck aria-hidden="true" size={17} />
              Componentes
            </a>
          </nav>

          <div className="rounded-2xl border border-slate-200 p-3.5">
            <div className="flex items-center gap-2">
              <CircleHelp aria-hidden="true" className="text-teal-700" size={17} />
              <p className="text-xs font-semibold text-ink">¿Necesitas ayuda?</p>
            </div>
            <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
              Contacta al administrador de tu establecimiento.
            </p>
          </div>

          <div className="mt-4 border-t border-border pt-3 sm:hidden">
            <AuthActions
              authenticated
              clientId={clientId}
              keycloakIssuer={keycloakIssuer}
            />
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-4 pb-12 pt-6 sm:px-6 lg:px-10 lg:pt-8">
          <div className="mx-auto max-w-6xl">
            <Breadcrumbs current={currentSection} />
            <section
              aria-labelledby="overview-title"
              className="mt-7 scroll-mt-24"
              id="overview"
            >
              <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
                <div>
                  <p className="text-sm font-medium text-teal-700">Tu espacio de trabajo</p>
                  <h1
                    className="mt-1 text-2xl font-semibold tracking-tight text-ink sm:text-3xl"
                    id="overview-title"
                  >
                    Hola, {displayName.split(" ")[0]}
                  </h1>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                    Accede a las herramientas habilitadas para tu cuenta. MediGest no presenta
                    métricas ni registros hasta conectarse con datos autorizados.
                  </p>
                </div>
                <Button
                  className="w-fit"
                  onClick={() => setTenantDialogOpen(true)}
                  variant="outline"
                >
                  <Building2 aria-hidden="true" size={16} />
                  {identity?.tenant_id ? "Cambiar establecimiento" : "Verificar establecimiento"}
                </Button>
              </div>
            </section>

            <div className="mt-7 grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
              <Card className="scroll-mt-24" id="permissions">
                <CardHeader className="flex-row items-start justify-between gap-4">
                  <div>
                    <CardTitle>Permisos activos</CardTitle>
                    <CardDescription className="mt-1">
                      Consultados desde el servidor según tu sesión y contexto actual.
                    </CardDescription>
                  </div>
                  <Badge tone={identity?.permissions.length ? "green" : "slate"}>
                    {loadingIdentity
                      ? "Verificando"
                      : identity?.permissions.length
                        ? `${identity.permissions.length} permisos`
                        : "Sin permisos"}
                  </Badge>
                </CardHeader>
                <CardContent>
                  {identityError ? (
                    <div
                      className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
                      role="alert"
                    >
                      {identityError}
                    </div>
                  ) : loadingIdentity ? (
                    <div
                      aria-label="Consultando permisos"
                      className="space-y-3"
                      role="status"
                    >
                      <div className="h-10 animate-pulse rounded-lg bg-slate-100" />
                      <div className="h-10 animate-pulse rounded-lg bg-slate-100" />
                    </div>
                  ) : identity?.permissions.length ? (
                    <Table>
                      <TableHeader>
                        <TableRow className="hover:bg-transparent">
                          <TableHead>Capacidad</TableHead>
                          <TableHead className="hidden sm:table-cell">Código</TableHead>
                          <TableHead>Tipo</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {identity.permissions.map((permission) => (
                          <TableRow key={permission}>
                            <TableCell className="font-medium">
                              {permissionNames[permission] ?? permission}
                            </TableCell>
                            <TableCell className="hidden font-mono text-xs text-muted-foreground sm:table-cell">
                              {permission}
                            </TableCell>
                            <TableCell>
                              <Badge tone="teal">
                                {permission.split(":")[1] === "read" ? "Lectura" : "Gestión"}
                              </Badge>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  ) : (
                    <EmptyState
                      action={
                        <Button onClick={() => setTenantDialogOpen(true)} variant="outline">
                          <Building2 aria-hidden="true" size={16} />
                          Verificar membresía
                        </Button>
                      }
                      description={
                        identity?.tenant_id
                          ? "Tu cuenta no tiene permisos asignados para este establecimiento. Contacta al administrador."
                          : "Selecciona un establecimiento para consultar los permisos que el servidor te ha asignado."
                      }
                      title="No hay permisos para mostrar"
                    />
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Tu cuenta</CardTitle>
                  <CardDescription>
                    Información de sesión y roles devuelta por MediGest.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center gap-3 rounded-xl bg-slate-50 p-3.5">
                    <span className="flex h-10 w-10 items-center justify-center rounded-full bg-teal-100 text-sm font-bold text-teal-900">
                      {userInitials}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{displayName}</p>
                      <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                    </div>
                  </div>
                  <div>
                    <p className="mb-2 text-xs font-semibold text-muted-foreground">Roles</p>
                    <div className="flex flex-wrap gap-2">
                      {loadingIdentity ? (
                        <span className="text-sm text-muted-foreground">Verificando…</span>
                      ) : identity?.roles.length ? (
                        identity.roles.map((role) => (
                          <Badge key={role} tone="teal">
                            {roleLabels[role] ?? role}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-sm text-muted-foreground">
                          No se encontraron roles en el contexto actual.
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="rounded-xl border border-teal-700/10 bg-teal-50/60 p-3.5">
                    <div className="flex items-start gap-2.5">
                      <ShieldCheck aria-hidden="true" className="mt-0.5 shrink-0 text-teal-800" size={17} />
                      <p className="text-xs leading-5 text-teal-900">
                        El menú se construye solo con los permisos confirmados por el servidor.
                        Los datos de salud no se muestran en este espacio de diseño.
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            <section aria-labelledby="design-system-title" className="mt-10" id="design-system">
              <div className="mb-4">
                <p className="text-xs font-bold uppercase tracking-[0.13em] text-teal-700">
                  Base de interfaz
                </p>
                <h2 className="mt-1 text-xl font-semibold tracking-tight text-ink" id="design-system-title">
                  Componentes accesibles
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Controles reutilizables para construir las siguientes vistas.
                </p>
              </div>
              <Card>
                <CardContent className="grid gap-6 pt-5 sm:grid-cols-2 sm:pt-6">
                  <div>
                    <label className="text-sm font-medium" htmlFor="design-search">
                      Campo de texto
                    </label>
                    <Input
                      className="mt-2"
                      id="design-search"
                      placeholder="Los campos incluyen foco visible"
                      readOnly
                      value=""
                    />
                    <p className="mt-1.5 text-xs text-muted-foreground">
                      Etiquetas explícitas y estados de foco accesibles.
                    </p>
                  </div>
                  <div>
                    <p className="text-sm font-medium">Acciones y estados</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Badge>Disponible</Badge>
                      <Badge tone="slate">Sin datos</Badge>
                      <Button
                        onClick={() =>
                          toast({
                            tone: "success",
                            title: "Notificación de prueba",
                            description: "Los mensajes usan una región accesible y se descartan automáticamente.",
                          })
                        }
                        size="sm"
                        variant="outline"
                      >
                        Probar notificación
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </section>

            {identity &&
            (identity.roles.includes("administrator") ||
              identity.roles.includes("superadmin")) ? (
              <section
                aria-labelledby="admin-dashboard-title"
                className="mt-10 scroll-mt-24"
                id="admin-dashboard"
              >
                <div className="mb-4">
                  <p className="text-xs font-bold uppercase tracking-[0.13em] text-teal-700">
                    Administración
                  </p>
                  <h2
                    className="mt-1 text-xl font-semibold tracking-tight text-ink"
                    id="admin-dashboard-title"
                  >
                    Dashboard administrativo
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Indicadores calculados con actividad real del establecimiento.
                  </p>
                </div>
                <AdminDashboard
                  activeSiteId={identity.site_id}
                  tenantId={identity.tenant_id}
                />
              </section>
            ) : null}

            {identity ? (
              <AdministrationPanel
                onTenantSelect={(tenantId) => void activateTenant(tenantId)}
                onSiteSelect={(siteId) => void activateSite(siteId)}
                permissions={identity.permissions}
                tenantId={identity.tenant_id}
              />
            ) : null}

            {identity?.permissions.includes("patients:manage") ? (
              <section
                aria-labelledby="patients-manage-title"
                className="mt-10 scroll-mt-24"
                id="patients-manage"
              >
                <div className="mb-4">
                  <p className="text-xs font-bold uppercase tracking-[0.13em] text-teal-700">
                    Ventanilla
                  </p>
                  <h2
                    className="mt-1 text-xl font-semibold tracking-tight text-ink"
                    id="patients-manage-title"
                  >
                    Registro y búsqueda de pacientes
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Administración de datos de contacto y correcciones auditadas.
                  </p>
                </div>
                <PatientManager
                  canManageRules={
                    identity.roles.includes("administrator") &&
                    identity.permissions.includes("tenant:manage")
                  }
                  tenantId={identity.tenant_id}
                  siteId={identity.site_id}
                />
              </section>
            ) : null}

            {identity?.permissions.includes("patients:manage") &&
            identity.permissions.some((permission) =>
              ["appointments:read", "appointments:manage"].includes(permission),
            ) ? (
              <section
                aria-labelledby="reception-title"
                className="mt-10 scroll-mt-24"
                id="reception"
              >
                <div className="mb-4">
                  <p className="text-xs font-bold uppercase tracking-[0.13em] text-teal-700">
                    Ventanilla
                  </p>
                  <h2
                    className="mt-1 text-xl font-semibold tracking-tight text-ink"
                    id="reception-title"
                  >
                    Recepción de pacientes
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Confirma identidad y llegada, registra tiempos y deriva a la cola de atención.
                  </p>
                </div>
                <ReceptionDesk
                  canManage={identity.permissions.includes("appointments:manage")}
                  siteId={identity.site_id}
                  tenantId={identity.tenant_id}
                />
              </section>
            ) : null}

            {identity?.permissions.includes("operations:manage") ? (
              <section
                aria-labelledby="service-queue-title"
                className="mt-10 scroll-mt-24"
                id="service-queue"
              >
                <div className="mb-4">
                  <p className="text-xs font-bold uppercase tracking-[0.13em] text-teal-700">
                    Servicio
                  </p>
                  <h2
                    className="mt-1 text-xl font-semibold tracking-tight text-ink"
                    id="service-queue-title"
                  >
                    Preparación y cola operativa
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Asigna sala, prepara el turno y registra los tiempos de atención.
                  </p>
                </div>
                <ServiceQueuePanel
                  siteId={identity.site_id}
                  tenantId={identity.tenant_id}
                />
              </section>
            ) : null}

            {identity?.roles.includes("doctor") &&
            identity.permissions.includes("clinical:read") ? (
              <section
                aria-labelledby="doctor-dashboard-title"
                className="mt-10 scroll-mt-24"
                id="doctor-dashboard"
              >
                <div className="mb-4">
                  <p className="text-xs font-bold uppercase tracking-[0.13em] text-teal-700">
                    Atención clínica
                  </p>
                  <h2
                    className="mt-1 text-xl font-semibold tracking-tight text-ink"
                    id="doctor-dashboard-title"
                  >
                    Dashboard médico
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Agenda, llegada de pacientes y expedientes dentro de tu ámbito asistencial.
                  </p>
                </div>
                <DoctorDashboard
                  siteId={identity.site_id}
                  tenantId={identity.tenant_id}
                />
              </section>
            ) : null}

            {!identity?.roles.includes("service") &&
            !identity?.roles.includes("doctor") &&
            identity?.permissions.some((permission) =>
              ["appointments:read", "appointments:manage"].includes(permission),
            ) ? (
              <section
                aria-labelledby="appointments-title"
                className="mt-10 scroll-mt-24"
                id="appointments"
              >
                <div className="mb-4">
                  <p className="text-xs font-bold uppercase tracking-[0.13em] text-teal-700">
                    Agenda
                  </p>
                  <h2
                    className="mt-1 text-xl font-semibold tracking-tight text-ink"
                    id="appointments-title"
                  >
                    Agenda de citas
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Calendario por sede, con disponibilidad validada antes de reservar.
                  </p>
                </div>
                <AppointmentCalendar
                  canManage={identity.permissions.includes("appointments:manage")}
                  canManageHolidays={
                    identity.roles.includes("administrator") &&
                    identity.permissions.includes("tenant:manage")
                  }
                  siteId={identity.site_id}
                  tenantId={identity.tenant_id}
                />
              </section>
            ) : null}

            {navigation
              .filter(
                (item) =>
                  item.permission !== "platform:manage" &&
                  item.permission !== "tenant:manage" &&
                  item.permission !== "patients:manage" &&
                  item.permission !== "appointments:read" &&
                  item.permission !== "appointments:manage" &&
                  item.permission !== "operations:manage" &&
                  item.permission !== "clinical:read" &&
                  item.permission !== "clinical:write",
              )
              .map((item) => (
              <section
                aria-labelledby={`${item.sectionId}-title`}
                className="mt-10 scroll-mt-24"
                id={item.sectionId}
                key={item.permission}
              >
                <div className="mb-4">
                  <p className="text-xs font-bold uppercase tracking-[0.13em] text-teal-700">
                    Área autorizada
                  </p>
                  <h2
                    className="mt-1 text-xl font-semibold tracking-tight text-ink"
                    id={`${item.sectionId}-title`}
                  >
                    {item.label}
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
                </div>
                <Card>
                  <EmptyState
                    description="La estructura visual está preparada. Esta área no consulta ni simula datos; su funcionalidad se implementará en una jornada posterior."
                    title="Módulo todavía no disponible"
                  />
                </Card>
              </section>
              ))}

            <footer className="mt-12 flex flex-col gap-2 border-t border-border pt-5 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
              <span>MediGest · Espacio de trabajo seguro</span>
              <a className="font-medium text-teal-800 hover:underline" href={`${keycloakIssuer}/account`} rel="noreferrer" target="_blank">
                Seguridad de la cuenta
              </a>
            </footer>
          </div>
        </main>
      </div>

      <Dialog
        description="El backend confirmará tu membresía antes de actualizar la navegación."
        onOpenChange={setTenantDialogOpen}
        open={tenantDialogOpen}
        title="Seleccionar establecimiento"
      >
        <form className="space-y-4" onSubmit={selectTenant}>
          <div>
            <label className="text-sm font-medium" htmlFor="tenant-id">
              ID del establecimiento
            </label>
            <Input
              autoComplete="off"
              className="mt-2 font-mono"
              id="tenant-id"
              onChange={(event) => setTenantIdInput(event.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              required
              value={tenantIdInput}
            />
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              Solicita el identificador a tu administrador. MediGest validará tu membresía;
              el ID por sí solo no concede acceso.
            </p>
          </div>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button
              onClick={() => setTenantDialogOpen(false)}
              type="button"
              variant="outline"
            >
              Cancelar
            </Button>
            <Button disabled={validatingTenant} type="submit">
              {validatingTenant ? "Verificando…" : "Validar membresía"}
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
