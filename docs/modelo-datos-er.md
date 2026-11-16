# Modelo de datos inicial

Diagrama lógico de persistencia del Día 2. Todas las claves primarias son UUID. Las entidades de negocio tienen `created_at` y `updated_at` UTC; `audit_events` usa `occurred_at`, y las tablas puente solo contienen las claves de relación.

```mermaid
erDiagram
    TENANTS {
        uuid id PK
        string slug UK
        string name
        string status
        timestamptz created_at
        timestamptz updated_at
    }
    SITES {
        uuid id PK
        uuid tenant_id FK
        string code
        string name
        string timezone
    }
    USERS {
        uuid id PK
        string identity_provider_subject UK
        string email
        string display_name
    }
    MEMBERSHIPS {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK
        string status
    }
    ROLES {
        uuid id PK
        string code UK
        string name
    }
    PERMISSIONS {
        uuid id PK
        string code UK
        string description
    }
    MEMBERSHIP_ROLES {
        uuid tenant_id PK, FK
        uuid membership_id PK, FK
        uuid role_id PK, FK
    }
    ROLE_PERMISSIONS {
        uuid role_id PK, FK
        uuid permission_id PK, FK
    }
    SPECIALTIES {
        uuid id PK
        string code UK
        string name
    }
    DOCTORS {
        uuid id PK
        uuid tenant_id FK
        uuid membership_id FK
        uuid specialty_id FK
        string license_number
    }
    SERVICES {
        uuid id PK
        uuid tenant_id FK
        uuid site_id FK
        string code
        string name
        int duration_minutes
        numeric price
    }
    PATIENTS {
        uuid id PK
        uuid tenant_id FK
        string patient_number
        string given_name
        string family_name
        date birth_date
    }
    PATIENT_IDENTIFIERS {
        uuid id PK
        uuid tenant_id FK
        uuid patient_id FK
        string identifier_type
        binary encrypted_value
        string lookup_digest
    }
    APPOINTMENTS {
        uuid id PK
        uuid tenant_id FK
        uuid site_id FK
        uuid patient_id FK
        uuid doctor_id FK
        uuid service_id FK
        timestamptz starts_at
        timestamptz ends_at
        string status
    }
    CLINICAL_RECORDS {
        uuid id PK
        uuid tenant_id FK
        uuid patient_id FK
        string record_number
        string status
    }
    ENCOUNTERS {
        uuid id PK
        uuid tenant_id FK
        uuid patient_id FK
        uuid clinical_record_id FK
        uuid appointment_id FK
        uuid doctor_id FK
        uuid site_id FK
        timestamptz started_at
        timestamptz ended_at
        string status
    }
    DIAGNOSES {
        uuid id PK
        uuid tenant_id FK
        uuid encounter_id FK
        string code_system
        string code
        string description
    }
    PRESCRIPTIONS {
        uuid id PK
        uuid tenant_id FK
        uuid encounter_id FK
        string medication_name
        string dosage
        string instructions
        string status
    }
    MEDICAL_ORDERS {
        uuid id PK
        uuid tenant_id FK
        uuid encounter_id FK
        string order_type
        string description
        string status
    }
    AUDIT_EVENTS {
        uuid id PK
        uuid tenant_id FK
        uuid actor_user_id FK
        string action
        string entity_type
        uuid entity_id
        json event_data
        timestamptz occurred_at
    }

    TENANTS ||--o{ SITES : owns
    TENANTS ||--o{ MEMBERSHIPS : grants
    USERS ||--o{ MEMBERSHIPS : joins
    MEMBERSHIPS ||--o{ MEMBERSHIP_ROLES : assigned
    ROLES ||--o{ MEMBERSHIP_ROLES : grants
    ROLES ||--o{ ROLE_PERMISSIONS : contains
    PERMISSIONS ||--o{ ROLE_PERMISSIONS : describes
    MEMBERSHIPS ||--o| DOCTORS : identifies
    SPECIALTIES ||--o{ DOCTORS : classifies
    TENANTS ||--o{ SERVICES : offers
    SITES ||--o{ SERVICES : hosts
    TENANTS ||--o{ PATIENTS : registers
    PATIENTS ||--o{ PATIENT_IDENTIFIERS : identifies
    PATIENTS ||--o{ APPOINTMENTS : books
    SITES ||--o{ APPOINTMENTS : schedules
    DOCTORS o|--o{ APPOINTMENTS : attends
    SERVICES o|--o{ APPOINTMENTS : provides
    PATIENTS ||--o| CLINICAL_RECORDS : owns
    PATIENTS ||--o{ ENCOUNTERS : receives
    CLINICAL_RECORDS ||--o{ ENCOUNTERS : contains
    APPOINTMENTS o|--o| ENCOUNTERS : results_in
    DOCTORS ||--o{ ENCOUNTERS : attends
    SITES ||--o{ ENCOUNTERS : hosts
    ENCOUNTERS ||--o{ DIAGNOSES : records
    ENCOUNTERS ||--o{ PRESCRIPTIONS : issues
    ENCOUNTERS ||--o{ MEDICAL_ORDERS : requests
    TENANTS o|--o{ AUDIT_EVENTS : scopes
    USERS o|--o{ AUDIT_EVENTS : performs
```

## Decisiones de integridad

- Las referencias entre entidades tenant-scoped usan claves foráneas compuestas `(tenant_id, id)` (y, cuando aplica, también `patient_id`) para rechazar relaciones entre establecimientos distintos desde PostgreSQL.
- Cada recurso tenant-scoped conserva además una FK a `tenants`. Los índices de citas, pacientes, atenciones y auditoría comienzan por `tenant_id`.
- Los estados y límites temporales/precios tienen restricciones `CHECK`; códigos y números tienen unicidad global o por tenant/sede según corresponda.
- Los identificadores de pacientes almacenan `encrypted_value` y `lookup_digest`, no el identificador original en texto claro. La gestión de claves y cifrado/digest en servicios de aplicación queda fuera del alcance de este esquema.
- `audit_events.event_data` es para metadatos técnicos permitidos; no debe contener secretos ni información clínica.
- El esquema no crea RLS ni datos semilla: las políticas PostgreSQL, permisos y flujos de negocio son trabajo posterior.
