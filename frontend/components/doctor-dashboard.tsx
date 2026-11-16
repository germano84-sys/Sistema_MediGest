"use client";

import { useEffect, useRef, useState } from "react";

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

type AttentionStatus = "not_started" | "pending" | "in_progress" | "completed" | "cancelled";
type ArrivalStatus = "waiting" | "arrived" | "checked_in" | "completed" | "cancelled" | "no_show";

type AgendaAppointment = {
  appointment_id: string;
  patient_name: string;
  starts_at: string;
  ends_at: string;
  appointment_status: string;
  arrival_status: ArrivalStatus;
  arrival_confirmed_at: string | null;
  checked_in_at: string | null;
  queue_entered_at: string | null;
  attention_status: AttentionStatus;
  encounter_id: string | null;
  clinical_record_id: string | null;
};

type DoctorDashboardData = {
  date: string;
  timezone: string;
  doctor_name: string;
  appointments: AgendaAppointment[];
  pending_attentions: AgendaAppointment[];
};

type ClinicalRecord = {
  id: string;
  record_number: string;
  status: string;
  patient_name: string;
  encounters: Array<{
    id: string;
    started_at: string;
    ended_at: string | null;
    status: string;
    diagnoses: Array<{
      code_system: string;
      code: string;
      description: string;
      diagnosed_on: string;
      status: string;
      is_primary: boolean;
    }>;
    prescriptions: Array<{
      medication_name: string;
      dosage: string | null;
      route: string | null;
      frequency: string | null;
      instructions: string | null;
      issued_at: string;
      status: string;
    }>;
    orders: Array<{
      order_type: string;
      description: string;
      status: string;
      requested_at: string;
    }>;
  }>;
};

const arrivalLabels: Record<ArrivalStatus, string> = {
  waiting: "Pendiente llegada",
  arrived: "Llegada confirmada",
  checked_in: "En recepción",
  completed: "Finalizada",
  cancelled: "Cancelada",
  no_show: "Ausente",
};

const attentionLabels: Record<AttentionStatus, string> = {
  not_started: "No iniciada",
  pending: "Pendiente",
  in_progress: "En curso",
  completed: "Finalizada",
  cancelled: "Cancelada",
};

