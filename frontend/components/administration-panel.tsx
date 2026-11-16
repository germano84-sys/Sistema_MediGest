"use client";

import { Building2, CirclePlus, Pencil, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { EmptyState } from "./ui/empty-state";
import { Input } from "./ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { useToast } from "./ui/toast";
import { UserDoctorManager } from "./user-doctor-manager";

type AdminRecord = Record<string, unknown> & { id?: string };
type Resource =
  | "tenants"
  | "specialties"
  | "sites"
  | "tenant-specialties"
  | "rooms"
  | "hours"
  | "settings";
type FieldDefinition = {
  name: string;
  label: string;
  kind?: "text" | "boolean" | "time" | "weekday" | "json" | "status" | "specialty";
  initial?: string;
  editOnly?: boolean;
};

const resourceLabels: Record<Resource, string> = {
  tenants: "Establecimientos",
  specialties: "Especialidades",
  sites: "Sedes",
  "tenant-specialties": "Especialidades habilitadas",
  rooms: "Consultorios",
  hours: "Horarios",
  settings: "Parámetros",
};

const fields: Record<Resource, FieldDefinition[]> = {
  tenants: [
    { name: "name", label: "Nombre" },
    { name: "slug", label: "Identificador", initial: "" },
    { name: "status", label: "Estado", kind: "status", initial: "active", editOnly: true },
  ],
  specialties: [
    { name: "code", label: "Código" },
    { name: "name", label: "Nombre" },
    { name: "is_active", label: "Estado activo", kind: "boolean", initial: "true" },
  ],
  sites: [
    { name: "code", label: "Código" },
    { name: "name", label: "Nombre" },
    { name: "timezone", label: "Zona horaria IANA", initial: "America/Guayaquil" },
    { name: "is_active", label: "Estado activo", kind: "boolean", initial: "true" },
  ],
  "tenant-specialties": [
    { name: "specialty_id", label: "Especialidad del catálogo", kind: "specialty" },
    { name: "is_active", label: "Estado activo", kind: "boolean", initial: "true" },
  ],
  rooms: [
    { name: "code", label: "Código" },
    { name: "name", label: "Nombre" },
    { name: "room_type", label: "Tipo de consultorio", initial: "consultation" },
    { name: "is_active", label: "Estado activo", kind: "boolean", initial: "true" },
  ],
  hours: [
    { name: "weekday", label: "Día de la semana", kind: "weekday", initial: "0" },
    { name: "opens_at", label: "Apertura", kind: "time", initial: "08:00" },
    { name: "closes_at", label: "Cierre", kind: "time", initial: "17:00" },
    { name: "is_closed", label: "Día cerrado", kind: "boolean", initial: "false" },
  ],
  settings: [
    { name: "key", label: "Clave" },
    { name: "value", label: "Valor JSON", kind: "json", initial: "{}" },
  ],
};

const columns: Record<Resource, string[]> = {
  tenants: ["name", "slug", "status"],
  specialties: ["code", "name", "is_active"],
  sites: ["code", "name", "timezone", "is_active"],
  "tenant-specialties": ["code", "name", "is_active"],
  rooms: ["code", "name", "room_type", "is_active"],
  hours: ["weekday", "opens_at", "closes_at", "is_closed"],
  settings: ["key", "value"],
};

const dayLabels = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

function getDisplayValue(key: string, value: unknown) {
  if (typeof value === "boolean") return value ? "Activo" : "Inactivo";
  if (key === "weekday" && typeof value === "number") return dayLabels[value] ?? value;
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  return String(value ?? "—");
}

function recordKey(resource: Resource, record: AdminRecord) {
  return resource === "settings" ? String(record.key) : String(record.id ?? "");
}

function fieldsFor(resource: Resource, isEditing: boolean) {
  return fields[resource].filter(
    (field) =>
      !(field.editOnly && !isEditing) &&
      !(isEditing && resource === "tenant-specialties" && field.name === "specialty_id"),
  );
}

function resourcePath(
  resource: Resource,
  tenantId: string | null,
  siteId: string | null,
) {
  if (resource === "tenants" || resource === "specialties") return `/${resource}`;
  if (!tenantId) throw new Error("Selecciona un establecimiento para continuar.");
  if (resource === "sites") return `/tenants/${tenantId}/sites`;
  if (resource === "tenant-specialties") return `/tenants/${tenantId}/specialties`;
  if (resource === "settings") return `/tenants/${tenantId}/settings`;
  if (!siteId) throw new Error("Selecciona una sede para continuar.");
  return `/tenants/${tenantId}/sites/${siteId}/${resource}`;
}

async function adminFetch<T>(
  path: string,
  method = "GET",
  payload?: Record<string, unknown>,
): Promise<T> {
  const response = await fetch(`/api/backend/admin${path}`, {
    method,
    headers: payload ? { "Content-Type": "application/json" } : undefined,
    body: payload ? JSON.stringify(payload) : undefined,
    cache: "no-store",
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new Error(body?.detail ?? `La solicitud falló (${response.status}).`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function ResourceManager({
  resources,
  tenantId,
  siteId,
  onTenantSelect,
  tenants,
  onTenantsLoaded,
  allowTenantSelection = false,
}: {
  resources: Resource[];
  tenantId: string | null;
  siteId: string | null;
  onTenantSelect?: (tenantId: string) => void;
  tenants?: AdminRecord[];
  onTenantsLoaded?: (tenants: AdminRecord[]) => void;
  allowTenantSelection?: boolean;
}) {
  const { toast } = useToast();
  const [resource, setResource] = useState<Resource>(resources[0]);
  const [records, setRecords] = useState<AdminRecord[]>([]);
  const [sites, setSites] = useState<AdminRecord[]>([]);
  const [catalogSpecialties, setCatalogSpecialties] = useState<AdminRecord[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState(siteId ?? "");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<AdminRecord | null>(null);
  const [creating, setCreating] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const isSiteBound = resource === "rooms" || resource === "hours";
  const effectiveSiteId = isSiteBound ? selectedSiteId || null : siteId;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (isSiteBound) {
        const loadedSites = tenantId
          ? await adminFetch<AdminRecord[]>(`/tenants/${tenantId}/sites`)
          : [];
        setSites(loadedSites);
        const selectedSiteExists = loadedSites.some(
          (site) => String(site.id) === selectedSiteId,
        );
        const nextSiteId = selectedSiteExists
          ? selectedSiteId
          : String(loadedSites[0]?.id ?? "");
        if (nextSiteId !== selectedSiteId) setSelectedSiteId(nextSiteId);
        if (!nextSiteId) {
          setRecords([]);
          return;
        }
        setRecords(
          await adminFetch<AdminRecord[]>(
            resourcePath(resource, tenantId, nextSiteId),
          ),
        );
        return;
      }
      if (resource === "tenant-specialties") {
        setCatalogSpecialties(await adminFetch<AdminRecord[]>("/specialties"));
      }
      if (
        resource !== "tenants" &&
        resource !== "specialties" &&
        !tenantId
      ) {
        setRecords([]);
        return;
      }
      const loadedRecords = await adminFetch<AdminRecord[]>(
        resourcePath(resource, tenantId, null),
      );
      setRecords(loadedRecords);
      if (resource === "tenants" && onTenantsLoaded) {
        onTenantsLoaded(loadedRecords);
      }
    } catch (loadError) {
      const message =
        loadError instanceof Error ? loadError.message : "No se pudo cargar la información.";
      setError(message);
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, [isSiteBound, onTenantsLoaded, resource, selectedSiteId, tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const formFields = useMemo(
    () => fieldsFor(resource, editing !== null),
    [editing, resource],
  );

  const startCreate = () => {
    setEditing(null);
    setValues(
      Object.fromEntries(
        fieldsFor(resource, false).map((field) => [field.name, field.initial ?? ""]),
      ),
    );
    setCreating(true);
  };

  const startEdit = (record: AdminRecord) => {
    setEditing(record);
    setValues(
      Object.fromEntries(
        fieldsFor(resource, true).map((field) => {
          const value = record[field.name];
          return [
            field.name,
            field.kind === "json"
              ? JSON.stringify(value ?? {}, null, 2)
              : value === undefined || value === null
                ? ""
                : String(value),
          ];
        }),
      ),
    );
    setCreating(true);
  };

  const closeForm = () => {
    setCreating(false);
    setEditing(null);
    setValues({});
  };

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {};
      for (const field of formFields) {
        const value = values[field.name] ?? "";
        if (field.kind === "boolean") payload[field.name] = value === "true";
        else if (field.kind === "weekday") payload[field.name] = Number(value);
        else if (field.kind === "json") {
          try {
            payload[field.name] = JSON.parse(value) as unknown;
          } catch {
            throw new Error("El valor JSON no tiene un formato válido.");
          }
        } else payload[field.name] = value;
      }
      if (resource === "hours" && payload.is_closed === true) {
        payload.opens_at = null;
        payload.closes_at = null;
      }
      const base = resourcePath(resource, tenantId, effectiveSiteId);
      const suffix =
        editing && resource === "settings"
          ? `/${encodeURIComponent(String(editing.key))}`
          : editing
            ? `/${encodeURIComponent(String(editing.id))}`
            : "";
      await adminFetch(
        `${base}${suffix}`,
        editing ? "PATCH" : "POST",
        payload,
      );
      closeForm();
      await load();
      toast({
        tone: "success",
        title: editing ? "Cambios guardados" : "Registro creado",
        description: `${resourceLabels[resource]} se actualizó correctamente.`,
      });
    } catch (saveError) {
      toast({
        tone: "error",
        title: "No se pudo guardar",
        description: saveError instanceof Error ? saveError.message : "Error inesperado.",
      });
    } finally {
      setSaving(false);
    }
  };

  const remove = async (record: AdminRecord) => {
    if (
      !window.confirm(
        "¿Eliminar este registro? Si tiene referencias asociadas, el servidor rechazará la operación.",
      )
    ) {
      return;
    }
    try {
      const base = resourcePath(resource, tenantId, effectiveSiteId);
      const key =
        resource === "settings" ? String(record.key) : String(record.id ?? "");
      await adminFetch(`${base}/${encodeURIComponent(key)}`, "DELETE");
      await load();
      toast({
        tone: "success",
        title: "Registro eliminado",
        description: `${resourceLabels[resource]} se actualizó correctamente.`,
      });
    } catch (deleteError) {
      toast({
        tone: "error",
        title: "No se pudo eliminar",
        description:
          deleteError instanceof Error ? deleteError.message : "Error inesperado.",
      });
    }
  };

  return (
    <div className="space-y-5">
      {allowTenantSelection ? (
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
          <label className="block text-sm font-medium" htmlFor="admin-tenant-select">
            Establecimiento activo
            <select
              className="mt-2 h-11 w-full rounded-xl border border-input bg-white px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
              id="admin-tenant-select"
              onChange={(event) => onTenantSelect?.(event.target.value)}
              value={tenantId ?? ""}
            >
              <option value="">Selecciona un establecimiento</option>
              {(tenants ?? []).map((tenant) => (
                <option key={String(tenant.id)} value={String(tenant.id)}>
                  {String(tenant.name)} · {String(tenant.slug)}
                </option>
              ))}
            </select>
          </label>
          <Button onClick={() => void load()} variant="outline">
            <RefreshCw aria-hidden="true" size={16} />
            Actualizar
          </Button>
        </div>
      ) : null}

      <div aria-label="Secciones de administración" className="flex flex-wrap gap-2" role="tablist">
        {resources.map((item) => (
          <button
            aria-selected={resource === item}
            className={`min-h-10 rounded-xl px-3.5 text-sm font-semibold transition ${
              resource === item
                ? "bg-teal-800 text-white"
                : "border border-border bg-white text-slate-600 hover:bg-slate-50"
            }`}
            key={item}
            onClick={() => {
              closeForm();
              setResource(item);
            }}
            role="tab"
            type="button"
          >
            {resourceLabels[item]}
          </button>
        ))}
      </div>

      {resource !== "tenants" && resource !== "specialties" && !tenantId ? (
        <EmptyState
          description="Selecciona un establecimiento para consultar y administrar sus recursos."
          title="Establecimiento requerido"
        />
      ) : null}

      {isSiteBound && tenantId && sites.length > 0 ? (
        <label className="block max-w-xl text-sm font-medium" htmlFor="admin-site-select">
          Sede
          <select
            className="mt-2 h-11 w-full rounded-xl border border-input bg-white px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
            id="admin-site-select"
            onChange={(event) => setSelectedSiteId(event.target.value)}
            value={effectiveSiteId ?? ""}
          >
            {sites.map((site) => (
              <option key={String(site.id)} value={String(site.id)}>
                {String(site.name)} · {String(site.code)}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {creating ? (
        <Card>
          <CardHeader>
            <CardTitle>{editing ? "Editar registro" : `Crear ${resourceLabels[resource].toLocaleLowerCase("es")}`}</CardTitle>
            <CardDescription>
              El backend valida permisos, formato e integridad antes de guardar.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={(event) => void save(event)}>
              <div className="grid gap-4 sm:grid-cols-2">
                {formFields.map((field) => (
                  <label
                    className={`block text-sm font-medium ${
                      field.kind === "json" ? "sm:col-span-2" : ""
                    }`}
                    htmlFor={`admin-field-${field.name}`}
                    key={field.name}
                  >
                    {field.label}
                    {field.kind === "boolean" ? (
                      <select
                        className="mt-2 h-11 w-full rounded-xl border border-input bg-white px-3 text-sm"
                        id={`admin-field-${field.name}`}
                        onChange={(event) =>
                          setValues((current) => ({
                            ...current,
                            [field.name]: event.target.value,
                          }))
                        }
                        value={values[field.name] ?? field.initial ?? "false"}
                      >
                        <option value="true">Activo / Sí</option>
                        <option value="false">Inactivo / No</option>
                      </select>
                    ) : field.kind === "weekday" ? (
                      <select
                        className="mt-2 h-11 w-full rounded-xl border border-input bg-white px-3 text-sm"
                        id={`admin-field-${field.name}`}
                        onChange={(event) =>
                          setValues((current) => ({
                            ...current,
                            [field.name]: event.target.value,
                          }))
                        }
                        value={values[field.name] ?? "0"}
                      >
                        {dayLabels.map((day, index) => (
                          <option key={day} value={index}>{day}</option>
                        ))}
                      </select>
                    ) : field.kind === "status" || field.kind === "specialty" ? (
                      <select
                        className="mt-2 h-11 w-full rounded-xl border border-input bg-white px-3 text-sm"
                        id={`admin-field-${field.name}`}
                        onChange={(event) =>
                          setValues((current) => ({
                            ...current,
                            [field.name]: event.target.value,
                          }))
                        }
                        required
                        value={values[field.name] ?? field.initial ?? ""}
                      >
                        {field.kind === "status" ? (
                          <>
                            <option value="active">Activo</option>
                            <option value="suspended">Suspendido</option>
                          </>
                        ) : (
                          <>
                            <option value="">Selecciona especialidad</option>
                            {catalogSpecialties.map((specialty) => (
                              <option key={String(specialty.id)} value={String(specialty.id)}>
                                {String(specialty.code)} · {String(specialty.name)}
                              </option>
                            ))}
                          </>
                        )}
                      </select>
                    ) : field.kind === "json" ? (
                      <textarea
                        className="mt-2 min-h-32 w-full rounded-xl border border-input bg-white px-3 py-2 font-mono text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20"
                        id={`admin-field-${field.name}`}
                        onChange={(event) =>
                          setValues((current) => {
                            const next = {
                              ...current,
                              [field.name]: event.target.value,
                            };
                            if (resource === "hours" && field.name === "is_closed") {
                              next.opens_at = event.target.value === "true" ? "" : "08:00";
                              next.closes_at = event.target.value === "true" ? "" : "17:00";
                            }
                            return next;
                          })
                        }
                        required
                        value={values[field.name] ?? "{}"}
                      />
                    ) : (
                      <Input
                        className="mt-2"
                        id={`admin-field-${field.name}`}
                        onChange={(event) =>
                          setValues((current) => ({
                            ...current,
                            [field.name]: event.target.value,
                          }))
                        }
                        required
                        disabled={
                          resource === "hours" &&
                          (field.name === "opens_at" || field.name === "closes_at") &&
                          values.is_closed === "true"
                        }
                        type={field.kind ?? "text"}
                        value={values[field.name] ?? ""}
                      />
                    )}
                  </label>
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button disabled={saving} type="submit">
                  {saving ? "Guardando…" : "Guardar"}
                </Button>
                <Button onClick={closeForm} type="button" variant="outline">
                  Cancelar
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>{resourceLabels[resource]}</CardTitle>
            <CardDescription className="mt-1">
              Registros persistidos y consultados desde la API autorizada.
            </CardDescription>
            {resource === "tenants" ? (
              <p className="mt-2 text-xs text-muted-foreground">
                Los establecimientos se suspenden para conservar la trazabilidad; edita el estado en lugar de eliminarlos.
              </p>
            ) : null}
          </div>
          <div className="flex gap-2">
            <Button onClick={() => void load()} size="sm" variant="outline">
              <RefreshCw aria-hidden="true" size={15} />
              Actualizar
            </Button>
            <Button onClick={startCreate} size="sm">
              <CirclePlus aria-hidden="true" size={15} />
              Nuevo
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
              {error}
            </div>
          ) : loading ? (
            <p className="py-8 text-center text-sm text-muted-foreground" role="status">
              Consultando {resourceLabels[resource].toLocaleLowerCase("es")}…
            </p>
          ) : records.length === 0 ? (
            <EmptyState
              action={
                <Button onClick={startCreate} variant="outline">
                  <CirclePlus aria-hidden="true" size={16} />
                  Crear registro
                </Button>
              }
              description="Todavía no hay registros para mostrar. Puedes crear el primero."
              title="Sin registros"
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  {columns[resource].map((column) => (
                    <TableHead key={column}>{column.replaceAll("_", " ")}</TableHead>
                  ))}
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {records.map((record) => (
                  <TableRow key={recordKey(resource, record)}>
                    {columns[resource].map((column) => (
                      <TableCell className="max-w-64 truncate" key={column}>
                        {column === "is_active" || column === "status" ? (
                          <Badge tone={record[column] === true || record[column] === "active" ? "green" : "slate"}>
                            {getDisplayValue(column, record[column])}
                          </Badge>
                        ) : (
                          <span className={column === "value" ? "font-mono text-xs" : ""}>
                            {getDisplayValue(column, record[column])}
                          </span>
                        )}
                      </TableCell>
                    ))}
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button
                          aria-label={`Editar ${String(record.name ?? record.key ?? record.code ?? "registro")}`}
                          onClick={() => startEdit(record)}
                          size="icon"
                          variant="ghost"
                        >
                          <Pencil aria-hidden="true" size={16} />
                        </Button>
                        {resource !== "tenants" ? (
                          <Button
                            aria-label={`Eliminar ${String(record.name ?? record.key ?? record.code ?? "registro")}`}
                            onClick={() => void remove(record)}
                            size="icon"
                            variant="ghost"
                          >
                            <Trash2 aria-hidden="true" size={16} />
                          </Button>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function AdministrationPanel({
  permissions,
  tenantId,
  onTenantSelect,
  onSiteSelect,
}: {
  permissions: readonly string[];
  tenantId: string | null;
  onTenantSelect: (tenantId: string) => void;
  onSiteSelect: (siteId: string) => void;
}) {
  const isPlatformAdmin = permissions.includes("platform:manage");
  const isTenantAdmin =
    isPlatformAdmin || permissions.includes("tenant:manage");
  const [tenants, setTenants] = useState<AdminRecord[]>([]);

  if (!isPlatformAdmin && !isTenantAdmin) return null;

  return (
    <div className="space-y-10">
      {isPlatformAdmin ? (
        <section aria-labelledby="platform-admin-title" className="mt-8 scroll-mt-24" id="platform-manage">
          <div className="mb-4">
            <p className="text-xs font-bold uppercase tracking-[0.13em] text-teal-700">
              Administración SaaS
            </p>
            <h2 className="mt-1 text-xl font-semibold tracking-tight text-ink" id="platform-admin-title">
              Plataforma
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Gestiona establecimientos y el catálogo global de especialidades.
            </p>
            <a
              className="mt-2 inline-flex text-sm font-semibold text-teal-800 hover:underline"
              href="#tenant-manage"
            >
              Configurar sedes y recursos del establecimiento
            </a>
          </div>
          <ResourceManager
            allowTenantSelection
            onTenantSelect={onTenantSelect}
            onTenantsLoaded={setTenants}
            resources={["tenants", "specialties"]}
            siteId={null}
            tenants={tenants}
            tenantId={tenantId}
          />
        </section>
      ) : null}

      {isTenantAdmin ? (
        <section aria-labelledby="tenant-admin-title" className="mt-8 scroll-mt-24" id="tenant-manage">
          <div className="mb-4">
            <p className="text-xs font-bold uppercase tracking-[0.13em] text-teal-700">
              Administración institucional
            </p>
            <h2 className="mt-1 text-xl font-semibold tracking-tight text-ink" id="tenant-admin-title">
              Configuración del establecimiento
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Administra sedes, especialidades habilitadas, consultorios, horarios y parámetros.
            </p>
          </div>
          <Card className="mb-5">
            <CardContent className="flex items-center gap-3 pt-5 text-sm text-muted-foreground">
              <Building2 aria-hidden="true" className="shrink-0 text-teal-800" size={18} />
              {tenantId
                ? "El establecimiento activo fue validado por el backend."
                : "Verifica primero tu membresía en el selector de establecimiento."}
            </CardContent>
          </Card>
          <ResourceManager
            resources={["sites", "tenant-specialties", "rooms", "hours", "settings"]}
            siteId={null}
            tenantId={tenantId}
          />
          {permissions.includes("users:manage") ? (
            <UserDoctorManager onSiteSelect={onSiteSelect} tenantId={tenantId} />
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
