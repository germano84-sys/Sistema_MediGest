"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { EmptyState } from "./ui/empty-state";
import { Input } from "./ui/input";
import { useToast } from "./ui/toast";

type CalendarView = "day" | "week" | "month";

type DoctorOption = {
  id: string;
  name: string;
  specialty_ids: string[];
};

type SpecialtyOption = { id: string; name: string };
type ServiceOption = { id: string; name: string; duration_minutes: number };
type Catalog = {
  site_id: string;
  timezone: string;
  doctors: DoctorOption[];
  specialties: SpecialtyOption[];
  services: ServiceOption[];
};

type Appointment = {
  id: string;
  patient_id: string;
  patient_name: string;
  doctor_id: string;
  doctor_name: string;
  service_id: string | null;
  service_name: string | null;
  starts_at: string;
  ends_at: string;
  duration_minutes: number;
  reason: string;
  operational_notes: string | null;
  status: string;
  version: number;
};

type AppointmentHistory = {
  id: string;
  action: string;
  reason: string;
  changes: Record<string, unknown>;
  created_at: string;
};

type AvailabilitySlot = {
  doctor_id: string;
  doctor_name: string;
  starts_at: string;
  ends_at: string;
  duration_minutes: number;
};

type Holiday = {
  id: string;
  holiday_date: string;
  name: string;
};

type PatientOption = {
  id: string;
  patient_number: string;
  given_name: string;
  family_name: string;
  status: string;
};

function localDate(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function addDays(date: string, days: number) {
  const value = new Date(`${date}T12:00:00`);
  value.setDate(value.getDate() + days);
  return localDate(value);
}

function startOfWeek(date: string) {
  const value = new Date(`${date}T12:00:00`);
  value.setDate(value.getDate() - ((value.getDay() + 6) % 7));
  return localDate(value);
}

function calendarRange(date: string, view: CalendarView): [string, string] {
  if (view === "day") return [date, date];
  if (view === "week") {
    const first = startOfWeek(date);
    return [first, addDays(first, 6)];
  }
  const monthDate = new Date(`${date}T12:00:00`);
  const firstOfMonth = localDate(new Date(monthDate.getFullYear(), monthDate.getMonth(), 1, 12));
  const gridStart = startOfWeek(firstOfMonth);
  return [gridStart, addDays(gridStart, 41)];
}

function formatDay(value: string, timezone: string, options: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat("es", { ...options, timeZone: timezone }).format(
    new Date(`${value}T12:00:00Z`),
  );
}

function formatTime(value: string, timezone: string) {
  return new Intl.DateTimeFormat("es", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone,
  }).format(new Date(value));
}