async function clinicalFetch<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/backend/clinical/${path}`, {
    cache: "no-store",
    signal,
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
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone,
  }).format(new Date(value));
}

export function DoctorDashboard({
  tenantId,
  siteId,
}: {
  tenantId: string | null;
  siteId: string | null;
}) {
  const [selectedDate, setSelectedDate] = useState("");
  const [dashboard, setDashboard] = useState<DoctorDashboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  const [record, setRecord] = useState<ClinicalRecord | null>(null);
  const [recordLoading, setRecordLoading] = useState(false);
  const [recordError, setRecordError] = useState<string | null>(null);
  const recordRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!tenantId || !siteId) {
      setDashboard(null);
      return;
    }

    const params = new URLSearchParams({ site_id: siteId });
    if (selectedDate) params.set("date", selectedDate);
    const controller = new AbortController();
    setDashboard(null);
    setLoading(true);
    setError(null);
    const loadDashboard = async () => {
      try {
        const result = await clinicalFetch<DoctorDashboardData>(
          `tenants/${tenantId}/dashboard?${params.toString()}`,
          controller.signal,
        );
        setDashboard(result);
        if (!selectedDate) setSelectedDate(result.date);
      } catch (loadError) {
        if (controller.signal.aborted) return;
        setDashboard(null);
        setError(
          loadError instanceof Error
            ? loadError.message
            : "No se pudo cargar el dashboard médico.",
        );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void loadDashboard();
    return () => controller.abort();
  }, [selectedDate, siteId, tenantId]);

  useEffect(() => {
    recordRequest.current?.abort();
    recordRequest.current = null;
    setSelectedRecordId(null);
    setRecord(null);
    setRecordError(null);
    setRecordLoading(false);
    return () => recordRequest.current?.abort();
  }, [siteId, tenantId]);

  const pendingAttentions = dashboard?.pending_attentions ?? [];

  const openRecord = async (recordId: string) => {
    if (!tenantId || !siteId) return;
    if (selectedRecordId === recordId) {
      recordRequest.current?.abort();
      recordRequest.current = null;
      setSelectedRecordId(null);
      setRecord(null);
      setRecordError(null);
      return;
    }

    recordRequest.current?.abort();
    const controller = new AbortController();
    recordRequest.current = controller;
    setSelectedRecordId(recordId);
    setRecord(null);
    setRecordError(null);
    setRecordLoading(true);
    const params = new URLSearchParams({ site_id: siteId });
    try {
      const result = await clinicalFetch<ClinicalRecord>(
        `tenants/${tenantId}/records/${recordId}?${params.toString()}`,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setRecord(result);
    } catch (loadError) {
      if (controller.signal.aborted) return;
      setRecordError(
        loadError instanceof Error
          ? loadError.message
          : "No se pudo abrir el expediente clínico.",
      );
    } finally {
      if (recordRequest.current === controller) {
        recordRequest.current = null;
        setRecordLoading(false);
      }
    }
  };

  if (!tenantId || !siteId) {
    return (
      <Card>
        <EmptyState
          title={!tenantId ? "Selecciona un establecimiento" : "Selecciona una sede"}
          description="El dashboard médico requiere una sede activa."
        />
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Dashboard médico</CardTitle>
          <CardDescription>
            Agenda y atenciones asignadas a {dashboard?.doctor_name ?? "tu perfil médico"}.
            Los expedientes solo incluyen atenciones autorizadas para esta sede.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm font-medium">
              Fecha de agenda
              <Input
                className="mt-1"
                onChange={(event) => {
                  recordRequest.current?.abort();
                  recordRequest.current = null;
                  setSelectedDate(event.target.value);
                  setSelectedRecordId(null);
                  setRecord(null);
                  setRecordError(null);
                  setRecordLoading(false);
                }}
                type="date"
                value={selectedDate}
              />
            </label>
            <div className="rounded-xl bg-slate-50 p-3">
              <p className="text-xs text-muted-foreground">Citas del día</p>
              <p className="mt-1 text-xl font-semibold">{dashboard?.appointments.length ?? 0}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Atenciones pendientes: {pendingAttentions.length}
              </p>
            </div>
          </div>

          {error ? (
            <p className="rounded-xl bg-red-50 p-3 text-sm text-red-800" role="alert">
              {error}
            </p>
          ) : null}
          {loading ? (
            <p className="text-sm text-muted-foreground" role="status">
              Cargando agenda médica…
            </p>
          ) : null}

          {pendingAttentions.length > 0 ? (
            <section aria-labelledby="pending-attentions-title">
              <h3 className="mb-2 font-semibold" id="pending-attentions-title">
                Atenciones pendientes
              </h3>
              <ul className="space-y-2">
                {pendingAttentions.map((appointment) => (
                  <li
                    className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border p-3"
                    key={appointment.appointment_id}
                  >
                    <span className="font-medium">{appointment.patient_name}</span>
                    <span className="text-sm text-muted-foreground">
                      {formatTime(appointment.starts_at, dashboard?.timezone ?? "UTC")}
                    </span>
                    <Badge>{attentionLabels[appointment.attention_status]}</Badge>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {!loading && dashboard?.appointments.length === 0 ? (
            <EmptyState
              title="No hay citas para esta fecha"
              description="La agenda solo incluye pacientes asignados a tu perfil médico en la sede activa."
            />
          ) : null}

          {dashboard && dashboard.appointments.length > 0 ? (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Paciente</TableHead>
                    <TableHead>Hora</TableHead>
                    <TableHead>Llegada</TableHead>
                    <TableHead>Atención</TableHead>
                    <TableHead>Expediente</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {dashboard.appointments.map((appointment) => (
                    <TableRow key={appointment.appointment_id}>
                      <TableCell className="font-medium">{appointment.patient_name}</TableCell>
                      <TableCell>{formatTime(appointment.starts_at, dashboard.timezone)}</TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <Badge
                            tone={
                              appointment.arrival_status === "checked_in" ||
                              appointment.arrival_status === "arrived"
                                ? "teal"
                                : "slate"
                            }
                          >
                            {arrivalLabels[appointment.arrival_status]}
                          </Badge>
                          {appointment.arrival_confirmed_at ? (
                            <p className="text-xs text-muted-foreground">
                              {formatTime(appointment.arrival_confirmed_at, dashboard.timezone)}
                            </p>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell>
                        {attentionLabels[appointment.attention_status]}
                      </TableCell>
                      <TableCell>
                        {appointment.clinical_record_id ? (
                          <Button
                            aria-expanded={selectedRecordId === appointment.clinical_record_id}
                            disabled={recordLoading}
                            onClick={() => {
                              const recordId = appointment.clinical_record_id;
                              if (recordId) void openRecord(recordId);
                            }}
                            size="sm"
                            variant="outline"
                          >
                            {selectedRecordId === appointment.clinical_record_id
                              ? "Cerrar expediente"
                              : "Ver expediente"}
                          </Button>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            Sin expediente
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {selectedRecordId && recordLoading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Cargando expediente clínico…
        </p>
      ) : null}
      {recordError ? (
        <p className="rounded-xl bg-red-50 p-3 text-sm text-red-800" role="alert">
          {recordError}
        </p>
      ) : null}
      {record ? (
        <Card>
          <CardHeader>
            <CardTitle>Expediente {record.record_number}</CardTitle>
            <CardDescription>
              {record.patient_name} · Estado: {record.status}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {record.encounters.length === 0 ? (
              <EmptyState
                title="Sin atenciones previas autorizadas"
                description="El expediente no contiene atenciones de esta sede asignadas a tu perfil."
              />
            ) : (
              record.encounters.map((encounter) => (
                <article
                  className="space-y-3 rounded-xl border border-border p-4"
                  key={encounter.id}
                >
                  <div className="flex flex-wrap justify-between gap-2">
                    <h3 className="font-semibold">
                      Atención · {formatTime(encounter.started_at, dashboard?.timezone ?? "UTC")}
                    </h3>
                    <Badge>{encounter.status}</Badge>
                  </div>
                  {encounter.diagnoses.length > 0 ? (
                    <div>
                      <h4 className="text-sm font-semibold">Diagnósticos</h4>
                      <ul className="mt-1 space-y-1 text-sm">
                        {encounter.diagnoses.map((diagnosis) => (
                          <li key={`${diagnosis.code_system}-${diagnosis.code}`}>
                            {diagnosis.description} · {diagnosis.code_system} {diagnosis.code}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {encounter.prescriptions.length > 0 ? (
                    <div>
                      <h4 className="text-sm font-semibold">Recetas</h4>
                      <ul className="mt-1 space-y-1 text-sm">
                        {encounter.prescriptions.map((prescription, index) => (
                          <li key={`${prescription.medication_name}-${prescription.issued_at}-${index}`}>
                            {prescription.medication_name}
                            {prescription.dosage ? ` · ${prescription.dosage}` : ""}
                            {prescription.route ? ` · ${prescription.route}` : ""}
                            {prescription.frequency ? ` · ${prescription.frequency}` : ""}
                            {prescription.instructions ? ` · ${prescription.instructions}` : ""}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {encounter.orders.length > 0 ? (
                    <div>
                      <h4 className="text-sm font-semibold">Órdenes</h4>
                      <ul className="mt-1 space-y-1 text-sm">
                        {encounter.orders.map((order, index) => (
                          <li key={`${order.order_type}-${order.requested_at}-${index}`}>
                            {order.order_type} · {order.description} · {order.status}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </article>
              ))
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
