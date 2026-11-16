"use client";

import { useCallback, useEffect, useState } from "react";

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

type DocumentRule = {
  identifier_type: string;
  min_length: number;
  max_length: number;
  character_set: "digits" | "alphanumeric" | "uppercase_alphanumeric";
  checksum_algorithm: "none" | "ec_cedula";
  is_active: boolean;
};

type EmergencyContact = {
  name: string;
  relationship: string;
  phone: string;
  email: string;
};

type PatientSummary = {
  id: string;
  patient_number: string;
  given_name: string;
  family_name: string;
  birth_date: string | null;
  status: string;
  identifier_type: string;
  identifier_last_four: string | null;
};

type PatientDetail = PatientSummary & {
  phone: string | null;
  email: string | null;
  address: string | null;
  emergency_contacts: Array<EmergencyContact & { id: string }>;
};

type PatientPage = {
  items: PatientSummary[];
  total: number;
  limit: number;
  offset: number;
};

type AdministrativeDocument = {
  id: string;
  document_type: "identity" | "proof_of_address" | "administrative_form" | "other";
  file_name: string;
  content_type: "application/pdf" | "image/jpeg" | "image/png";
  size_bytes: number;
  created_at: string;
};

type AdministrativeFile = {
  id: string;
  site_id: string;
  patient_id: string;
  record_code: string;
  created_at: string;
  documents: AdministrativeDocument[];
};

type PatientForm = {
  identifier_type: string;
  identifier_value: string;
  given_name: string;
  family_name: string;
  birth_date: string;
  phone: string;
  email: string;
  address: string;
  emergency_contacts: EmergencyContact[];
};

const emptyContact: EmergencyContact = {
  name: "",
  relationship: "",
  phone: "",
  email: "",
};

const emptyForm = (identifierType = ""): PatientForm => ({
  identifier_type: identifierType,
  identifier_value: "",
  given_name: "",
  family_name: "",
  birth_date: "",
  phone: "",
  email: "",
  address: "",
  emergency_contacts: [],
});

async function patientFetch<T>(
  tenantId: string,
  path: string,
  method = "GET",
  payload?: Record<string, unknown>,
): Promise<T> {
  const response = await fetch(`/api/backend/patients/${path}`, {
    method,
    headers: {
      "X-Tenant-ID": tenantId,
      ...(payload ? { "Content-Type": "application/json" } : {}),
    },
    body: payload ? JSON.stringify(payload) : undefined,
    cache: "no-store",
  });
  const body = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    throw new Error(body?.detail ?? `La solicitud falló (${response.status}).`);
  }
  return body as T;
}

async function administrativeFileFetch<T>(
  tenantId: string,
  siteId: string,
  path: string,
  method = "GET",
  payload?: FormData,
): Promise<T> {
  const response = await fetch(`/api/backend/patients/${path}`, {
    method,
    headers: {
      "X-Tenant-ID": tenantId,
      "X-Site-ID": siteId,
    },
    body: payload,
    cache: "no-store",
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail ?? `La solicitud falló (${response.status}).`);
  }
  return body as T;
}

