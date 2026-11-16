"use client";

import {
  Check,
  Clock3,
  ListPlus,
  RefreshCw,
  Search,
  UserRoundCheck,
} from "lucide-react";
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
import { useToast } from "./ui/toast";

type ReceptionAppointment = {
  id: string;
  patient_id: string;
  patient_number: string;
  patient_name: string;
  doctor_id: string;
  doctor_name: string;
  starts_at: string;
  ends_at: string;
  status: string;
  version: number;
  arrival_confirmed_at: string | null;
  checked_in_at: string | null;
  queue_entered_at: string | null;
};

type ReceptionPage = {
  date: string;
  timezone: string;
  items: ReceptionAppointment[];
  total: number;
};

type ReceptionAction = "confirm-arrival" | "check-in" | "send-to-queue";

const statusLabels: Record<string, string> = {
  scheduled: "Programada",
  confirmed: "Confirmada",
  checked_in: "Check-in",
  completed: "Finalizada",
  cancelled: "Cancelada",
  no_show: "No asistió",
};

async function receptionFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend/admin/${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  const body = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    throw new Error(body?.detail ?? `La solicitud falló (${response.status}).`);
  }
  return body as T;
}

function formatTime(value: string, timezone: string) {
  return new Intl.DateTimeFormat("es", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone,
  }).format(new Date(value));
}

function formatTimestamp(value: string | null, timezone: string) {
  if (!value) return "Pendiente";
  return new Intl.DateTimeFormat("es", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: timezone,
  }).format(new Date(value));
}

function statusTone(status: string): "teal" | "slate" | "amber" | "green" {
  if (status === "checked_in") return "green";
  if (status === "cancelled" || status === "no_show") return "slate";
  if (status === "scheduled") return "amber";
  return "teal";
}