async function adminFetch<T>(path: string, init?: RequestInit): Promise<T> {
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

export function AppointmentCalendar({
  tenantId,
  siteId,
  canManage,
  canManageHolidays,
}: {
  tenantId: string | null;
  siteId: string | null;
  canManage: boolean;
  canManageHolidays: boolean;
}) {
  const { toast } = useToast();
  const [view, setView] = useState<CalendarView>("week");
  const [selectedDate, setSelectedDate] = useState(() => localDate(new Date()));
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [availability, setAvailability] = useState<AvailabilitySlot[]>([]);
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [doctorId, setDoctorId] = useState("");
  const [specialtyId, setSpecialtyId] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [duration, setDuration] = useState("30");
  const [patientQuery, setPatientQuery] = useState("");
  const [patientOptions, setPatientOptions] = useState<PatientOption[]>([]);
  const [patient, setPatient] = useState<PatientOption | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<AvailabilitySlot | null>(null);
  const [reason, setReason] = useState("");
  const [operationalNotes, setOperationalNotes] = useState("");
  const [appointmentStatus, setAppointmentStatus] = useState<"scheduled" | "confirmed">("scheduled");
  const [holidayDate, setHolidayDate] = useState("");
  const [holidayName, setHolidayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [editingAppointment, setEditingAppointment] = useState<Appointment | null>(null);
  const [changeAction, setChangeAction] = useState<"confirm" | "cancel" | "reschedule">("confirm");
  const [changeReason, setChangeReason] = useState("");
  const [rescheduleDate, setRescheduleDate] = useState("");
  const [rescheduleSlots, setRescheduleSlots] = useState<AvailabilitySlot[]>([]);
  const [rescheduleSlot, setRescheduleSlot] = useState<AvailabilitySlot | null>(null);
  const [loadingRescheduleSlots, setLoadingRescheduleSlots] = useState(false);
  const [historyAppointmentId, setHistoryAppointmentId] = useState<string | null>(null);
  const [appointmentHistory, setAppointmentHistory] = useState<AppointmentHistory[]>([]);

  const [rangeStart, rangeEnd] = useMemo(
    () => calendarRange(selectedDate, view),
    [selectedDate, view],
  );
  const dates = useMemo(() => {
    const result: string[] = [];
    for (let day = rangeStart; day <= rangeEnd; day = addDays(day, 1)) result.push(day);
    return result;
  }, [rangeEnd, rangeStart]);
  const appointmentGroups = useMemo(() => {
    const grouped = new Map<string, Appointment[]>();
    for (const appointment of appointments) {
      const day = new Intl.DateTimeFormat("en-CA", {
        timeZone: catalog?.timezone ?? "UTC",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).formatToParts(new Date(appointment.starts_at));
      const dateParts = Object.fromEntries(day.map((part) => [part.type, part.value]));
      const appointmentDate = `${dateParts.year}-${dateParts.month}-${dateParts.day}`;
      grouped.set(appointmentDate, [...(grouped.get(appointmentDate) ?? []), appointment]);
    }
    return grouped;
  }, [appointments, catalog?.timezone]);
  const holidayByDate = useMemo(
    () => new Map(holidays.map((holiday) => [holiday.holiday_date, holiday.name])),
    [holidays],
  );

  const loadCalendar = useCallback(async () => {
    if (!tenantId || !siteId) {
      setCatalog(null);
      setAppointments([]);
      setAvailability([]);
      setHolidays([]);
      return;
    }
    setLoading(true);
    setError(null);
    const query = new URLSearchParams({
      site_id: siteId,
      date_from: rangeStart,
      date_to: rangeEnd,
    });
    if (doctorId) query.set("doctor_id", doctorId);
    if (specialtyId) query.set("specialty_id", specialtyId);
    if (serviceId) query.set("service_id", serviceId);
    const availabilityQuery = new URLSearchParams({
      site_id: siteId,
      date_from: selectedDate,
      date_to: selectedDate,
    });
    if (doctorId) availabilityQuery.set("doctor_id", doctorId);
    if (specialtyId) availabilityQuery.set("specialty_id", specialtyId);
    if (serviceId) availabilityQuery.set("service_id", serviceId);
    else availabilityQuery.set("duration_minutes", duration);
    const holidayQuery = new URLSearchParams({
      date_from: rangeStart,
      date_to: rangeEnd,
    });
    try {
      const [catalogResult, appointmentResult, availabilityResult, holidayResult] =
        await Promise.all([
          adminFetch<Catalog>(`tenants/${tenantId}/scheduling/catalog?site_id=${siteId}`),
          adminFetch<{ items: Appointment[] }>(
            `tenants/${tenantId}/appointments?${query.toString()}`,
          ),
          adminFetch<{ items: AvailabilitySlot[] }>(
            `tenants/${tenantId}/scheduling/availability?${availabilityQuery.toString()}`,
          ),
          adminFetch<Holiday[]>(
            `tenants/${tenantId}/sites/${siteId}/holidays?${holidayQuery.toString()}`,
          ),
        ]);
      setCatalog(catalogResult);
      setAppointments(appointmentResult.items);
      setAvailability(availabilityResult.items);
      setHolidays(holidayResult);
      if (
        doctorId &&
        !catalogResult.doctors.some(
          (doctor) =>
            doctor.id === doctorId &&
            (!specialtyId || doctor.specialty_ids.includes(specialtyId)),
        )
      ) {
        setDoctorId("");
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "No se pudo cargar la agenda.");
      setCatalog(null);
      setAppointments([]);
      setAvailability([]);
      setHolidays([]);
    } finally {
      setLoading(false);
    }
  }, [
    doctorId,
    duration,
    rangeEnd,
    rangeStart,
    selectedDate,
    serviceId,
    siteId,
    specialtyId,
    tenantId,
    refreshKey,
  ]);

  useEffect(() => {
    void loadCalendar();
  }, [loadCalendar]);

  useEffect(() => {
    const service = catalog?.services.find((option) => option.id === serviceId);
    setDuration(service ? String(service.duration_minutes) : "30");
  }, [catalog, serviceId]);

  const changeDate = (offset: number) => {
    const delta = view === "day" ? 1 : view === "week" ? 7 : 30;
    setSelectedDate((current) => addDays(current, offset * delta));
  };

  const searchPatients = async () => {
    if (!tenantId || patientQuery.trim().length < 2) return;
    try {
      const params = new URLSearchParams({ q: patientQuery.trim(), limit: "10" });
      const response = await fetch(`/api/backend/patients/records?${params}`, {
        cache: "no-store",
        headers: { "X-Tenant-ID": tenantId },
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.detail ?? "No se pudo buscar el paciente.");
      setPatientOptions(body.items);
    } catch (searchError) {
      toast({
        tone: "error",
        title: "Error al buscar pacientes",
        description: searchError instanceof Error ? searchError.message : "Intenta de nuevo.",
      });
    }
  };

  const bookAppointment = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!tenantId || !siteId || !patient || !selectedSlot) return;
    setSaving(true);
    try {
      await adminFetch(`tenants/${tenantId}/appointments`, {
        method: "POST",
        body: JSON.stringify({
          site_id: siteId,
          patient_id: patient.id,
          doctor_id: selectedSlot.doctor_id,
          service_id: serviceId || null,
          starts_at: selectedSlot.starts_at,
          duration_minutes: selectedSlot.duration_minutes,
          reason,
          operational_notes: operationalNotes || null,
          status: appointmentStatus,
        }),
      });
      toast({ tone: "success", title: "Cita agendada", description: "La agenda se actualizó." });
      setPatient(null);
      setPatientOptions([]);
      setPatientQuery("");
      setSelectedSlot(null);
      setReason("");
      setOperationalNotes("");
      setRefreshKey((value) => value + 1);
    } catch (saveError) {
      toast({
        tone: "error",
        title: "No se pudo agendar la cita",
        description: saveError instanceof Error ? saveError.message : "Intenta de nuevo.",
      });
    } finally {
      setSaving(false);
    }
  };

  const openAppointmentChange = (
    appointment: Appointment,
    action: "confirm" | "cancel" | "reschedule",
  ) => {
    setEditingAppointment(appointment);
    setChangeAction(action);
    setChangeReason("");
    setRescheduleDate("");
    setRescheduleSlots([]);
    setRescheduleSlot(null);
  };

  const loadRescheduleSlots = async (appointment: Appointment, day: string) => {
    if (!tenantId || !siteId || !day) return;
    setLoadingRescheduleSlots(true);
    try {
      const params = new URLSearchParams({
        site_id: siteId,
        date_from: day,
        date_to: day,
        doctor_id: appointment.doctor_id,
        duration_minutes: String(appointment.duration_minutes),
      });
      if (appointment.service_id) params.set("service_id", appointment.service_id);
      const response = await adminFetch<{ items: AvailabilitySlot[] }>(
        `tenants/${tenantId}/scheduling/availability?${params.toString()}`,
      );
      setRescheduleSlots(response.items);
      setRescheduleSlot(null);
    } catch (statusError) {
      toast({
        tone: "error",
        title: "No se pudo consultar la disponibilidad",
        description: statusError instanceof Error ? statusError.message : "Intenta de nuevo.",
      });
    } finally {
      setLoadingRescheduleSlots(false);
    }
  };

  const saveAppointmentChange = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!tenantId || !siteId || !editingAppointment) return;
    if (changeAction === "reschedule" && !rescheduleSlot) return;
    setSaving(true);
    try {
      await adminFetch(
        `tenants/${tenantId}/appointments/${editingAppointment.id}?site_id=${siteId}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            action: changeAction,
            expected_version: editingAppointment.version,
            reason: changeReason,
            ...(changeAction === "reschedule"
              ? { starts_at: rescheduleSlot?.starts_at }
              : {}),
          }),
        },
      );
      toast({
        tone: "success",
        title:
          changeAction === "confirm"
            ? "Cita confirmada"
            : changeAction === "cancel"
              ? "Cita cancelada"
              : "Cita reprogramada",
        description: "El historial de la cita quedó actualizado.",
      });
      if (changeAction === "reschedule" && rescheduleDate) {
        setSelectedDate(rescheduleDate);
      }
      setEditingAppointment(null);
      setRefreshKey((value) => value + 1);
    } catch (changeError) {
      toast({
        tone: "error",
        title: "No se pudo actualizar la cita",
        description: changeError instanceof Error ? changeError.message : "Intenta de nuevo.",
      });
      if (
        changeError instanceof Error &&
        changeError.message.toLocaleLowerCase("es").includes("changed by another request")
      ) {
        setRefreshKey((value) => value + 1);
        setEditingAppointment(null);
      }
    } finally {
      setSaving(false);
    }
  };

  const toggleAppointmentHistory = async (appointment: Appointment) => {
    if (!tenantId || !siteId) return;
    if (historyAppointmentId === appointment.id) {
      setHistoryAppointmentId(null);
      return;
    }
    try {
      const history = await adminFetch<AppointmentHistory[]>(
        `tenants/${tenantId}/appointments/${appointment.id}/history?site_id=${siteId}`,
      );
      setAppointmentHistory(history);
      setHistoryAppointmentId(appointment.id);
    } catch (historyError) {
      toast({
        tone: "error",
        title: "No se pudo cargar el historial",
        description: historyError instanceof Error ? historyError.message : "Intenta de nuevo.",
      });
    }
  };

  const saveHoliday = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!tenantId || !siteId) return;
    try {
      await adminFetch(`tenants/${tenantId}/sites/${siteId}/holidays`, {
        method: "POST",
        body: JSON.stringify({ holiday_date: holidayDate, name: holidayName }),
      });
      setHolidayDate("");
      setHolidayName("");
      setRefreshKey((value) => value + 1);
    } catch (holidayError) {
      toast({
        tone: "error",
        title: "No se pudo guardar el feriado",
        description: holidayError instanceof Error ? holidayError.message : "Intenta de nuevo.",
      });
    }
  };

  const removeHoliday = async (holiday: Holiday) => {
    if (!tenantId || !siteId) return;
    try {
      await adminFetch(
        `tenants/${tenantId}/sites/${siteId}/holidays/${holiday.id}`,
        { method: "DELETE" },
      );
      setRefreshKey((value) => value + 1);
    } catch (holidayError) {
      toast({
        tone: "error",
        title: "No se pudo quitar el feriado",
        description: holidayError instanceof Error ? holidayError.message : "Intenta de nuevo.",
      });
    }
  };

  if (!tenantId) {
    return <EmptyState title="Selecciona un establecimiento" description="La agenda requiere un tenant activo." />;
  }
  if (!siteId) {
    return <EmptyState title="Selecciona una sede" description="La agenda y la disponibilidad se consultan por sede." />;
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Agenda de citas</CardTitle>
          <CardDescription>
            Disponibilidad del médico según su horario y el calendario de la sede. Las observaciones son operativas; no incluyas información clínica.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-48 flex-1">
              <label className="mb-1 block text-xs font-medium" htmlFor="calendar-date">Fecha</label>
              <Input id="calendar-date" onChange={(event) => setSelectedDate(event.target.value)} type="date" value={selectedDate} />
            </div>
            <div className="flex gap-2">
              <Button onClick={() => changeDate(-1)} type="button" variant="outline">Anterior</Button>
              <Button onClick={() => setSelectedDate(localDate(new Date()))} type="button" variant="outline">Hoy</Button>
              <Button onClick={() => changeDate(1)} type="button" variant="outline">Siguiente</Button>
            </div>
            <div className="flex gap-1" role="group" aria-label="Vista de calendario">
              {(["day", "week", "month"] as const).map((option) => (
                <Button
                  aria-pressed={view === option}
                  key={option}
                  onClick={() => setView(option)}
                  type="button"
                  variant={view === option ? "default" : "outline"}
                >
                  {option === "day" ? "Día" : option === "week" ? "Semana" : "Mes"}
                </Button>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-xs font-medium">
              Especialidad
              <select className="mt-1 h-11 w-full rounded-xl border border-input bg-white px-3 text-sm" onChange={(event) => setSpecialtyId(event.target.value)} value={specialtyId}>
                <option value="">Todas</option>
                {(catalog?.specialties ?? []).map((specialty) => <option key={specialty.id} value={specialty.id}>{specialty.name}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium">
              Médico
              <select className="mt-1 h-11 w-full rounded-xl border border-input bg-white px-3 text-sm" onChange={(event) => setDoctorId(event.target.value)} value={doctorId}>
                <option value="">Todos</option>
                {(catalog?.doctors ?? [])
                  .filter((doctor) => !specialtyId || doctor.specialty_ids.includes(specialtyId))
                  .map((doctor) => <option key={doctor.id} value={doctor.id}>{doctor.name}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium">
              Servicio para disponibilidad
              <select className="mt-1 h-11 w-full rounded-xl border border-input bg-white px-3 text-sm" onChange={(event) => setServiceId(event.target.value)} value={serviceId}>
                <option value="">Sin servicio específico</option>
                {(catalog?.services ?? []).map((service) => <option key={service.id} value={service.id}>{service.name} · {service.duration_minutes} min</option>)}
              </select>
            </label>
            <label className="text-xs font-medium">
              Duración manual (minutos)
              <Input className="mt-1" disabled={Boolean(serviceId)} max={480} min={5} onChange={(event) => setDuration(event.target.value)} type="number" value={duration} />
            </label>
          </div>

          {error ? <p className="rounded-xl bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p> : null}
          {loading ? <p className="text-sm text-muted-foreground">Cargando agenda y disponibilidad…</p> : null}
          <div className={`grid gap-3 ${view === "day" ? "grid-cols-1" : view === "week" ? "md:grid-cols-2 xl:grid-cols-7" : "grid-cols-2 md:grid-cols-4 xl:grid-cols-7"}`}>
            {dates.map((day) => {
              const items = appointmentGroups.get(day) ?? [];
              const isSelectedMonth = day.slice(0, 7) === selectedDate.slice(0, 7);
              return (
                <section className={`min-h-36 rounded-xl border border-border p-3 ${view === "month" && !isSelectedMonth ? "bg-slate-50 text-muted-foreground" : "bg-white"}`} key={day}>
                  <h3 className="mb-2 flex items-center justify-between text-sm font-semibold">
                    <span>{formatDay(day, catalog?.timezone ?? "UTC", view === "day" ? { weekday: "long", day: "numeric", month: "long" } : { weekday: "short", day: "numeric", month: view === "month" ? undefined : "short" })}</span>
                    {holidayByDate.has(day) ? <Badge tone="amber">{holidayByDate.get(day)}</Badge> : null}
                  </h3>
                  <div className="space-y-2">
                    {items.map((appointment) => (
                      <article className="rounded-lg bg-teal-50 p-2 text-xs text-teal-950" key={appointment.id}>
                        <div className="flex items-center justify-between gap-1">
                          <strong>{formatTime(appointment.starts_at, catalog?.timezone ?? "UTC")} · {formatTime(appointment.ends_at, catalog?.timezone ?? "UTC")}</strong>
                          <Badge tone={appointment.status === "confirmed" ? "green" : appointment.status === "cancelled" ? "slate" : "teal"}>{appointment.status}</Badge>
                        </div>
                        <p className="mt-1 font-medium">{appointment.patient_name}</p>
                        <p>{appointment.doctor_name}{appointment.service_name ? ` · ${appointment.service_name}` : ""}</p>
                        <p className="mt-1 text-teal-800">{appointment.reason}</p>
                        {canManage && ["scheduled", "confirmed"].includes(appointment.status) ? (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {appointment.status === "scheduled" ? (
                              <button className="underline" onClick={() => openAppointmentChange(appointment, "confirm")} type="button">Confirmar</button>
                            ) : null}
                            <button className="underline" onClick={() => openAppointmentChange(appointment, "reschedule")} type="button">Reprogramar</button>
                            <button className="underline" onClick={() => openAppointmentChange(appointment, "cancel")} type="button">Cancelar</button>
                          </div>
                        ) : null}
                        <button
                          className="mt-2 block underline"
                          onClick={() => void toggleAppointmentHistory(appointment)}
                          type="button"
                        >
                          {historyAppointmentId === appointment.id ? "Ocultar historial" : "Ver historial"}
                        </button>
                        {historyAppointmentId === appointment.id ? (
                          <ol className="mt-2 space-y-2 border-l border-teal-300 pl-3">
                            {appointmentHistory.map((entry) => (
                              <li key={entry.id}>
                                <span className="font-semibold">{entry.action}</span>
                                <span> · {entry.reason}</span>
                                <time className="block text-[10px]" dateTime={entry.created_at}>
                                  {new Date(entry.created_at).toLocaleString("es")}
                                </time>
                              </li>
                            ))}
                          </ol>
                        ) : null}
                      </article>
                    ))}
                    {!items.length && view === "day" ? <p className="text-xs text-muted-foreground">Sin citas.</p> : null}
                  </div>
                </section>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {canManage && editingAppointment ? (
        <Card>
          <CardHeader>
            <CardTitle>
              {changeAction === "confirm"
                ? "Confirmar cita"
                : changeAction === "cancel"
                  ? "Cancelar cita"
                  : "Reprogramar cita"}
            </CardTitle>
            <CardDescription>
              {editingAppointment.patient_name} · {editingAppointment.doctor_name} · versión {editingAppointment.version}.
              Escribe el motivo del cambio para conservarlo en el historial.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={saveAppointmentChange}>
              {changeAction === "reschedule" ? (
                <>
                  <label className="block max-w-sm text-xs font-medium">
                    Nueva fecha (zona horaria de la sede: {catalog?.timezone})
                    <Input
                      className="mt-1"
                      min={localDate(new Date())}
                      onChange={(event) => {
                        setRescheduleDate(event.target.value);
                        setRescheduleSlots([]);
                        setRescheduleSlot(null);
                        void loadRescheduleSlots(editingAppointment, event.target.value);
                      }}
                      required
                      type="date"
                      value={rescheduleDate}
                    />
                  </label>
                  {loadingRescheduleSlots ? (
                    <p className="text-sm text-muted-foreground">Consultando nuevos horarios…</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {rescheduleSlots.map((slot) => (
                        <Button
                          aria-pressed={rescheduleSlot?.starts_at === slot.starts_at}
                          key={`${slot.doctor_id}-${slot.starts_at}`}
                          onClick={() => setRescheduleSlot(slot)}
                          type="button"
                          variant={rescheduleSlot?.starts_at === slot.starts_at ? "default" : "outline"}
                        >
                          {formatTime(slot.starts_at, catalog?.timezone ?? "UTC")}
                        </Button>
                      ))}
                      {rescheduleDate && !rescheduleSlots.length && !loadingRescheduleSlots ? (
                        <p className="text-sm text-muted-foreground">No hay horarios disponibles para esta fecha.</p>
                      ) : null}
                    </div>
                  )}
                </>
              ) : null}
              <label className="block max-w-xl text-xs font-medium">
                Motivo
                <Input
                  className="mt-1"
                  maxLength={300}
                  minLength={2}
                  onChange={(event) => setChangeReason(event.target.value)}
                  required
                  value={changeReason}
                />
              </label>
              <div className="flex gap-2">
                <Button disabled={saving || (changeAction === "reschedule" && !rescheduleSlot)} type="submit">
                  {saving ? "Guardando…" : "Guardar cambio"}
                </Button>
                <Button onClick={() => setEditingAppointment(null)} type="button" variant="outline">
                  Cerrar
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {canManage ? (
        <Card>
          <CardHeader>
            <CardTitle>Agendar una cita</CardTitle>
            <CardDescription>Selecciona una disponibilidad para {formatDay(selectedDate, catalog?.timezone ?? "UTC", { weekday: "long", day: "numeric", month: "long" })}.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {availability.length ? (
              <div className="flex flex-wrap gap-2">
                {availability.map((slot) => (
                  <Button
                    aria-pressed={selectedSlot?.starts_at === slot.starts_at && selectedSlot.doctor_id === slot.doctor_id}
                    key={`${slot.doctor_id}-${slot.starts_at}`}
                    onClick={() => setSelectedSlot(slot)}
                    type="button"
                    variant={selectedSlot?.starts_at === slot.starts_at && selectedSlot.doctor_id === slot.doctor_id ? "default" : "outline"}
                  >
                    {formatTime(slot.starts_at, catalog?.timezone ?? "UTC")} · {slot.doctor_name}
                  </Button>
                ))}
              </div>
            ) : <p className="text-sm text-muted-foreground">No hay horarios disponibles para esta fecha y filtros.</p>}

            {selectedSlot ? (
              <form className="space-y-4 border-t border-border pt-4" onSubmit={bookAppointment}>
                <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                  <Input aria-label="Buscar paciente" onChange={(event) => { setPatientQuery(event.target.value); setPatient(null); }} placeholder="Buscar paciente por nombre o apellido" value={patientQuery} />
                  <Button disabled={patientQuery.trim().length < 2} onClick={() => void searchPatients()} type="button" variant="outline">Buscar paciente</Button>
                </div>
                {patient ? <p className="text-sm font-medium">Paciente: {patient.given_name} {patient.family_name} · {patient.patient_number}</p> : null}
                {!patient && patientOptions.length ? (
                  <div className="space-y-2" aria-label="Resultados de pacientes">
                    {patientOptions.map((option) => (
                      <button className="block w-full rounded-lg border border-border p-2 text-left text-sm hover:bg-muted" key={option.id} onClick={() => { setPatient(option); setPatientOptions([]); }} type="button">
                        {option.given_name} {option.family_name} · {option.patient_number}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-xs font-medium">
                    Motivo de cita (administrativo)
                    <Input className="mt-1" maxLength={300} onChange={(event) => setReason(event.target.value)} required value={reason} />
                  </label>
                  <label className="text-xs font-medium">
                    Observaciones operativas (no clínicas)
                    <Input className="mt-1" maxLength={1000} onChange={(event) => setOperationalNotes(event.target.value)} value={operationalNotes} />
                  </label>
                </div>
                <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
                  <label className="text-xs font-medium">
                    Estado inicial
                    <select className="mt-1 h-11 w-full rounded-xl border border-input bg-white px-3 text-sm" onChange={(event) => setAppointmentStatus(event.target.value as "scheduled" | "confirmed")} value={appointmentStatus}>
                      <option value="scheduled">Programada</option>
                      <option value="confirmed">Confirmada</option>
                    </select>
                  </label>
                  <Button disabled={saving || !patient} type="submit">{saving ? "Guardando…" : "Agendar cita"}</Button>
                </div>
              </form>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {canManageHolidays ? (
        <Card>
          <CardHeader>
            <CardTitle>Feriados de la sede</CardTitle>
            <CardDescription>Un feriado bloquea la disponibilidad y las nuevas citas durante todo el día local.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form className="grid gap-3 sm:grid-cols-[1fr_2fr_auto]" onSubmit={saveHoliday}>
              <Input aria-label="Fecha del feriado" onChange={(event) => setHolidayDate(event.target.value)} required type="date" value={holidayDate} />
              <Input aria-label="Nombre del feriado" maxLength={120} minLength={2} onChange={(event) => setHolidayName(event.target.value)} placeholder="Nombre del feriado" required value={holidayName} />
              <Button type="submit">Agregar</Button>
            </form>
            {holidays.length ? holidays.map((holiday) => (
              <div className="flex items-center justify-between gap-3 rounded-lg border border-border p-3 text-sm" key={holiday.id}>
                <span>{holiday.holiday_date} · {holiday.name}</span>
                <Button onClick={() => void removeHoliday(holiday)} type="button" variant="outline">Quitar</Button>
              </div>
            )) : <p className="text-sm text-muted-foreground">No hay feriados configurados en este período.</p>}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