export function PatientManager({
  tenantId,
  siteId,
  canManageRules,
}: {
  tenantId: string | null;
  siteId: string | null;
  canManageRules: boolean;
}) {
  const { toast } = useToast();
  const [rules, setRules] = useState<DocumentRule[]>([]);
  const [patients, setPatients] = useState<PatientPage>({
    items: [],
    total: 0,
    limit: 25,
    offset: 0,
  });
  const [form, setForm] = useState<PatientForm>(emptyForm);
  const [selectedPatient, setSelectedPatient] = useState<PatientDetail | null>(null);
  const [query, setQuery] = useState("");
  const [documentSearchType, setDocumentSearchType] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ruleDraft, setRuleDraft] = useState<DocumentRule | null>(null);
  const [newIdentifierType, setNewIdentifierType] = useState("");
  const [administrativeFile, setAdministrativeFile] =
    useState<AdministrativeFile | null>(null);
  const [filePatient, setFilePatient] = useState<PatientSummary | null>(null);
  const [documentType, setDocumentType] =
    useState<AdministrativeDocument["document_type"]>("administrative_form");
  const [documentToUpload, setDocumentToUpload] = useState<File | null>(null);
  const [documentInputKey, setDocumentInputKey] = useState(0);
  const [fileLoading, setFileLoading] = useState(false);
  const [documentUploading, setDocumentUploading] = useState(false);

  const loadRules = useCallback(async () => {
    if (!tenantId) return;
    try {
      const currentRules = await patientFetch<DocumentRule[]>(
        tenantId,
        "document-rules",
      );
      setRules(currentRules);
      setForm((current) => ({
        ...current,
        identifier_type:
          current.identifier_type || currentRules.find((rule) => rule.is_active)?.identifier_type || "",
      }));
      setRuleDraft(currentRules[0] ?? null);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "No se pudieron cargar las reglas documentales.",
      );
    }
  }, [tenantId]);

  const searchPatients = useCallback(async () => {
    if (!tenantId || !query.trim()) {
      setPatients({ items: [], total: 0, limit: 25, offset: 0 });
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ q: query.trim() });
      if (documentSearchType) params.set("document_type", documentSearchType);
      setPatients(
        await patientFetch<PatientPage>(
          tenantId,
          `records?${params.toString()}`,
        ),
      );
    } catch (searchError) {
      setError(
        searchError instanceof Error
          ? searchError.message
          : "No se pudo completar la búsqueda.",
      );
    } finally {
      setLoading(false);
    }
  }, [documentSearchType, query, tenantId]);

  useEffect(() => {
    void loadRules();
  }, [loadRules]);

  useEffect(() => {
    setRules([]);
    setPatients({ items: [], total: 0, limit: 25, offset: 0 });
    setSelectedPatient(null);
    setAdministrativeFile(null);
    setFilePatient(null);
    setDocumentToUpload(null);
    setForm(emptyForm(rules.find((rule) => rule.is_active)?.identifier_type ?? ""));
    setError(null);
  }, [siteId, tenantId]);

  const showError = (actionError: unknown) => {
    const message =
      actionError instanceof Error
        ? actionError.message
        : "No fue posible completar la operación.";
    setError(message);
    toast({ tone: "error", title: "No se pudo completar", description: message });
  };

  const submitPatient = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!tenantId) return;
    setSaving(true);
    setError(null);
    try {
      const emergencyContacts = form.emergency_contacts
        .filter((contact) => contact.name.trim())
        .map((contact) => ({
          ...contact,
          email: contact.email || null,
        }));
      if (selectedPatient) {
        const payload: Record<string, unknown> = {
          given_name: form.given_name,
          family_name: form.family_name,
          birth_date: form.birth_date,
          phone: form.phone || null,
          email: form.email || null,
          address: form.address || null,
          emergency_contacts: emergencyContacts,
        };
        if (form.identifier_value.trim()) {
          payload.identifier_type = form.identifier_type;
          payload.identifier_value = form.identifier_value;
        }
        await patientFetch<PatientDetail>(
          tenantId,
          `records/${selectedPatient.id}`,
          "PATCH",
          payload,
        );
        toast({
          tone: "success",
          title: "Corrección guardada",
          description: "Los cambios se registraron en la auditoría del establecimiento.",
        });
      } else {
        await patientFetch<PatientDetail>(tenantId, "records", "POST", {
          ...form,
          phone: form.phone || null,
          email: form.email || null,
          address: form.address || null,
          emergency_contacts: emergencyContacts,
        });
        toast({
          tone: "success",
          title: "Paciente registrado",
          description: "El registro quedó guardado en el establecimiento activo.",
        });
      }
      setForm(emptyForm());
      setSelectedPatient(null);
      await searchPatients();
    } catch (saveError) {
      showError(saveError);
    } finally {
      setSaving(false);
    }
  };

  const editPatient = async (patientId: string) => {
    if (!tenantId) return;
    try {
      const patient = await patientFetch<PatientDetail>(
        tenantId,
        `records/${patientId}`,
      );
      setSelectedPatient(patient);
      setForm({
        identifier_type: patient.identifier_type,
        identifier_value: "",
        given_name: patient.given_name,
        family_name: patient.family_name,
        birth_date: patient.birth_date ?? "",
        phone: patient.phone ?? "",
        email: patient.email ?? "",
        address: patient.address ?? "",
        emergency_contacts: patient.emergency_contacts.map((contact) => ({
          name: contact.name,
          relationship: contact.relationship,
          phone: contact.phone,
          email: contact.email ?? "",
        })),
      });
    } catch (loadError) {
      showError(loadError);
    }
  };

  const openAdministrativeFile = async (patient: PatientSummary) => {
    if (!tenantId || !siteId) {
      showError(new Error("Selecciona una sede antes de abrir el expediente."));
      return;
    }
    setFileLoading(true);
    try {
      const file = await administrativeFileFetch<AdministrativeFile>(
        tenantId,
        siteId,
        `administrative-files/${patient.id}/open`,
        "POST",
      );
      setFilePatient(patient);
      setAdministrativeFile(file);
      setDocumentToUpload(null);
    } catch (openError) {
      showError(openError);
    } finally {
      setFileLoading(false);
    }
  };

  const uploadAdministrativeDocument = async (
    event: React.FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();
    if (!tenantId || !siteId || !administrativeFile || !documentToUpload) return;
    setDocumentUploading(true);
    try {
      const payload = new FormData();
      payload.set("document_type", documentType);
      payload.set("document", documentToUpload);
      const updatedFile = await administrativeFileFetch<AdministrativeFile>(
        tenantId,
        siteId,
        `administrative-files/${administrativeFile.id}/documents`,
        "POST",
        payload,
      );
      setAdministrativeFile(updatedFile);
      setDocumentToUpload(null);
      setDocumentInputKey((key) => key + 1);
      toast({
        tone: "success",
        title: "Documento asociado",
        description: "El archivo se guardó cifrado en el expediente administrativo.",
      });
    } catch (uploadError) {
      showError(uploadError);
    } finally {
      setDocumentUploading(false);
    }
  };

  const downloadAdministrativeDocument = async (
    administrativeDocument: AdministrativeDocument,
  ) => {
    if (!tenantId || !siteId) return;
    try {
      const response = await fetch(
        `/api/backend/patients/administrative-files/documents/${administrativeDocument.id}/download`,
        {
          headers: {
            "X-Tenant-ID": tenantId,
            "X-Site-ID": siteId,
          },
          cache: "no-store",
        },
      );
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body?.detail ?? `La descarga falló (${response.status}).`);
      }
      const objectUrl = URL.createObjectURL(await response.blob());
      const link = window.document.createElement("a");
      link.href = objectUrl;
      link.download = administrativeDocument.file_name;
      window.document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (downloadError) {
      showError(downloadError);
    }
  };

  const saveRule = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!tenantId || !ruleDraft) return;
    const identifierType = newIdentifierType.trim().toLowerCase();
    const rulesToSave = [...rules];
    if (
      identifierType &&
      !rulesToSave.some((rule) => rule.identifier_type === identifierType)
    ) {
      rulesToSave.push({
        ...ruleDraft,
        identifier_type: identifierType,
        checksum_algorithm: "none",
      });
    } else {
      const index = rulesToSave.findIndex(
        (rule) => rule.identifier_type === ruleDraft.identifier_type,
      );
      if (index >= 0) rulesToSave[index] = ruleDraft;
    }
    try {
      const saved = await patientFetch<DocumentRule[]>(
        tenantId,
        "document-rules",
        "PUT",
        { rules: rulesToSave },
      );
      setRules(saved);
      setNewIdentifierType("");
      setRuleDraft(saved[0] ?? null);
      toast({
        tone: "success",
        title: "Reglas actualizadas",
        description: "Las reglas se aplican al validar nuevos registros.",
      });
    } catch (saveError) {
      showError(saveError);
    }
  };

  const setField = (field: keyof PatientForm, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  if (!tenantId) {
    return (
      <Card>
        <EmptyState
          description="Selecciona un establecimiento con permiso de gestión de pacientes para continuar."
          title="Establecimiento requerido"
        />
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      {canManageRules ? (
        <Card>
          <CardHeader>
            <CardTitle>Reglas de identificación</CardTitle>
            <CardDescription>
              Define tipos y longitudes permitidas. Las identificaciones se cifran y
              solo se muestran parcialmente en resultados.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-3 md:grid-cols-2" onSubmit={saveRule}>
              <label className="space-y-1 text-sm font-medium">
                Regla
                <select
                  className="h-11 w-full rounded-xl border border-input bg-white px-3 text-sm"
                  onChange={(event) =>
                    setRuleDraft(
                      rules.find((rule) => rule.identifier_type === event.target.value) ?? null,
                    )
                  }
                  value={ruleDraft?.identifier_type ?? ""}
                >
                  {rules.map((rule) => (
                    <option key={rule.identifier_type} value={rule.identifier_type}>
                      {rule.identifier_type}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-1 text-sm font-medium">
                Nuevo tipo (opcional)
                <Input
                  maxLength={32}
                  onChange={(event) => setNewIdentifierType(event.target.value)}
                  pattern="[a-zA-Z][a-zA-Z0-9_-]{1,31}"
                  value={newIdentifierType}
                />
              </label>
              {ruleDraft ? (
                <>
                  <label className="space-y-1 text-sm font-medium">
                    Longitud mínima
                    <Input
                      max={64}
                      min={1}
                      onChange={(event) =>
                        setRuleDraft({ ...ruleDraft, min_length: Number(event.target.value) })
                      }
                      type="number"
                      value={ruleDraft.min_length}
                    />
                  </label>
                  <label className="space-y-1 text-sm font-medium">
                    Longitud máxima
                    <Input
                      max={64}
                      min={1}
                      onChange={(event) =>
                        setRuleDraft({ ...ruleDraft, max_length: Number(event.target.value) })
                      }
                      type="number"
                      value={ruleDraft.max_length}
                    />
                  </label>
                  <label className="space-y-1 text-sm font-medium">
                    Caracteres
                    <select
                      className="h-11 w-full rounded-xl border border-input bg-white px-3 text-sm"
                      onChange={(event) =>
                        setRuleDraft({
                          ...ruleDraft,
                          character_set: event.target.value as DocumentRule["character_set"],
                          checksum_algorithm:
                            event.target.value === "digits" &&
                            ruleDraft.checksum_algorithm === "ec_cedula"
                              ? "ec_cedula"
                              : "none",
                        })
                      }
                      value={ruleDraft.character_set}
                    >
                      <option value="digits">Solo números</option>
                      <option value="alphanumeric">Alfanuméricos</option>
                      <option value="uppercase_alphanumeric">
                        Alfanuméricos en mayúsculas
                      </option>
                    </select>
                  </label>
                  <label className="flex items-center gap-2 self-end pb-3 text-sm font-medium">
                    <input
                      checked={ruleDraft.is_active}
                      onChange={(event) =>
                        setRuleDraft({ ...ruleDraft, is_active: event.target.checked })
                      }
                      type="checkbox"
                    />
                    Regla activa
                  </label>
                  {ruleDraft.character_set === "digits" ? (
                    <label className="space-y-1 text-sm font-medium">
                      Validación adicional
                      <select
                        className="h-11 w-full rounded-xl border border-input bg-white px-3 text-sm"
                        onChange={(event) =>
                          setRuleDraft({
                            ...ruleDraft,
                            checksum_algorithm: event.target.value as DocumentRule["checksum_algorithm"],
                            min_length: event.target.value === "ec_cedula" ? 10 : ruleDraft.min_length,
                            max_length: event.target.value === "ec_cedula" ? 10 : ruleDraft.max_length,
                          })
                        }
                        value={ruleDraft.checksum_algorithm}
                      >
                        <option value="none">Sin checksum</option>
                        <option value="ec_cedula">Cédula ecuatoriana</option>
                      </select>
                    </label>
                  ) : null}
                </>
              ) : null}
              <div className="flex items-end">
                <Button disabled={!ruleDraft} type="submit">
                  Guardar reglas
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(20rem,0.9fr)]">
        <Card>
          <CardHeader>
            <CardTitle>{selectedPatient ? "Corrección de paciente" : "Registro de paciente"}</CardTitle>
            <CardDescription>
              Identificaciones y datos de contacto se cifran antes de persistirse. No
              registres información clínica aquí.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {error ? (
              <p className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">
                {error}
              </p>
            ) : null}
            <form className="space-y-4" onSubmit={submitPatient}>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="space-y-1 text-sm font-medium">
                  Tipo de identificación
                  <select
                    className="h-11 w-full rounded-xl border border-input bg-white px-3 text-sm"
                    onChange={(event) => setField("identifier_type", event.target.value)}
                    required={!selectedPatient}
                    value={form.identifier_type}
                  >
                    {rules.filter((rule) => rule.is_active).map((rule) => (
                      <option key={rule.identifier_type} value={rule.identifier_type}>
                        {rule.identifier_type}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1 text-sm font-medium">
                  {selectedPatient ? "Nueva identificación (opcional)" : "Identificación"}
                  <Input
                    autoComplete="off"
                    maxLength={64}
                    onChange={(event) => setField("identifier_value", event.target.value)}
                    required={!selectedPatient}
                    value={form.identifier_value}
                  />
                </label>
                <label className="space-y-1 text-sm font-medium">
                  Nombres
                  <Input
                    autoComplete="given-name"
                    maxLength={120}
                    onChange={(event) => setField("given_name", event.target.value)}
                    required
                    value={form.given_name}
                  />
                </label>
                <label className="space-y-1 text-sm font-medium">
                  Apellidos
                  <Input
                    autoComplete="family-name"
                    maxLength={120}
                    onChange={(event) => setField("family_name", event.target.value)}
                    required
                    value={form.family_name}
                  />
                </label>
                <label className="space-y-1 text-sm font-medium">
                  Fecha de nacimiento
                  <Input
                    max={new Date().toISOString().slice(0, 10)}
                    onChange={(event) => setField("birth_date", event.target.value)}
                    required
                    type="date"
                    value={form.birth_date}
                  />
                </label>
                <label className="space-y-1 text-sm font-medium">
                  Teléfono
                  <Input
                    autoComplete="tel"
                    maxLength={24}
                    onChange={(event) => setField("phone", event.target.value)}
                    type="tel"
                    value={form.phone}
                  />
                </label>
                <label className="space-y-1 text-sm font-medium">
                  Correo electrónico
                  <Input
                    autoComplete="email"
                    maxLength={320}
                    onChange={(event) => setField("email", event.target.value)}
                    type="email"
                    value={form.email}
                  />
                </label>
                <label className="space-y-1 text-sm font-medium sm:col-span-2">
                  Dirección
                  <Input
                    autoComplete="street-address"
                    maxLength={500}
                    onChange={(event) => setField("address", event.target.value)}
                    value={form.address}
                  />
                </label>
              </div>

              <fieldset className="space-y-3 rounded-xl border border-border p-4">
                <legend className="px-1 text-sm font-semibold">Contacto de emergencia</legend>
                {form.emergency_contacts.map((contact, index) => (
                  <div className="grid gap-3 sm:grid-cols-2" key={index}>
                    <Input
                      aria-label="Nombre del contacto de emergencia"
                      maxLength={160}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          emergency_contacts: current.emergency_contacts.map((item, itemIndex) =>
                            itemIndex === index ? { ...item, name: event.target.value } : item,
                          ),
                        }))
                      }
                      placeholder="Nombre"
                      value={contact.name}
                    />
                    <Input
                      aria-label="Relación con el paciente"
                      maxLength={80}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          emergency_contacts: current.emergency_contacts.map((item, itemIndex) =>
                            itemIndex === index
                              ? { ...item, relationship: event.target.value }
                              : item,
                          ),
                        }))
                      }
                      placeholder="Relación"
                      value={contact.relationship}
                    />
                    <Input
                      aria-label="Teléfono de emergencia"
                      maxLength={24}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          emergency_contacts: current.emergency_contacts.map((item, itemIndex) =>
                            itemIndex === index ? { ...item, phone: event.target.value } : item,
                          ),
                        }))
                      }
                      placeholder="Teléfono"
                      type="tel"
                      value={contact.phone}
                    />
                    <Input
                      aria-label="Correo de emergencia"
                      maxLength={320}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          emergency_contacts: current.emergency_contacts.map((item, itemIndex) =>
                            itemIndex === index ? { ...item, email: event.target.value } : item,
                          ),
                        }))
                      }
                      placeholder="Correo (opcional)"
                      type="email"
                      value={contact.email}
                    />
                  </div>
                ))}
                <div className="flex flex-wrap gap-2">
                  <Button
                    disabled={form.emergency_contacts.length >= 10}
                    onClick={() =>
                      setForm((current) => ({
                        ...current,
                        emergency_contacts: [...current.emergency_contacts, { ...emptyContact }],
                      }))
                    }
                    type="button"
                    variant="outline"
                  >
                    Añadir contacto
                  </Button>
                  {form.emergency_contacts.length ? (
                    <Button
                      onClick={() =>
                        setForm((current) => ({
                          ...current,
                          emergency_contacts: current.emergency_contacts.slice(0, -1),
                        }))
                      }
                      type="button"
                      variant="ghost"
                    >
                      Quitar último
                    </Button>
                  ) : null}
                </div>
              </fieldset>

              {selectedPatient ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="slate">
                    Identificación actual termina en {selectedPatient.identifier_last_four ?? "----"}
                  </Badge>
                  <Button
                    onClick={() => {
                      setSelectedPatient(null);
                      setForm(emptyForm(rules.find((rule) => rule.is_active)?.identifier_type ?? ""));
                    }}
                    type="button"
                    variant="outline"
                  >
                    Cancelar corrección
                  </Button>
                  <Button disabled={saving} type="submit">
                    {saving ? "Guardando…" : "Guardar corrección"}
                  </Button>
                </div>
              ) : (
                <Button disabled={saving || !rules.some((rule) => rule.is_active)} type="submit">
                  {saving ? "Registrando…" : "Registrar paciente"}
                </Button>
              )}
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Buscar pacientes</CardTitle>
            <CardDescription>
              Busca por nombres o por identificación. Los números de documento no se
              incluyen completos en los resultados.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="flex flex-col gap-2 sm:flex-row"
              onSubmit={(event) => {
                event.preventDefault();
                void searchPatients();
              }}
            >
              <Input
                aria-label="Nombre o identificación"
                maxLength={120}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Nombre o identificación"
                required
                value={query}
              />
              <select
                aria-label="Tipo para búsqueda por identificación"
                className="h-11 rounded-xl border border-input bg-white px-3 text-sm"
                onChange={(event) => setDocumentSearchType(event.target.value)}
                value={documentSearchType}
              >
                <option value="">Solo nombres</option>
                {rules.filter((rule) => rule.is_active).map((rule) => (
                  <option key={rule.identifier_type} value={rule.identifier_type}>
                    {rule.identifier_type}
                  </option>
                ))}
              </select>
              <Button disabled={loading} type="submit">
                {loading ? "Buscando…" : "Buscar"}
              </Button>
            </form>
            {patients.items.length ? (
              <div className="mt-4 overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Paciente</TableHead>
                      <TableHead>Identificación</TableHead>
                      <TableHead><span className="sr-only">Acciones</span></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {patients.items.map((patient) => (
                      <TableRow key={patient.id}>
                        <TableCell>
                          <span className="font-medium">
                            {patient.given_name} {patient.family_name}
                          </span>
                          <span className="block text-xs text-muted-foreground">
                            {patient.patient_number}
                          </span>
                        </TableCell>
                        <TableCell>
                          {patient.identifier_type} ····{patient.identifier_last_four ?? "----"}
                        </TableCell>
                        <TableCell>
                          <Button
                            onClick={() => void editPatient(patient.id)}
                            size="sm"
                            variant="outline"
                          >
                            Corregir
                          </Button>
                          <Button
                            disabled={!siteId || fileLoading}
                            onClick={() => void openAdministrativeFile(patient)}
                            size="sm"
                            variant="outline"
                          >
                            Expediente
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <p className="mt-3 text-xs text-muted-foreground">
                  {patients.total} resultado{patients.total === 1 ? "" : "s"}
                </p>
              </div>
            ) : query && !loading ? (
              <div className="mt-4">
                <EmptyState
                  description="No hay coincidencias para esta búsqueda en el establecimiento activo."
                  title="Sin resultados"
                />
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Expediente administrativo</CardTitle>
          <CardDescription>
            Expediente y documentos administrativos cifrados, independientes de las
            consultas y del expediente clínico.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!siteId ? (
            <EmptyState
              description="Activa una sede para abrir un expediente administrativo con código propio."
              title="Sede requerida"
            />
          ) : !administrativeFile || !filePatient ? (
            <EmptyState
              description="Busca un paciente y selecciona «Expediente» para abrirlo en esta sede."
              title="Ningún expediente abierto"
            />
          ) : (
            <div className="space-y-5">
              <div>
                <p className="text-sm text-muted-foreground">Paciente</p>
                <p className="font-medium text-ink">
                  {filePatient.given_name} {filePatient.family_name}
                </p>
                <p className="mt-1 text-sm">
                  Código del expediente:{" "}
                  <span className="font-semibold">{administrativeFile.record_code}</span>
                </p>
              </div>

              <form
                className="grid gap-3 md:grid-cols-[minmax(12rem,0.7fr)_minmax(16rem,1fr)_auto]"
                onSubmit={uploadAdministrativeDocument}
              >
                <label className="space-y-1 text-sm font-medium">
                  Tipo autorizado
                  <select
                    className="h-11 w-full rounded-xl border border-input bg-white px-3 text-sm"
                    onChange={(event) =>
                      setDocumentType(
                        event.target.value as AdministrativeDocument["document_type"],
                      )
                    }
                    value={documentType}
                  >
                    <option value="identity">Identificación</option>
                    <option value="proof_of_address">Comprobante de domicilio</option>
                    <option value="administrative_form">Formulario administrativo</option>
                    <option value="other">Otro documento administrativo</option>
                  </select>
                </label>
                <label className="space-y-1 text-sm font-medium">
                  Archivo (PDF, JPEG o PNG; máximo 10 MiB)
                  <Input
                    key={documentInputKey}
                    accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                    onChange={(event) =>
                      setDocumentToUpload(event.target.files?.[0] ?? null)
                    }
                    required
                    type="file"
                  />
                </label>
                <div className="flex items-end">
                  <Button disabled={documentUploading || !documentToUpload} type="submit">
                    {documentUploading ? "Subiendo…" : "Asociar documento"}
                  </Button>
                </div>
              </form>

              {administrativeFile.documents.length ? (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Documento</TableHead>
                        <TableHead>Tipo</TableHead>
                        <TableHead>Tamaño</TableHead>
                        <TableHead><span className="sr-only">Acciones</span></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {administrativeFile.documents.map((document) => (
                        <TableRow key={document.id}>
                          <TableCell>{document.file_name}</TableCell>
                          <TableCell>{document.document_type}</TableCell>
                          <TableCell>
                            {(document.size_bytes / 1024).toFixed(0)} KiB
                          </TableCell>
                          <TableCell>
                            <Button
                              onClick={() =>
                                void downloadAdministrativeDocument(document)
                              }
                              size="sm"
                              variant="outline"
                            >
                              Descargar
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Este expediente todavía no tiene documentos asociados.
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
