"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, CalendarCheck, Stethoscope, Users } from "lucide-react";

import { Badge } from "./ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { EmptyState } from "./ui/empty-state";
import { Input } from "./ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";

type Dashboard = {
  generated_at: string;
  filters: {
    start_date: string;
    end_date: string;
    site_id: string | null;
    specialty_id: string | null;
  };
  sites: Array<{ id: string; code: string; name: string }>;
  specialties: Array<{ id: string; code: string; name: string }>;
  patients_registered: number;
  appointments_by_status: Array<{ status: string; count: number }>;
  available_doctors: number;
  completed_encounters: number;
  productivity: Array<{
    doctor_id: string;
    doctor_name: string;
    completed_encounters: number;
    appointments_total: number;
    completed_appointments: number;
    completion_rate_percent: number;
  }>;
};

const appointmentStatusLabels: Record<string, string> = {
  scheduled: "Programadas",
  confirmed: "Confirmadas",
  checked_in: "En recepción",
  completed: "Completadas",
  cancelled: "Canceladas",
  no_show: "Ausencias",
};

function localDate(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function defaultStartDate() {
  const start = new Date();
  start.setDate(start.getDate() - 29);
  return localDate(start);
}

async function dashboardFetch<T>(path: string): Promise<T> {
  const response = await fetch(`/api/backend/admin/${path}`, {
    cache: "no-store",
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail ?? `La solicitud falló (${response.status}).`);
  }
  return body as T;
}

export function AdminDashboard({
  tenantId,
  activeSiteId,
}: {
  tenantId: string | null;
  activeSiteId: string | null;
}) {
  const [startDate, setStartDate] = useState(defaultStartDate);
  const [endDate, setEndDate] = useState(() => localDate(new Date()));
  const [siteId, setSiteId] = useState(activeSiteId ?? "");
  const [specialtyId, setSpecialtyId] = useState("");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    if (!tenantId) {
      setDashboard(null);
      return;
    }
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
    if (siteId) params.set("site_id", siteId);
    if (specialtyId) params.set("specialty_id", specialtyId);
    try {
      const result = await dashboardFetch<Dashboard>(
        `tenants/${tenantId}/dashboard?${params.toString()}`,
      );
      setDashboard(result);
    } catch (loadError) {
      setDashboard(null);
      setError(
        loadError instanceof Error
          ? loadError.message
          : "No se pudo cargar el dashboard.",
      );
    } finally {
      setLoading(false);
    }
  }, [endDate, siteId, specialtyId, startDate, tenantId]);

  useEffect(() => {
    setSiteId(activeSiteId ?? "");
  }, [activeSiteId, tenantId]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  if (!tenantId) {
    return (
      <Card>
        <EmptyState
          description="Selecciona un establecimiento con permisos de administración."
          title="Establecimiento requerido"
        />
      </Card>
    );
  }

  const kpis = dashboard
    ? [
        {
          title: "Pacientes registrados",
          value: dashboard.patients_registered,
          icon: Users,
        },
        {
          title: "Citas en el período",
          value: dashboard.appointments_by_status.reduce(
            (total, row) => total + row.count,
            0,
          ),
          icon: CalendarCheck,
        },
        {
          title: "Médicos con disponibilidad",
          value: dashboard.available_doctors,
          icon: Stethoscope,
        },
        {
          title: "Atenciones realizadas",
          value: dashboard.completed_encounters,
          icon: Activity,
        },
      ]
    : [];

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Filtros del dashboard</CardTitle>
          <CardDescription>
            Los datos demográficos se cuentan por registro; al filtrar sede o
            especialidad, se incluyen pacientes con cita en ese contexto y período.
            Disponibilidad médica se basa en los horarios configurados para los días
            del período. Las fechas se interpretan en UTC.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-4">
            <label className="space-y-1 text-sm font-medium">
              Desde
              <Input
                onChange={(event) => setStartDate(event.target.value)}
                type="date"
                value={startDate}
              />
            </label>
            <label className="space-y-1 text-sm font-medium">
              Hasta
              <Input
                onChange={(event) => setEndDate(event.target.value)}
                type="date"
                value={endDate}
              />
            </label>
            <label className="space-y-1 text-sm font-medium">
              Sede
              <select
                className="h-11 w-full rounded-xl border border-input bg-white px-3 text-sm"
                onChange={(event) => setSiteId(event.target.value)}
                value={siteId}
              >
                <option value="">Todas las sedes</option>
                {dashboard?.sites.map((site) => (
                  <option key={site.id} value={site.id}>
                    {site.name} ({site.code})
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm font-medium">
              Especialidad
              <select
                className="h-11 w-full rounded-xl border border-input bg-white px-3 text-sm"
                onChange={(event) => setSpecialtyId(event.target.value)}
                value={specialtyId}
              >
                <option value="">Todas las especialidades</option>
                {dashboard?.specialties.map((specialty) => (
                  <option key={specialty.id} value={specialty.id}>
                    {specialty.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {error ? (
            <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">
              {error}
            </p>
          ) : null}
          {loading ? (
            <p className="mt-4 text-sm text-muted-foreground" role="status">
              Actualizando indicadores…
            </p>
          ) : null}
        </CardContent>
      </Card>

      {dashboard ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {kpis.map(({ title, value, icon: Icon }) => (
              <Card key={title}>
                <CardContent className="flex items-center justify-between gap-4 pt-5">
                  <div>
                    <p className="text-sm text-muted-foreground">{title}</p>
                    <p className="mt-2 text-3xl font-semibold tracking-tight text-ink">
                      {value.toLocaleString("es")}
                    </p>
                  </div>
                  <span className="rounded-xl bg-teal-50 p-3 text-teal-800">
                    <Icon aria-hidden="true" size={22} />
                  </span>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Citas por estado</CardTitle>
                <CardDescription>Estados registrados dentro del período seleccionado.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {dashboard.appointments_by_status.map((row) => (
                  <div
                    className="flex items-center justify-between gap-3"
                    key={row.status}
                  >
                    <Badge tone={row.status === "completed" ? "green" : "slate"}>
                      {appointmentStatusLabels[row.status] ?? row.status}
                    </Badge>
                    <span className="font-semibold tabular-nums">
                      {row.count.toLocaleString("es")}
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Productividad por médico</CardTitle>
                <CardDescription>
                  Atenciones completadas y porcentaje de citas completadas entre las
                  citas no canceladas ni ausentes.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {dashboard.productivity.length ? (
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Médico</TableHead>
                          <TableHead>Atenciones</TableHead>
                          <TableHead>Citas</TableHead>
                          <TableHead>Completadas</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {dashboard.productivity.map((row) => (
                          <TableRow key={row.doctor_id}>
                            <TableCell>{row.doctor_name}</TableCell>
                            <TableCell>{row.completed_encounters}</TableCell>
                            <TableCell>{row.appointments_total}</TableCell>
                            <TableCell>{row.completion_rate_percent}%</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                ) : (
                  <EmptyState
                    description="No hay citas ni atenciones para los filtros seleccionados."
                    title="Sin actividad"
                  />
                )}
              </CardContent>
            </Card>
          </div>
          <p className="text-right text-xs text-muted-foreground">
            Actualizado {new Date(dashboard.generated_at).toLocaleString("es")}
          </p>
        </>
      ) : null}
    </div>
  );
}
