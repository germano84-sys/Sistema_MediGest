"use client";

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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table";
import { useToast } from "./ui/toast";

type Site = { id: string; name: string };
type Specialty = { specialty_id: string; code: string; name: string; is_active: boolean };
type ManagedRole = { code: string; name: string };
type ManagedUser = {
  membership_id: string;
  user_id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  membership_status: "active" | "suspended";
  role_codes: string[];
};
type Doctor = {
  id: string;
  membership_id: string;
  email: string;
  display_name: string;
  license_number: string;
  is_active: boolean;
  specialty_ids: string[];
  primary_specialty_id: string;
};
type Availability = {
  id: string;
  doctor_id: string;
  site_id: string;
  weekday: number;
  starts_at: string;
  ends_at: string;
  is_available: boolean;
};
type Page<T> = { items: T[]; total: number; limit: number; offset: number };

const WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const PAGE_SIZE = 25;

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

function pageCount(total: number) {
  return Math.max(1, Math.ceil(total / PAGE_SIZE));
}

export function UserDoctorManager({
  tenantId,
  onSiteSelect,
}: {
  tenantId: string | null;
  onSiteSelect: (siteId: string) => void;
}) {
  const { toast } = useToast();
  const [sites, setSites] = useState<Site[]>([]);
  const [siteId, setSiteId] = useState("");
  const [roles, setRoles] = useState<ManagedRole[]>([]);
  const [specialties, setSpecialties] = useState<Specialty[]>([]);
  const [users, setUsers] = useState<Page<ManagedUser>>({
    items: [],
    total: 0,
    limit: PAGE_SIZE,
    offset: 0,
  });
  const [doctors, setDoctors] = useState<Page<Doctor>>({
    items: [],
    total: 0,
    limit: PAGE_SIZE,
    offset: 0,
  });
  const [availability, setAvailability] = useState<Availability[]>([]);
  const [selectedDoctor, setSelectedDoctor] = useState("");
  const [search, setSearch] = useState("");
  const [doctorSearch, setDoctorSearch] = useState("");
  const [userOffset, setUserOffset] = useState(0);
  const [doctorOffset, setDoctorOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invite, setInvite] = useState({ email: "", display_name: "", role_codes: [] as string[] });
  const [doctorInvite, setDoctorInvite] = useState({
    membership_id: "",
    license_number: "",
    specialty_ids: [] as string[],
  });
  const [specialtyEdit, setSpecialtyEdit] = useState<{
    doctorId: string;
    specialtyIds: string[];
    primarySpecialtyId: string;
  } | null>(null);
  const [schedule, setSchedule] = useState({
    weekday: "0",
    starts_at: "08:00",
    ends_at: "17:00",
  });

  const basePath = tenantId ? `/tenants/${tenantId}` : null;
  const activeSpecialties = useMemo(
    () => specialties.filter((specialty) => specialty.is_active),
    [specialties],
  );

  useEffect(() => {
    let active = true;
    if (!basePath) {
      setSites([]);
      setRoles([]);
      setSpecialties([]);
      setSiteId("");
      return;
    }
    setError(null);
    Promise.all([
      adminFetch<Site[]>(`${basePath}/sites`),
      adminFetch<ManagedRole[]>(`${basePath}/managed-roles`),
      adminFetch<Specialty[]>(`${basePath}/specialties`),
    ])
      .then(([loadedSites, loadedRoles, loadedSpecialties]) => {
        if (!active) return;
        setSites(loadedSites);
        setRoles(loadedRoles);
        setSpecialties(loadedSpecialties);
        setSiteId((current) =>
          loadedSites.some((site) => site.id === current)
            ? current
            : loadedSites[0]?.id ?? "",
        );
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(cause instanceof Error ? cause.message : "No se pudo cargar la configuración.");
        }
      });
    return () => {
      active = false;
    };
  }, [basePath]);

  const loadUsers = useCallback(async () => {
    if (!basePath || !siteId) {
      setUsers({ items: [], total: 0, limit: PAGE_SIZE, offset: 0 });
      return;
    }
    const params = new URLSearchParams({
      site_id: siteId,
      limit: String(PAGE_SIZE),
      offset: String(userOffset),
    });
    if (search.trim()) params.set("q", search.trim());
    const result = await adminFetch<Page<ManagedUser>>(
      `${basePath}/users?${params.toString()}`,
    );
    setUsers(result);
  }, [basePath, search, siteId, userOffset]);

  const loadDoctors = useCallback(async () => {
    if (!basePath) {
      setDoctors({ items: [], total: 0, limit: PAGE_SIZE, offset: 0 });
      return;
    }
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(doctorOffset),
    });
    if (doctorSearch.trim()) params.set("q", doctorSearch.trim());
    const result = await adminFetch<Page<Doctor>>(
      `${basePath}/doctors?${params.toString()}`,
    );
    setDoctors(result);
    setSelectedDoctor((current) =>
      result.items.some((doctor) => doctor.id === current)
        ? current
        : result.items[0]?.id ?? "",
    );
  }, [basePath, doctorOffset, doctorSearch]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([loadUsers(), loadDoctors()])
      .catch((cause: unknown) => {
        if (active) {
          setError(cause instanceof Error ? cause.message : "No se pudieron cargar los registros.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [loadDoctors, loadUsers]);

  useEffect(() => {
    let active = true;
    if (!basePath || !selectedDoctor || !siteId) {
      setAvailability([]);
      return;
    }
    const params = new URLSearchParams({ site_id: siteId });
    adminFetch<Availability[]>(
      `${basePath}/doctors/${selectedDoctor}/availability?${params.toString()}`,
    )
      .then((result) => {
        if (active) setAvailability(result);
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(cause instanceof Error ? cause.message : "No se pudo consultar la disponibilidad.");
        }
      });
    return () => {
      active = false;
    };
  }, [basePath, selectedDoctor, siteId]);

  async function runAction(action: () => Promise<void>, successMessage: string) {
    setSaving(true);
    setError(null);
    try {
      await action();
      toast({ tone: "success", title: successMessage });
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "La operación no se pudo completar.";
      setError(message);
      toast({ tone: "error", title: "No se pudo guardar", description: message });
    } finally {
      setSaving(false);
    }
  }

  async function inviteUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!basePath || !siteId) return;
    await runAction(async () => {
      await adminFetch(`${basePath}/users`, "POST", {
        ...invite,
        site_id: siteId,
      });
      setInvite({ email: "", display_name: "", role_codes: [] });
      await loadUsers();
    }, "Invitación enviada");
  }

  async function updateUserStatus(user: ManagedUser) {
    if (!basePath) return;
    await runAction(async () => {
      await adminFetch(
        `${basePath}/users/${user.membership_id}/status`,
        "PATCH",
        { status: user.membership_status === "active" ? "suspended" : "active" },
      );
      await loadUsers();
    }, "Estado actualizado");
  }

  async function updateRoles(user: ManagedUser, roleCodes: string[]) {
    if (!basePath || !siteId) return;
    await runAction(async () => {
      await adminFetch(
        `${basePath}/users/${user.membership_id}/sites/${siteId}/roles`,
        "PUT",
        { role_codes: roleCodes },
      );
      await loadUsers();
    }, "Roles actualizados");
  }

  async function createDoctor(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!basePath || !siteId) return;
    await runAction(async () => {
      await adminFetch(`${basePath}/doctors`, "POST", {
        ...doctorInvite,
        site_id: siteId,
      });
      setDoctorInvite({ membership_id: "", license_number: "", specialty_ids: [] });
      await loadDoctors();
    }, "Perfil médico creado");
  }

  async function toggleDoctor(doctor: Doctor) {
    if (!basePath) return;
    await runAction(async () => {
      await adminFetch(`${basePath}/doctors/${doctor.id}`, "PATCH", {
        is_active: !doctor.is_active,
      });
      await loadDoctors();
    }, "Estado médico actualizado");
  }

  async function saveDoctorSpecialties(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!basePath || !specialtyEdit) return;
    await runAction(async () => {
      await adminFetch(
        `${basePath}/doctors/${specialtyEdit.doctorId}/specialties`,
        "PUT",
        {
          specialty_ids: specialtyEdit.specialtyIds,
          primary_specialty_id: specialtyEdit.primarySpecialtyId,
        },
      );
      setSpecialtyEdit(null);
      await loadDoctors();
    }, "Especialidades actualizadas");
  }

  async function createAvailability(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!basePath || !siteId || !selectedDoctor) return;
    await runAction(async () => {
      await adminFetch(
        `${basePath}/doctors/${selectedDoctor}/availability`,
        "POST",
        {
          site_id: siteId,
          weekday: Number(schedule.weekday),
          starts_at: schedule.starts_at,
          ends_at: schedule.ends_at,
        },
      );
      const params = new URLSearchParams({ site_id: siteId });
      setAvailability(
        await adminFetch<Availability[]>(
          `${basePath}/doctors/${selectedDoctor}/availability?${params.toString()}`,
        ),
      );
    }, "Disponibilidad guardada");
  }

  async function deleteAvailability(item: Availability) {
    if (!basePath || !selectedDoctor) return;
    await runAction(async () => {
      await adminFetch(
        `${basePath}/doctors/${selectedDoctor}/availability/${item.id}`,
        "DELETE",
      );
      setAvailability((current) => current.filter((value) => value.id !== item.id));
    }, "Disponibilidad eliminada");
  }

  async function toggleAvailability(item: Availability) {
    if (!basePath || !selectedDoctor) return;
    await runAction(async () => {
      const updated = await adminFetch<Availability>(
        `${basePath}/doctors/${selectedDoctor}/availability/${item.id}`,
        "PATCH",
        { is_available: !item.is_available },
      );
      setAvailability((current) =>
        current.map((value) => value.id === updated.id ? updated : value),
      );
    }, "Disponibilidad actualizada");
  }

  if (!tenantId) {
    return (
      <Card className="mt-6">
        <CardContent className="pt-5 text-sm text-muted-foreground">
          Selecciona un establecimiento para administrar usuarios y médicos.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="mt-6 space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Usuarios y médicos</CardTitle>
          <CardDescription>
            Las invitaciones se envían mediante Keycloak. Las contraseñas no se almacenan en MediGest.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="block text-sm font-medium" htmlFor="managed-site">
            Sede de trabajo
            <select
              className="mt-2 h-10 w-full rounded-xl border border-input bg-white px-3 text-sm sm:max-w-md"
              id="managed-site"
              onChange={(event) => {
                setSiteId(event.target.value);
                setUserOffset(0);
                onSiteSelect(event.target.value);
              }}
              value={siteId}
            >
              {sites.map((site) => (
                <option key={site.id} value={site.id}>{site.name}</option>
              ))}
            </select>
          </label>
          {error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
              {error}
            </div>
          ) : null}
          {!sites.length ? (
            <EmptyState title="Sin sedes activas" description="Crea o activa una sede antes de administrar usuarios." />
          ) : (
            <form className="grid gap-3 rounded-xl border border-border p-4 md:grid-cols-2" onSubmit={(event) => void inviteUser(event)}>
              <h3 className="text-sm font-semibold md:col-span-2">Invitar usuario</h3>
              <Input
                autoComplete="name"
                aria-label="Nombre completo"
                onChange={(event) => setInvite((current) => ({ ...current, display_name: event.target.value }))}
                placeholder="Nombre completo"
                required
                value={invite.display_name}
              />
              <Input
                autoComplete="email"
                aria-label="Correo electrónico"
                onChange={(event) => setInvite((current) => ({ ...current, email: event.target.value }))}
                placeholder="correo@ejemplo.com"
                required
                type="email"
                value={invite.email}
              />
              <fieldset className="flex flex-wrap gap-x-5 gap-y-2 md:col-span-2">
                <legend className="mb-2 text-sm font-medium">Roles para esta sede</legend>
                {roles.map((role) => (
                  <label className="flex items-center gap-2 text-sm" key={role.code}>
                    <input
                      checked={invite.role_codes.includes(role.code)}
                      onChange={(event) =>
                        setInvite((current) => ({
                          ...current,
                          role_codes: event.target.checked
                            ? [...current.role_codes, role.code]
                            : current.role_codes.filter((code) => code !== role.code),
                        }))
                      }
                      type="checkbox"
                    />
                    {role.name}
                  </label>
                ))}
              </fieldset>
              <div className="md:col-span-2">
                <Button disabled={saving || !invite.role_codes.length} type="submit">
                  Enviar invitación
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Usuarios del establecimiento</CardTitle>
          <CardDescription>Filtra, pagina y asigna roles operativos por sede.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Input
              aria-label="Buscar usuarios"
              className="max-w-sm"
              onChange={(event) => {
                setSearch(event.target.value);
                setUserOffset(0);
              }}
              placeholder="Buscar por nombre o correo"
              value={search}
            />
            <Button disabled={loading} onClick={() => void loadUsers()} variant="outline">Buscar</Button>
          </div>
          {users.items.length ? (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Usuario</TableHead>
                    <TableHead>Roles en la sede</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead className="text-right">Acciones</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.items.map((user) => (
                    <TableRow key={user.membership_id}>
                      <TableCell>
                        <div className="font-medium">{user.display_name}</div>
                        <div className="text-xs text-muted-foreground">{user.email}</div>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-2">
                          {roles.map((role) => (
                            <label className="flex items-center gap-1 text-xs" key={role.code}>
                              <input
                                aria-label={`${role.name} para ${user.display_name}`}
                                checked={user.role_codes.includes(role.code)}
                                onChange={(event) => {
                                  const next = event.target.checked
                                    ? [...user.role_codes, role.code]
                                    : user.role_codes.filter((code) => code !== role.code);
                                  void updateRoles(user, next);
                                }}
                                type="checkbox"
                              />
                              {role.name}
                            </label>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge tone={user.membership_status === "active" ? "green" : "slate"}>
                          {user.membership_status === "active" ? "Activo" : "Suspendido"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button disabled={saving} onClick={() => void updateUserStatus(user)} size="sm" variant="outline">
                          {user.membership_status === "active" ? "Suspender" : "Reactivar"}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="flex items-center justify-between text-sm">
                <span>Página {Math.floor(users.offset / PAGE_SIZE) + 1} de {pageCount(users.total)} · {users.total} usuarios</span>
                <div className="flex gap-2">
                  <Button disabled={!users.offset || loading} onClick={() => setUserOffset(Math.max(0, userOffset - PAGE_SIZE))} size="sm" variant="outline">Anterior</Button>
                  <Button disabled={users.offset + PAGE_SIZE >= users.total || loading} onClick={() => setUserOffset(userOffset + PAGE_SIZE)} size="sm" variant="outline">Siguiente</Button>
                </div>
              </div>
            </>
          ) : (
            <EmptyState title="Sin usuarios" description="No hay usuarios que coincidan con el filtro en esta sede." />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Perfiles médicos</CardTitle>
          <CardDescription>Asocia usuarios con rol médico a especialidades habilitadas para el establecimiento.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="grid gap-3 rounded-xl border border-border p-4 md:grid-cols-2" onSubmit={(event) => void createDoctor(event)}>
            <h3 className="text-sm font-semibold md:col-span-2">Crear perfil médico</h3>
            <label className="text-sm">
              Usuario con rol médico
              <select
                className="mt-2 h-10 w-full rounded-xl border border-input bg-white px-3"
                onChange={(event) => setDoctorInvite((current) => ({ ...current, membership_id: event.target.value }))}
                required
                value={doctorInvite.membership_id}
              >
                <option value="">Selecciona un usuario</option>
                {users.items.filter((user) => user.membership_status === "active").map((user) => (
                  <option key={user.membership_id} value={user.membership_id}>{user.display_name} · {user.email}</option>
                ))}
              </select>
            </label>
            <Input
              aria-label="Número de registro profesional"
              onChange={(event) => setDoctorInvite((current) => ({ ...current, license_number: event.target.value }))}
              placeholder="Registro profesional"
              required
              value={doctorInvite.license_number}
            />
            <fieldset className="flex flex-wrap gap-x-5 gap-y-2 md:col-span-2">
              <legend className="mb-2 text-sm font-medium">Especialidades</legend>
              {activeSpecialties.map((specialty) => (
                <label className="flex items-center gap-2 text-sm" key={specialty.specialty_id}>
                  <input
                    checked={doctorInvite.specialty_ids.includes(specialty.specialty_id)}
                    onChange={(event) =>
                      setDoctorInvite((current) => ({
                        ...current,
                        specialty_ids: event.target.checked
                          ? [...current.specialty_ids, specialty.specialty_id]
                          : current.specialty_ids.filter((id) => id !== specialty.specialty_id),
                      }))
                    }
                    type="checkbox"
                  />
                  {specialty.name}
                </label>
              ))}
            </fieldset>
            <div className="md:col-span-2">
              <Button disabled={saving || !doctorInvite.specialty_ids.length} type="submit">Crear perfil</Button>
            </div>
          </form>
          <div className="flex flex-wrap gap-2">
            <Input
              aria-label="Buscar médicos"
              className="max-w-sm"
              onChange={(event) => {
                setDoctorSearch(event.target.value);
                setDoctorOffset(0);
              }}
              placeholder="Buscar por nombre, correo o registro"
              value={doctorSearch}
            />
            <Button disabled={loading} onClick={() => void loadDoctors()} variant="outline">Buscar</Button>
          </div>
          {doctors.items.length ? (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Médico</TableHead>
                    <TableHead>Registro</TableHead>
                    <TableHead>Especialidades</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead className="text-right">Acción</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {doctors.items.map((doctor) => (
                    <TableRow key={doctor.id}>
                      <TableCell>
                        <div className="font-medium">{doctor.display_name}</div>
                        <div className="text-xs text-muted-foreground">{doctor.email}</div>
                      </TableCell>
                      <TableCell>{doctor.license_number}</TableCell>
                      <TableCell>
                        {doctor.specialty_ids
                          .map((id) => activeSpecialties.find((specialty) => specialty.specialty_id === id)?.name ?? "Especialidad")
                          .join(", ")}
                      </TableCell>
                      <TableCell>
                        <Badge tone={doctor.is_active ? "green" : "slate"}>{doctor.is_active ? "Activo" : "Inactivo"}</Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button
                            onClick={() => setSpecialtyEdit({
                              doctorId: doctor.id,
                              specialtyIds: doctor.specialty_ids,
                              primarySpecialtyId: doctor.primary_specialty_id,
                            })}
                            size="sm"
                            variant="outline"
                          >
                            Especialidades
                          </Button>
                          <Button disabled={saving} onClick={() => void toggleDoctor(doctor)} size="sm" variant="outline">
                            {doctor.is_active ? "Desactivar" : "Activar"}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="flex items-center justify-between text-sm">
                <span>Página {Math.floor(doctors.offset / PAGE_SIZE) + 1} de {pageCount(doctors.total)} · {doctors.total} médicos</span>
                <div className="flex gap-2">
                  <Button disabled={!doctors.offset || loading} onClick={() => setDoctorOffset(Math.max(0, doctorOffset - PAGE_SIZE))} size="sm" variant="outline">Anterior</Button>
                  <Button disabled={doctors.offset + PAGE_SIZE >= doctors.total || loading} onClick={() => setDoctorOffset(doctorOffset + PAGE_SIZE)} size="sm" variant="outline">Siguiente</Button>
                </div>
              </div>
            </>
          ) : (
            <EmptyState title="Sin perfiles médicos" description="Crea un perfil para una membresía activa con rol médico." />
          )}
          {specialtyEdit ? (
            <form className="space-y-3 rounded-xl border border-border p-4" onSubmit={(event) => void saveDoctorSpecialties(event)}>
              <h3 className="text-sm font-semibold">Editar especialidades</h3>
              <fieldset className="flex flex-wrap gap-x-5 gap-y-2">
                <legend className="mb-2 text-sm font-medium">Asociaciones</legend>
                {activeSpecialties.map((specialty) => (
                  <label className="flex items-center gap-2 text-sm" key={specialty.specialty_id}>
                    <input
                      checked={specialtyEdit.specialtyIds.includes(specialty.specialty_id)}
                      onChange={(event) => {
                        const nextIds = event.target.checked
                          ? [...specialtyEdit.specialtyIds, specialty.specialty_id]
                          : specialtyEdit.specialtyIds.filter((id) => id !== specialty.specialty_id);
                        setSpecialtyEdit({
                          ...specialtyEdit,
                          specialtyIds: nextIds,
                          primarySpecialtyId: nextIds.includes(specialtyEdit.primarySpecialtyId)
                            ? specialtyEdit.primarySpecialtyId
                            : nextIds[0] ?? "",
                        });
                      }}
                      type="checkbox"
                    />
                    {specialty.name}
                  </label>
                ))}
              </fieldset>
              <label className="block max-w-md text-sm">
                Especialidad principal
                <select
                  className="mt-2 h-10 w-full rounded-xl border border-input bg-white px-3"
                  onChange={(event) => setSpecialtyEdit({ ...specialtyEdit, primarySpecialtyId: event.target.value })}
                  required
                  value={specialtyEdit.primarySpecialtyId}
                >
                  {specialtyEdit.specialtyIds.map((id) => {
                    const specialty = activeSpecialties.find((item) => item.specialty_id === id);
                    return <option key={id} value={id}>{specialty?.name ?? id}</option>;
                  })}
                </select>
              </label>
              <div className="flex gap-2">
                <Button disabled={saving || !specialtyEdit.specialtyIds.length} type="submit">Guardar especialidades</Button>
                <Button onClick={() => setSpecialtyEdit(null)} type="button" variant="outline">Cancelar</Button>
              </div>
            </form>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Disponibilidad semanal</CardTitle>
          <CardDescription>Configura intervalos sin cruces dentro de la sede seleccionada.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="block max-w-lg text-sm">
            Médico
            <select
              className="mt-2 h-10 w-full rounded-xl border border-input bg-white px-3"
              onChange={(event) => setSelectedDoctor(event.target.value)}
              value={selectedDoctor}
            >
              {doctors.items.map((doctor) => (
                <option key={doctor.id} value={doctor.id}>{doctor.display_name} · {doctor.license_number}</option>
              ))}
            </select>
          </label>
          <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" onSubmit={(event) => void createAvailability(event)}>
            <label className="text-sm">
              Día
              <select
                className="mt-2 h-10 w-full rounded-xl border border-input bg-white px-3"
                onChange={(event) => setSchedule((current) => ({ ...current, weekday: event.target.value }))}
                value={schedule.weekday}
              >
                {WEEKDAYS.map((day, index) => <option key={day} value={index}>{day}</option>)}
              </select>
            </label>
            <Input aria-label="Hora de inicio" onChange={(event) => setSchedule((current) => ({ ...current, starts_at: event.target.value }))} required type="time" value={schedule.starts_at} />
            <Input aria-label="Hora de fin" onChange={(event) => setSchedule((current) => ({ ...current, ends_at: event.target.value }))} required type="time" value={schedule.ends_at} />
            <div className="flex items-end">
              <Button disabled={saving || !selectedDoctor} type="submit">Agregar horario</Button>
            </div>
          </form>
          {availability.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Día</TableHead>
                  <TableHead>Inicio</TableHead>
                  <TableHead>Fin</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Acción</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {availability.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{WEEKDAYS[item.weekday]}</TableCell>
                    <TableCell>{item.starts_at.slice(0, 5)}</TableCell>
                    <TableCell>{item.ends_at.slice(0, 5)}</TableCell>
                    <TableCell>{item.is_available ? "Disponible" : "No disponible"}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button disabled={saving} onClick={() => void toggleAvailability(item)} size="sm" variant="outline">
                          {item.is_available ? "Marcar no disponible" : "Marcar disponible"}
                        </Button>
                        <Button disabled={saving} onClick={() => void deleteAvailability(item)} size="sm" variant="outline">Eliminar</Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <EmptyState title="Sin disponibilidad configurada" description="Agrega el primer intervalo semanal para este médico y sede." />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
