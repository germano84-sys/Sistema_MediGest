"use client";

import { Check, Clock3, DoorOpen, Play, RefreshCw } from "lucide-react";
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

type ServiceStatus = "pending" | "preparing" | "ready" | "completed";
type ServiceAction =
  | "assign-room"
  | "start-preparation"
  | "mark-ready"
  | "start-attention"
  | "finish";

type Room = {
  id: string;
  code: string;
  name: string;
};

type ServiceQueueItem = {
  appointment_id: string;
  patient_name: string;
  doctor_name: string | null;
  appointment_starts_at: string;
  queue_entered_at: string;
  service_status: ServiceStatus;
  version: number;
  room_id: string | null;
  room_code: string | null;
  room_name: string | null;
  preparation_started_at: string | null;
  ready_at: string | null;
  attention_started_at: string | null;
  attention_completed_at: string | null;
};

type ServiceQueuePage = {
  date: string;
  timezone: string;
  items: ServiceQueueItem[];
  rooms: Room[];
  total: number;
};

const statusLabels: Record<ServiceStatus, string> = {
  pending: "Pendiente",
  preparing: "En preparación",
  ready: "Listo",
  completed: "Finalizado",
};

async function serviceFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend/admin/${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail ?? `La solicitud falló (${response.status}).`);
  }
  return body as T;
}

function formatTime(value: string | null, timezone: string) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("es", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: timezone,
  }).format(new Date(value));
}