export function ReceptionDesk({
  tenantId,
  siteId,
  canManage,
}: {
  tenantId: string | null;
  siteId: string | null;
  canManage: boolean;
}) {
  const { toast } = useToast();
  const [page, setPage] = useState<ReceptionPage | null>(null);
  const [selectedDate, setSelectedDate] = useState("");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [status, setStatus] = useState("");
  const [queue, setQueue] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeActionId, setActiveActionId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const loadReception = useCallback(async () => {
    if (!tenantId || !siteId) {
      setPage(null);
      return;
    }

    const params = new URLSearchParams({ site_id: siteId });
    if (selectedDate) params.set("date", selectedDate);
    if (debouncedSearch) params.set("q", debouncedSearch);
    if (doctorId) params.set("doctor_id", doctorId);
    if (status) params.set("status", status);
    if (queue) params.set("queue", queue);

    setLoading(true);
    setError(null);
    try {
      const result = await receptionFetch<ReceptionPage>(
        `tenants/${tenantId}/operations/reception/appointments?${params.toString()}`,
      );
      setPage(result);
      if (!selectedDate) setSelectedDate(result.date);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "No se pudo cargar la recepción.",
      );
      setPage(null);
    } finally {
      setLoading(false);
    }
  }, [
    debouncedSearch,
    doctorId,
    queue,
    refreshKey,
    selectedDate,
    siteId,
    status,
    tenantId,
  ]);

  useEffect(() => {
    void loadReception();
  }, [loadReception]);

  const doctors = useMemo(() => {
    const values = new Map<string, string>();
    for (const appointment of page?.items ?? []) {
      values.set(appointment.doctor_id, appointment.doctor_name);
    }
    return [...values.entries()].sort((first, second) =>
      first[1].localeCompare(second[1], "es"),
    );
  }, [page?.items]);

  const queueCount = useMemo(
    () => (page?.items ?? []).filter((item) => item.queue_entered_at).length,
    [page?.items],
  );
  const arrivedCount = useMemo(
    () => (page?.items ?? []).filter((item) => item.arrival_confirmed_at).length,
    [page?.items],
  );

  const updateAppointment = async (
    appointment: ReceptionAppointment,
    action: ReceptionAction,
  ) => {
    if (!tenantId || !siteId) return;
    setActiveActionId(appointment.id);
    try {
      await receptionFetch(
        `tenants/${tenantId}/operations/reception/appointments/${appointment.id}/${action}?site_id=${siteId}`,
        {
          method: "POST",
          body: JSON.stringify({ expected_version: appointment.version }),
        },
      );
      const actionLabel =
        action === "confirm-arrival"
          ? "Llegada confirmada"
          : action === "check-in"
            ? "Check-in registrado"
            : "Enviado a la cola";
      toast({
        tone: "success",
        title: actionLabel,
        description: "Se registró la hora de la operación.",
      });
      setRefreshKey((value) => value + 1);
    } catch (actionError) {
      toast({
        tone: "error",
        title: "No se pudo actualizar la recepción",
        description:
          actionError instanceof Error ? actionError.message : "Intenta de nuevo.",
      });
      if (
        actionError instanceof Error &&
        actionError.message.toLocaleLowerCase("es").includes("changed by another request")
      ) {
        setRefreshKey((value) => value + 1);
      }
    } finally {
      setActiveActionId(null);
    }
  };

  if (!tenantId || !siteId) {
    return (
      <Card>
        <EmptyState
          title={!tenantId ? "Selecciona un establecimiento" : "Selecciona una sede"}
          description="La recepción consulta las citas del día en la sede activa."
        />
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
          <div>
            <CardTitle>Ventanilla · recepción del día</CardTitle>
            <CardDescription className="mt-1">
              Identificación administrativa, llegada y flujo a cola. No se muestran datos clínicos.
            </CardDescription>
          </div>
          <Button
            disabled={loading}
            onClick={() => setRefreshKey((value) => value + 1)}
            size="sm"
            variant="outline"
          >
            <RefreshCw aria-hidden="true" size={15} />
            Actualizar
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-xs font-medium">
            Fecha de atención
            <Input
              className="mt-1"
              onChange={(event) => setSelectedDate(event.target.value)}
              type="date"
              value={selectedDate}
            />
          </label>
          <label className="text-xs font-medium">
            Búsqueda rápida
            <span className="relative mt-1 block">
              <Search
                aria-hidden="true"
                className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                size={16}
              />
              <Input
                className="pl-9"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Nombre o número de paciente"
                value={search}
              />
            </span>
          </label>
          <label className="text-xs font-medium">
            Estado de la cita
            <select
              className="mt-1 h-11 w-full rounded-xl border border-input bg-white px-3 text-sm"
              onChange={(event) => setStatus(event.target.value)}
              value={status}
            >
              <option value="">Todos</option>
              {Object.entries(statusLabels).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium">
            Flujo a cola
            <select
              className="mt-1 h-11 w-full rounded-xl border border-input bg-white px-3 text-sm"
              onChange={(event) => setQueue(event.target.value)}
              value={queue}
            >
              <option value="">Todas</option>
              <option value="waiting">Check-in sin enviar</option>
              <option value="sent">Enviadas a cola</option>
            </select>
          </label>
          <label className="text-xs font-medium sm:col-span-2 lg:col-span-4">
            Profesional
            <select
              className="mt-1 h-11 w-full rounded-xl border border-input bg-white px-3 text-sm sm:max-w-sm"
              onChange={(event) => setDoctorId(event.target.value)}
              value={doctorId}
            >
              <option value="">Todos</option>
              {doctors.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </select>
          </label>
        </div>

        {page ? (
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl bg-slate-50 p-3">
              <p className="text-xs text-muted-foreground">Citas en esta vista</p>
              <p className="mt-1 text-xl font-semibold">{page.total}</p>
            </div>
            <div className="rounded-xl bg-teal-50 p-3">
              <p className="text-xs text-teal-800">Llegadas confirmadas</p>
              <p className="mt-1 text-xl font-semibold text-teal-950">{arrivedCount}</p>
            </div>
            <div className="rounded-xl bg-emerald-50 p-3">
              <p className="text-xs text-emerald-800">En cola de atención</p>
              <p className="mt-1 text-xl font-semibold text-emerald-950">{queueCount}</p>
            </div>
          </div>
        ) : null}

        {error ? (
          <p className="rounded-xl bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>
        ) : null}
        {loading ? (
          <p className="text-sm text-muted-foreground" role="status">Cargando citas de recepción…</p>
        ) : null}
        {!loading && page?.items.length === 0 ? (
          <EmptyState
            title="No hay citas para estos filtros"
            description="Prueba con otra fecha, estado, profesional o término de búsqueda."
          />
        ) : null}

        <div className="space-y-3">
          {page?.items.map((appointment) => {
            const busy = activeActionId === appointment.id;
            const canAdvance = canManage && ["scheduled", "confirmed"].includes(appointment.status);
            return (
              <article
                className="rounded-2xl border border-border bg-white p-4"
                key={appointment.id}
              >
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold">{appointment.patient_name}</h3>
                      <Badge tone="slate">N.º {appointment.patient_number}</Badge>
                      <Badge tone={statusTone(appointment.status)}>
                        {statusLabels[appointment.status] ?? appointment.status}
                      </Badge>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {formatTime(appointment.starts_at, page?.timezone ?? "UTC")} · {appointment.doctor_name}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {canAdvance && !appointment.arrival_confirmed_at ? (
                      <Button
                        disabled={busy}
                        onClick={() => void updateAppointment(appointment, "confirm-arrival")}
                        size="sm"
                        variant="outline"
                      >
                        <UserRoundCheck aria-hidden="true" size={15} />
                        Confirmar identidad y llegada
                      </Button>
                    ) : null}
                    {canAdvance && appointment.arrival_confirmed_at && !appointment.checked_in_at ? (
                      <Button
                        disabled={busy}
                        onClick={() => void updateAppointment(appointment, "check-in")}
                        size="sm"
                      >
                        <Check aria-hidden="true" size={15} />
                        Registrar check-in
                      </Button>
                    ) : null}
                    {canManage && appointment.checked_in_at && !appointment.queue_entered_at ? (
                      <Button
                        disabled={busy}
                        onClick={() => void updateAppointment(appointment, "send-to-queue")}
                        size="sm"
                      >
                        <ListPlus aria-hidden="true" size={15} />
                        Enviar a cola
                      </Button>
                    ) : null}
                    {appointment.queue_entered_at ? <Badge tone="green">En cola</Badge> : null}
                  </div>
                </div>
                <dl className="mt-4 grid gap-3 border-t border-border pt-3 text-xs sm:grid-cols-3">
                  <div>
                    <dt className="flex items-center gap-1 font-semibold text-muted-foreground">
                      <Clock3 aria-hidden="true" size={13} /> Llegada
                    </dt>
                    <dd className="mt-1">{formatTimestamp(appointment.arrival_confirmed_at, page?.timezone ?? "UTC")}</dd>
                  </div>
                  <div>
                    <dt className="flex items-center gap-1 font-semibold text-muted-foreground">
                      <Clock3 aria-hidden="true" size={13} /> Check-in
                    </dt>
                    <dd className="mt-1">{formatTimestamp(appointment.checked_in_at, page?.timezone ?? "UTC")}</dd>
                  </div>
                  <div>
                    <dt className="flex items-center gap-1 font-semibold text-muted-foreground">
                      <Clock3 aria-hidden="true" size={13} /> Entrada a cola
                    </dt>
                    <dd className="mt-1">{formatTimestamp(appointment.queue_entered_at, page?.timezone ?? "UTC")}</dd>
                  </div>
                </dl>
              </article>
            );
          })}
        </div>
        {!canManage ? (
          <p className="text-xs text-muted-foreground">
            Acceso de consulta: las acciones de recepción requieren permiso para gestionar citas.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