function elapsedMinutes(start: string | null, end: string | null, now: number) {
  if (!start) return "—";
  const minutes = Math.max(
    0,
    Math.floor(((end ? new Date(end).getTime() : now) - new Date(start).getTime()) / 60_000),
  );
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

function statusTone(status: ServiceStatus): "teal" | "slate" | "amber" | "green" {
  if (status === "pending") return "amber";
  if (status === "completed") return "slate";
  if (status === "ready") return "green";
  return "teal";
}

export function ServiceQueuePanel({
  tenantId,
  siteId,
}: {
  tenantId: string | null;
  siteId: string | null;
}) {
  const { toast } = useToast();
  const [page, setPage] = useState<ServiceQueuePage | null>(null);
  const [selectedDate, setSelectedDate] = useState("");
  const [status, setStatus] = useState("");
  const [roomId, setRoomId] = useState("");
  const [selectedRooms, setSelectedRooms] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const loadQueue = useCallback(async () => {
    if (!tenantId || !siteId) {
      setPage(null);
      return;
    }

    const params = new URLSearchParams({ site_id: siteId });
    if (selectedDate) params.set("date", selectedDate);
    if (status) params.set("status", status);
    if (roomId) params.set("room_id", roomId);

    setLoading(true);
    setError(null);
    try {
      const result = await serviceFetch<ServiceQueuePage>(
        `tenants/${tenantId}/operations/service/queue?${params.toString()}`,
      );
      setPage(result);
      setSelectedRooms(
        Object.fromEntries(
          result.items.map((item) => [item.appointment_id, item.room_id ?? ""]),
        ),
      );
      if (!selectedDate) setSelectedDate(result.date);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "No se pudo cargar la cola del Servicio.",
      );
      setPage(null);
    } finally {
      setLoading(false);
    }
  }, [refreshKey, roomId, selectedDate, siteId, status, tenantId]);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);

  const counts = useMemo(() => {
    const result: Record<ServiceStatus, number> = {
      pending: 0,
      preparing: 0,
      ready: 0,
      completed: 0,
    };
    for (const item of page?.items ?? []) result[item.service_status] += 1;
    return result;
  }, [page?.items]);

  const runAction = async (
    item: ServiceQueueItem,
    action: ServiceAction,
    assignedRoomId?: string,
  ) => {
    if (!tenantId || !siteId) return;
    setSavingId(item.appointment_id);
    try {
      await serviceFetch(
        `tenants/${tenantId}/operations/service/queue/${item.appointment_id}?site_id=${siteId}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            action,
            expected_version: item.version,
            ...(action === "assign-room" ? { room_id: assignedRoomId } : {}),
          }),
        },
      );
      toast({
        tone: "success",
        title:
          action === "assign-room"
            ? "Sala asignada"
            : action === "start-preparation"
              ? "Preparación iniciada"
              : action === "mark-ready"
                ? "Consulta lista"
                : action === "start-attention"
                  ? "Atención iniciada"
                  : "Atención finalizada",
        description: "Se registró el cambio y su hora.",
      });
      setRefreshKey((value) => value + 1);
    } catch (actionError) {
      toast({
        tone: "error",
        title: "No se pudo actualizar la cola",
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
      setSavingId(null);
    }
  };

  if (!tenantId || !siteId) {
    return (
      <Card>
        <EmptyState
          title={!tenantId ? "Selecciona un establecimiento" : "Selecciona una sede"}
          description="La cola del Servicio requiere una sede activa."
        />
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
          <div>
            <CardTitle>Cola operativa del Servicio</CardTitle>
            <CardDescription className="mt-1">
              Solo identificación básica, turno, profesional, sala y tiempos operativos. Sin notas clínicas, diagnósticos ni recetas.
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
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-xs font-medium">
            Fecha de cola
            <Input
              className="mt-1"
              onChange={(event) => setSelectedDate(event.target.value)}
              type="date"
              value={selectedDate}
            />
          </label>
          <label className="text-xs font-medium">
            Estado
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
            Sala
            <select
              className="mt-1 h-11 w-full rounded-xl border border-input bg-white px-3 text-sm"
              onChange={(event) => setRoomId(event.target.value)}
              value={roomId}
            >
              <option value="">Todas</option>
              {(page?.rooms ?? []).map((room) => (
                <option key={room.id} value={room.id}>{room.code} · {room.name}</option>
              ))}
            </select>
          </label>
        </div>

        {page ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {(Object.keys(statusLabels) as ServiceStatus[]).map((value) => (
              <div className="rounded-xl bg-slate-50 p-3" key={value}>
                <p className="text-xs text-muted-foreground">{statusLabels[value]}</p>
                <p className="mt-1 text-xl font-semibold">{counts[value]}</p>
              </div>
            ))}
          </div>
        ) : null}

        {error ? (
          <p className="rounded-xl bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>
        ) : null}
        {loading ? (
          <p className="text-sm text-muted-foreground" role="status">Cargando cola del Servicio…</p>
        ) : null}
        {!loading && page?.items.length === 0 ? (
          <EmptyState
            title="No hay turnos con estos filtros"
            description="Las citas aparecen después de que Ventanilla las envía a la cola."
          />
        ) : null}

        <div className="space-y-3">
          {page?.items.map((item) => {
            const busy = savingId === item.appointment_id;
            const canAssignRoom =
              item.service_status !== "completed" && !item.attention_started_at;
            const selectedRoom = selectedRooms[item.appointment_id] ?? item.room_id ?? "";
            return (
              <article
                className="rounded-2xl border border-border bg-white p-4"
                key={item.appointment_id}
              >
                <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-start">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold">{item.patient_name}</h3>
                      <Badge tone={statusTone(item.service_status)}>
                        {statusLabels[item.service_status]}
                      </Badge>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Turno {formatTime(item.appointment_starts_at, page?.timezone ?? "UTC")}
                      {item.doctor_name ? ` · ${item.doctor_name}` : ""}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {item.room_code && item.room_name
                        ? `Sala ${item.room_code} · ${item.room_name}`
                        : "Sin sala asignada"}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-end gap-2">
                    {canAssignRoom ? (
                      <>
                        <label className="min-w-48 text-xs font-medium">
                          Sala
                          <select
                            className="mt-1 h-10 w-full rounded-xl border border-input bg-white px-3 text-sm"
                            onChange={(event) =>
                              setSelectedRooms((current) => ({
                                ...current,
                                [item.appointment_id]: event.target.value,
                              }))
                            }
                            value={selectedRoom}
                          >
                            <option value="">Selecciona sala</option>
                            {(page?.rooms ?? []).map((room) => (
                              <option key={room.id} value={room.id}>
                                {room.code} · {room.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <Button
                          disabled={savingId !== null || !selectedRoom}
                          onClick={() => void runAction(item, "assign-room", selectedRoom)}
                          size="sm"
                          variant="outline"
                        >
                          <DoorOpen aria-hidden="true" size={15} />
                          Asignar sala
                        </Button>
                      </>
                    ) : null}
                    {item.service_status === "pending" ? (
                      <Button
                        disabled={savingId !== null || !item.room_id}
                        onClick={() => void runAction(item, "start-preparation")}
                        size="sm"
                      >
                        <Play aria-hidden="true" size={15} />
                        Iniciar preparación
                      </Button>
                    ) : null}
                    {item.service_status === "preparing" ? (
                      <Button
                        disabled={savingId !== null}
                        onClick={() => void runAction(item, "mark-ready")}
                        size="sm"
                      >
                        <Check aria-hidden="true" size={15} />
                        Marcar listo
                      </Button>
                    ) : null}
                    {item.service_status === "ready" && !item.attention_started_at ? (
                      <Button
                        disabled={savingId !== null}
                        onClick={() => void runAction(item, "start-attention")}
                        size="sm"
                      >
                        <Play aria-hidden="true" size={15} />
                        Iniciar atención
                      </Button>
                    ) : null}
                    {item.service_status === "ready" && item.attention_started_at ? (
                      <Button
                        disabled={savingId !== null}
                        onClick={() => void runAction(item, "finish")}
                        size="sm"
                      >
                        <Check aria-hidden="true" size={15} />
                        Finalizar
                      </Button>
                    ) : null}
                  </div>
                </div>
                <dl className="mt-4 grid gap-3 border-t border-border pt-3 text-xs sm:grid-cols-2 lg:grid-cols-5">
                  <div>
                    <dt className="flex items-center gap-1 font-semibold text-muted-foreground">
                      <Clock3 aria-hidden="true" size={13} /> En cola
                    </dt>
                    <dd className="mt-1">
                      {formatTime(item.queue_entered_at, page?.timezone ?? "UTC")}
                    </dd>
                    <dd className="text-muted-foreground">
                      Espera: {elapsedMinutes(item.queue_entered_at, item.preparation_started_at, now)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-muted-foreground">Preparación</dt>
                    <dd className="mt-1">
                      {formatTime(item.preparation_started_at, page?.timezone ?? "UTC")}
                    </dd>
                    <dd className="text-muted-foreground">
                      Duración: {elapsedMinutes(item.preparation_started_at, item.ready_at, now)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-muted-foreground">Listo</dt>
                    <dd className="mt-1">{formatTime(item.ready_at, page?.timezone ?? "UTC")}</dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-muted-foreground">Atención iniciada</dt>
                    <dd className="mt-1">
                      {formatTime(item.attention_started_at, page?.timezone ?? "UTC")}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-muted-foreground">Atención finalizada</dt>
                    <dd className="mt-1">
                      {formatTime(item.attention_completed_at, page?.timezone ?? "UTC")}
                    </dd>
                    <dd className="text-muted-foreground">
                      Duración: {elapsedMinutes(item.attention_started_at, item.attention_completed_at, now)}
                    </dd>
                  </div>
                </dl>
                {busy ? (
                  <p className="mt-3 text-xs text-muted-foreground" role="status">
                    Guardando cambio…
                  </p>
                ) : null}
              </article>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
