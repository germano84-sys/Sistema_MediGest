# MediGest

Monorepositorio para MediGest, una plataforma de gestión de atención médica. Los módulos administrativos se mantienen separados de los datos clínicos.

El frontend usa Next.js App Router, TypeScript, Tailwind CSS y la configuración base para componentes shadcn/ui.

## Estructura

```text
backend/
  alembic/                 Configuración y migraciones
  app/
    api/                   Endpoints HTTP
    core/                  Configuración común
    db/                    Base SQLAlchemy y conexión
    domains/               Modelos SQLAlchemy agrupados por dominio
    main.py                Aplicación FastAPI
  tests/                   Pruebas API y esquema
frontend/
  app/                     Next.js App Router
docs/
  modelo-datos-er.md        Diagrama lógico del esquema inicial
infra/                     Espacio para infraestructura complementaria
  postgres/init/           Creación del rol PostgreSQL de runtime
compose.yaml               PostgreSQL, FastAPI y Next.js
```

Los modelos iniciales están organizados en los dominios de identidad, tenants, pacientes, agenda, atención clínica y auditoría. El diagrama y las decisiones de integridad están documentados en [docs/modelo-datos-er.md](./docs/modelo-datos-er.md).
La revisión inicial `60b458284510` crea 20 tablas de aplicación; se aplica explícitamente con Alembic y no se ejecuta al arrancar la API.

## Requisitos

- Docker Desktop con Docker Compose
- Git

No se requiere instalar Node.js ni Python en el host para ejecutar los servicios: Docker construye las imágenes.

## Inicio local

En Windows PowerShell:

```powershell
.\start.ps1
```

En Linux/macOS:

```sh
sh ./start.sh
```

El script crea `.env` desde `.env.example` si aún no existe y luego construye e inicia los contenedores. Para dejar los contenedores en segundo plano desde PowerShell, usa `.\start.ps1 -Detached`; con el script POSIX, `sh ./start.sh -d`.

Servicios disponibles:

- Frontend: <http://localhost:3000>
- API: <http://localhost:8000>
- OpenAPI de FastAPI: <http://localhost:8000/docs>
- PostgreSQL: `localhost:5432`

El frontend consulta el backend desde la red privada de Compose (`BACKEND_URL`). La página inicial muestra el resultado de esa consulta junto al estado de la base de datos. El endpoint de disponibilidad del backend ejecuta `SELECT 1` contra PostgreSQL.

## Comprobaciones

Con los servicios iniciados:

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
```

`/health` comprueba que la API responde; `/ready` comprueba además la conexión a PostgreSQL. La página del frontend incluye el resultado de `/ready`, validando la comunicación entre contenedores.

Pruebas del backend (desde `backend/`, con Python 3.12 instalado):

```sh
python -m pip install -e ".[dev]"
python -m pytest
```

Aplicar y verificar migraciones PostgreSQL con los contenedores iniciados:

```powershell
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
docker compose exec backend alembic check
```

Para revertir el esquema inicial en una base local vacía: `docker compose exec backend alembic downgrade base`. No ejecutes el downgrade en una base con datos que deban conservarse.

La prueba de esquema usa SQLite temporal para verificar constraints y rechazos tenant cruzados; la revisión inicial también se valida en PostgreSQL mediante upgrade, downgrade, reaplicación y `alembic check`.

## Aislamiento multi-tenant (Día 3)

En un volumen PostgreSQL nuevo, el entrypoint crea `medigest_app` (login de runtime sin privilegios de superusuario, creación de roles/DB o `BYPASSRLS`) y `medigest_policy_owner` (NOLOGIN, sin `BYPASSRLS`). La API usa `DATABASE_URL` como `medigest_app`; Alembic usa `MIGRATION_DATABASE_URL` como propietario/migrador. No configures la conexión de runtime con el usuario propietario.

Los valores de ejemplo son únicamente locales. En `.env`, establece una `TENANT_CONTEXT_SECRET` aleatoria de al menos 32 bytes, mantén el mismo valor para la API y Alembic, y usa `POSTGRES_APP_PASSWORD` para el usuario runtime.

Si ya existe el volumen `postgres_data` de una versión anterior, los scripts del entrypoint **no** se repiten automáticamente. Inicializa los dos roles una vez como administrador y luego levanta la pila:

```powershell
docker compose up -d db
docker compose exec -T db psql -U medigest -d medigest -f /docker-entrypoint-initdb.d/01-application-role.sql
docker compose up --build -d
docker compose exec backend alembic upgrade head
```

La migración `7f3a2c91d4e6` activa y fuerza RLS para `tenants`, sedes, membresías/roles, médicos, servicios, pacientes e identificaciones, citas, expedientes, atenciones, diagnósticos, recetas, órdenes y auditoría. El rol de aplicación no es propietario de esas tablas, no tiene `BYPASSRLS`, carece de `DELETE` general y solo recibe lectura de catálogos globales.

Usa `tenant_session(tenant_id)` en cada operación de dominio, **después** de validar que el usuario autenticado pertenece al establecimiento. El helper abre una transacción SQLAlchemy y llama a `app_private.set_tenant_context`; PostgreSQL valida una firma HMAC antes de fijar el contexto local a esa transacción. Modificar `app.tenant_id` directamente no crea un contexto autorizado. El esquema privado y la clave no son legibles por `medigest_app`. El contexto se limpia al cerrar/confirmar/revertir la transacción.

Las pruebas PostgreSQL de aislamiento requieren servicios migrados y las credenciales separadas. Desde PowerShell, monta las pruebas del repositorio porque la imagen de runtime no las incluye:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://medigest_app:medigest_app_dev_only@db:5432/medigest"
$env:MIGRATION_DATABASE_URL = "postgresql+psycopg://medigest:medigest_dev_only@db:5432/medigest"
$env:TEST_MIGRATION_DATABASE_URL = $env:MIGRATION_DATABASE_URL
$env:TENANT_CONTEXT_SECRET = "medigest-local-only-tenant-context-secret-change-me"
docker compose run --build --rm --no-deps -v "$((Get-Location).Path)\backend\tests:/app/tests:ro" -e DATABASE_URL -e MIGRATION_DATABASE_URL -e TEST_MIGRATION_DATABASE_URL -e TENANT_CONTEXT_SECRET backend sh -c 'python -m pip install ".[dev]" && python -m pytest -q -W error::sqlalchemy.exc.SAWarning'
```

Los datos de prueba son sintéticos y se eliminan mediante limpieza transaccional. `SET LOCAL row_security = off` no elude RLS: PostgreSQL rechaza las consultas filtradas. La cuenta migradora/superusuario sigue siendo privilegiada por diseño; nunca debe usarse desde solicitudes de la aplicación.

## Configuración y límites

- `.env.example` solo contiene credenciales ficticias de desarrollo. No reutilices estos valores fuera del entorno local.
- `.env` está excluido de Git; cambia sus credenciales antes de cualquier despliegue y mantén `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `POSTGRES_APP_PASSWORD` y `TENANT_CONTEXT_SECRET` sincronizados.
- PostgreSQL conserva datos en el volumen `postgres_data`. Para detener los servicios usa `docker compose down`; para borrar el volumen de datos de desarrollo, ejecuta `docker compose down -v` conscientemente.
- La disponibilidad actual verifica conectividad, no aplica migraciones automáticamente.
- Las restricciones compuestas y políticas RLS protegen las consultas tenant-scoped; la autorización que determina si el usuario autenticado pertenece al tenant solicitado debe comprobarse en la capa de aplicación antes de abrir `tenant_session`.
- Las identificaciones se cifran y se buscan por digest HMAC; teléfonos, correo, dirección y contactos de emergencia también se cifran en la aplicación. Define `PATIENT_DATA_ENCRYPTION_KEY` y `PATIENT_IDENTIFIER_HMAC_SECRET` fuera de producción con valores secretos únicos. La rotación de claves requiere un procedimiento de recifrado, que aún no está implementado.
- Los adjuntos administrativos se limitan a PDF/JPEG/PNG de hasta 10 MiB y se cifran en PostgreSQL con `ADMINISTRATIVE_DOCUMENT_ENCRYPTION_KEY`; define una clave única en producción y considera su respaldo y rotación. No se admiten documentos clínicos en este módulo.

## Expediente administrativo (Día 9)

Ventanilla puede buscar un paciente y abrir su expediente desde la sede activa. La API requiere `X-Tenant-ID`, `X-Site-ID` y `patients:manage`; la apertura es idempotente y el código `EXP-<sede>-<sufijo>` es único dentro de la sede. Las rutas administrativas son `POST /api/v1/patients/administrative-files/{patient_id}/open`, `GET /api/v1/patients/administrative-files/{patient_id}`, carga multipart en `POST /api/v1/patients/administrative-files/{file_id}/documents` y descarga autenticada en `GET /api/v1/patients/administrative-files/documents/{document_id}/download`.

El catálogo permitido es identificación, comprobante de domicilio, formulario administrativo u otro documento administrativo. Solo se aceptan PDF/JPEG/PNG con extensión y firma concordantes, de 1 byte a 10 MiB. El contenido se cifra en la aplicación antes de guardarse en PostgreSQL. Para instalar el cambio, actualizar `ADMINISTRATIVE_DOCUMENT_ENCRYPTION_KEY` en `.env` con una clave Fernet secreta propia de 32 bytes codificada en base64, reconstruir y migrar:

```powershell
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose exec backend alembic check
```

La suite PostgreSQL cubre apertura repetible, carga/descarga, cifrado, RBAC y RLS:

```powershell
$env:TEST_MIGRATION_DATABASE_URL = "******db:5432/medigest"
docker compose run --rm --no-deps -v "$((Get-Location).Path)\backend\tests:/app/tests:ro" backend sh -c 'python -m pip install ".[dev]" && TEST_MIGRATION_DATABASE_URL="$MIGRATION_DATABASE_URL" python -m pytest -q -W error::sqlalchemy.exc.SAWarning'
```

No hay endpoints clínicos de escritura expuestos por el backend en esta etapa. El rol Ventanilla no recibe permisos `clinical:read` ni `clinical:write`; el módulo administrativo no permite crear diagnósticos, notas médicas ni alterar consultas.

## Dashboard administrativo (Día 10)

Administradores de tenant y superadministradores pueden consultar `GET /api/v1/admin/tenants/{tenant_id}/dashboard`. La respuesta calcula pacientes registrados, citas por estado, médicos con horario disponible al menos un día del período, atenciones con estado completado y productividad agregada por médico. Acepta `start_date`, `end_date` (máximo 366 días inclusive), `site_id` y `specialty_id`. Las fechas se evalúan como días UTC; las citas y atenciones usan su hora de inicio. Productividad cuenta atenciones completadas y la tasa de citas completadas sobre las no canceladas ni marcadas como ausencia.

Todos los agregados se ejecutan en PostgreSQL con contexto tenant y RLS; la API verifica rol de administración, permiso y sede activa para el filtro solicitado. El dashboard frontend se muestra solo a administradores. El conteo de pacientes es por fecha de alta; al filtrar sede/especialidad, considera pacientes con cita de ese contexto durante el período porque el registro de paciente actual no almacena sede de alta.

La suite automatizada de `backend/tests/test_reporting_dashboard.py` prepara datos sintéticos y valida estados, KPIs, productividad, filtros, fechas inválidas, permisos y aislamiento. Ejecuta las instrucciones de pruebas PostgreSQL de arriba; no requiere migración ni esquema nuevo.

## Agenda de citas (Día 11)

La agenda autenticada ofrece vistas de día, semana y mes por sede. Los endpoints `GET /api/v1/admin/tenants/{tenant_id}/scheduling/catalog` y `GET /api/v1/admin/tenants/{tenant_id}/scheduling/availability` reciben `site_id`; disponibilidad acepta `date_from`, `date_to` (hasta 31 días), `doctor_id`, `specialty_id`, `service_id` y `duration_minutes` (5–480). Los servicios aplican su duración configurada; sin servicio se usa la duración indicada. Los horarios se calculan en la zona IANA de la sede, con inicios cada 15 minutos, y solo incluyen médicos activos con disponibilidad semanal.

El calendario usa `GET /api/v1/admin/tenants/{tenant_id}/appointments` con fechas inclusivas (hasta 62 días) y filtros de sede, médico, especialidad, servicio y estado. Para reservar se usa `POST` al mismo recurso con `site_id`, `patient_id`, `doctor_id`, `starts_at` con zona horaria, `reason`, `status`, duración y `operational_notes`. La duración puede omitirse si se selecciona un servicio. Las citas nuevas inician como `scheduled` o `confirmed`; los cambios de estado y reprogramaciones se detallan en la sección del Día 12.

## Reprogramación y cancelación (Día 12)

El endpoint `PATCH /api/v1/admin/tenants/{tenant_id}/appointments/{appointment_id}?site_id=...` recibe una acción (`confirm`, `cancel` o `reschedule`), un motivo obligatorio y `expected_version`, que debe coincidir con la versión actual de la cita. Para reprogramar, envía además `starts_at` con zona horaria; opcionalmente puede cambiarse el médico, servicio o duración (la duración debe coincidir con la del servicio). Solo las citas `scheduled` pueden confirmarse; las citas `scheduled` o `confirmed` pueden cancelarse o reprogramarse. Las citas `checked_in`, `completed`, `cancelled` y `no_show` son terminales para estas operaciones. Las transiciones inválidas, versiones desactualizadas y conflictos de disponibilidad devuelven HTTP 409 con un mensaje explícito.

Cada creación, confirmación, cancelación y reprogramación registra actor, motivo, estado anterior/nuevo y los campos operativos modificados en `appointment_history`. El historial se consulta con `GET /api/v1/admin/tenants/{tenant_id}/appointments/{appointment_id}/history?site_id=...`; el registro es de solo inserción para el rol de aplicación y está aislado por tenant/RLS. Las respuestas de cita exponen `version` para control optimista. Bloqueos transaccionales compartidos entre creación, reprogramación, confirmación y cancelación serializan cambios por médico, paciente y fecha de sede; ante solicitudes simultáneas incompatibles una reserva prevalece y las otras reciben 409.

Aplicar con `docker compose exec backend alembic upgrade head`; la migración `d1a7c9e5b204` agrega versión optimista e historial. La UI solicita motivo para cada cambio, ofrece nuevos horarios disponibles al reprogramar, muestra historial y refresca el calendario al guardar. Pruebas PostgreSQL en `backend/tests/test_scheduling_api.py` cubren transiciones, historial, versión obsoleta, conflictos y reservas concurrentes.

Se valida la disponibilidad del médico, el horario de apertura de sede cuando está configurado, la vigencia del paciente/médico/servicio y los solapamientos del médico y del paciente. Los bloqueos transaccionales impiden reservas simultáneas superpuestas. Las notas son operativas y no deben contener información clínica.

Los feriados de día completo se administran por sede y requieren `tenant:manage`: `GET/POST /api/v1/admin/tenants/{tenant_id}/sites/{site_id}/holidays` y `DELETE` por ID. Un feriado configurado bloquea tanto la oferta de horarios como la creación de citas en la fecha local. Aplicar el esquema con `docker compose exec backend alembic upgrade head`; la migración `c4e8a7b19d32` añade los campos administrativos de cita y el catálogo de feriados con RLS por tenant.

La suite PostgreSQL `backend/tests/test_scheduling_api.py` valida disponibilidad por filtros, calendario, duración del servicio, reservas, conflictos, feriados, permisos y aislamiento. La interfaz se prueba con `docker compose run --rm --no-deps` montando `frontend/tests` y `frontend/lib`, seguido por `frontend node --experimental-strip-types --test tests/*.test.ts`.

## Recepción de pacientes (Día 13)

La sección Ventanilla muestra las citas por fecha local de la sede, permite buscar por nombre o número de paciente y filtrar por profesional, estado y estado de cola. La respuesta se limita a identificación administrativa y agenda; no incluye el motivo de la cita ni datos clínicos. La lectura requiere `appointments:read` y `patients:manage`.

El endpoint `GET /api/v1/admin/tenants/{tenant_id}/operations/reception/appointments` acepta `site_id` y, opcionalmente, `date`, `q`, `doctor_id`, `status` y `queue` (`waiting` o `sent`). La recepción confirma identidad/llegada con `POST /api/v1/admin/tenants/{tenant_id}/operations/reception/appointments/{appointment_id}/confirm-arrival?site_id=...`; luego registra check-in en `/check-in` y deriva a la cola en `/send-to-queue`. Cada acción recibe `expected_version`, exige `appointments:manage` y `patients:manage`, valida el orden y devuelve HTTP 409 ante transiciones duplicadas, fuera de orden o versiones obsoletas.

Las marcas `arrival_confirmed_at`, `checked_in_at` y `queue_entered_at` quedan en la cita con restricciones de orden en PostgreSQL. Las operaciones también registran actor y acción en la auditoría sin incluir nombres ni notas. Aplica la migración con `docker compose exec backend alembic upgrade head` y verifica con `docker compose exec backend alembic check`.

Criterios de aceptación: buscar una cita del día por nombre/número; filtrar por fecha, profesional, estado y cola; mostrar hora local y los tres tiempos operativos; impedir check-in antes de confirmar llegada y entrada a cola antes del check-in; rechazar acciones duplicadas o sin permisos; mantener la recepción administrativa separada de los datos clínicos. Las pruebas API PostgreSQL están en `backend/tests/test_scheduling_api.py`; las transiciones y restricciones se prueban en `backend/tests/test_reception_operations.py` y `backend/tests/test_schema.py`.

## Panel de Servicio (Día 14)

El rol Servicio administra únicamente la cola operativa recibida desde Ventanilla. El panel permite filtrar por fecha de entrada a cola, estado y sala, asignar una sala, iniciar preparación, marcar el turno listo, iniciar atención y finalizarla. Cada acción usa la versión de la cita para detectar cambios concurrentes; una sala no puede ocuparse simultáneamente por dos atenciones. Se muestran nombre del paciente, turno, profesional, sala y marcas/duraciones operativas, pero no número de paciente, motivo, notas operativas ni información clínica.

La API requiere `appointments:read` y `operations:manage`. `GET /api/v1/admin/tenants/{tenant_id}/operations/service/queue` acepta `site_id` y filtros opcionales `date`, `status` (`pending`, `preparing`, `ready`, `completed`) y `room_id`. `PATCH /api/v1/admin/tenants/{tenant_id}/operations/service/queue/{appointment_id}?site_id=...` recibe `action`, `expected_version` y `room_id` únicamente para `assign-room`. Las acciones disponibles son `assign-room`, `start-preparation`, `mark-ready`, `start-attention` y `finish`; las transiciones inválidas, salas inactivas/ocupadas, permisos insuficientes o versiones obsoletas se rechazan explícitamente.

La migración `4a7c2d8e913f` añade estado y tiempos operativos, índices y restricciones de integridad, además de la referencia tenant+sede a la sala. Aplícala y verifica el esquema con:

```powershell
docker compose exec backend alembic upgrade head
docker compose exec backend alembic check
```

La suite PostgreSQL cubre el ciclo Ventanilla→Servicio, permisos y contenido mínimo de la respuesta en `backend/tests/test_scheduling_api.py`; las transiciones puras se prueban en `backend/tests/test_service_operations.py` y las restricciones del modelo en `backend/tests/test_schema.py`. Ejecútala con el procedimiento de pruebas PostgreSQL de la sección Día 3. Las pruebas UI se ejecutan desde `frontend/` con `npm run test:ui`; la compilación se valida con `npm run build`.

Criterios de aceptación: solo las citas enviadas por Ventanilla aparecen en la cola del día local; el Servicio puede asignar sala y completar las transiciones en orden; se registran inicio de preparación, listo, inicio y fin de atención y sus duraciones; la ocupación concurrente de una sala y las versiones obsoletas se rechazan; el rol sin permiso no puede consultar ni modificar la cola; ninguna respuesta o vista de Servicio expone notas clínicas, diagnósticos ni recetas.

## Dashboard médico (Día 15)

El rol Médico consulta su agenda del día según la zona horaria de la sede, con estado de llegada, atenciones pendientes y acceso al expediente clínico. `GET /api/v1/clinical/tenants/{tenant_id}/dashboard?site_id=...&date=...` requiere `clinical:read`, rol Médico y un perfil `Doctor` activo asociado al usuario; la consulta filtra siempre por ese médico y sede. `GET /api/v1/clinical/tenants/{tenant_id}/records/{record_id}?site_id=...` permite abrir un expediente solo si el paciente tiene una cita vigente o una atención del médico en esa sede, y devuelve únicamente atenciones, diagnósticos, recetas y órdenes de ese mismo ámbito.

La autorización también limita `GET /api/v1/admin/tenants/{tenant_id}/appointments` y el historial de citas para médicos al perfil propio; un filtro explícito por otro médico se rechaza. La interfaz reemplaza para ese rol la agenda general por el Dashboard médico y usa el BFF autenticado `/api/backend/clinical`. No se requieren cambios de esquema ni migración.

Pruebas PostgreSQL sintéticas: `backend/tests/test_reporting_dashboard.py` verifica aislamiento por médico y sede, acceso al expediente propio, denegación de otros pacientes e historial de otras citas; también cubre permisos. Ejecuta `python -m pytest` desde `backend/` con `TEST_MIGRATION_DATABASE_URL` configurada como se describe en Día 3. Desde `frontend/`, valida navegación con `npm run test:ui` y compila con `npm run build`.

Criterios de aceptación: el médico solo ve sus citas y pacientes de la sede autorizada; la llegada y las atenciones pendientes reflejan las marcas persistidas; no puede consultar citas, historiales ni expedientes de otro médico; el expediente incluye solo atenciones del médico en la sede; usuarios sin rol/permisos clínicos reciben `403` o `404` sin revelar la existencia de recursos ajenos.

## Autenticación OIDC, MFA y RBAC (Día 4)

Keycloak se ejecuta localmente en <http://localhost:8080>; el cliente web usa Authorization Code con PKCE S256 y `state`. NextAuth mantiene una sesión JWT en cookie HttpOnly y el token de acceso solo se utiliza en el servidor. La ruta BFF `GET /api/backend/auth/me` reenvía la identidad a FastAPI sin exponer el token al navegador. El issuer público es `http://localhost:8080/realms/medigest`; el frontend y el backend usan `http://keycloak:8080` para comunicación entre contenedores.

El backend verifica firma RS256 mediante JWKS y comprueba issuer, audiencia, vigencia y claims requeridos. `GET /api/v1/auth/me` requiere `Authorization: Bearer <access-token>` y acepta `X-Tenant-ID` opcional para resolver membresía y permisos de ese establecimiento. Sin token devuelve `401`; si se solicita un tenant sin membresía activa, devuelve `403`. Los endpoints de dominio deben aplicar `require_permission(...)` para rechazar con `403` permisos ausentes. Los roles y permisos provienen de MediGest, no de roles declarados por el navegador ni de claims RBAC de Keycloak.

La migración `9c4e7a1b2d6f` crea los cinco roles (`superadmin`, `administrator`, `doctor`, `service`, `receptionist`), sus permisos granulares y el rol global. Para aplicar el esquema en el entorno local:

```powershell
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose exec backend alembic check
```

La aplicación sincroniza el usuario OIDC por `sub`. El Día 6 incorpora una interfaz de superadministración para crear/suspender establecimientos y gestionar el catálogo global, además de administración de recursos institucionales. La creación de membresías y la asignación de roles todavía requieren un flujo privilegiado separado; `medigest_app` no puede modificar `platform_role_id`.

El backend exige evidencia MFA (`amr` con un método MFA aceptado o `acr` de nivel 2) para `superadmin`, `administrator` y `doctor`; el cliente solicita `acr_values=2`. Para cuentas privilegiadas, el administrador de Keycloak debe requerir y configurar TOTP (acción requerida **Configure OTP**) antes de otorgarles esos roles. Si el token no acredita MFA, las operaciones protegidas se rechazan con `403`. El flujo interactivo completo con una cuenta TOTP no se validó en esta jornada; sí se probaron la denegación sin MFA y las señales aceptadas en pruebas automatizadas.

La recuperación de contraseña está habilitada en Keycloak. En local, los correos de recuperación se pueden revisar en <http://localhost:8025> (Mailpit). Las credenciales y secretos de `.env.example` son exclusivamente de desarrollo; reemplázalos antes de cualquier despliegue. Para más detalle y limitaciones, consulta [docs/PROGRESO.md](./docs/PROGRESO.md).

## Sistema visual (Día 5)

El frontend aplica un sistema visual responsive con tokens Tailwind y componentes reutilizables con convenciones shadcn/ui. El login usa la sesión OIDC real; después de autenticar, la interfaz consulta `GET /api/backend/auth/me`. La navegación lateral se genera únicamente a partir de permisos devueltos por FastAPI. No se muestran métricas de ejemplo ni registros clínicos simulados.

El selector general de contexto valida el UUID contra el backend y solo lo conserva en `sessionStorage`; conocer un ID no concede acceso. En el área de administración, el superadministrador puede elegir establecimientos desde el listado persistido. Los módulos que todavía no existen muestran estados vacíos explícitos. Las notificaciones son una base accesible para mensajes de interfaz y no representan alertas de producción.

Componentes de interfaz: `components/ui/` (botón, campo, tarjeta, etiqueta, tabla, diálogo nativo accesible, breadcrumbs, estado vacío y notificaciones accesibles). Pruebas unitarias de navegación por permisos, con Node.js 22:

```powershell
docker compose run --rm --no-deps `
  -v "$((Get-Location).Path)\frontend\tests:/app/tests:ro" `
  -v "$((Get-Location).Path)\frontend\lib:/app/lib:ro" `
  frontend npm run test:ui
```

Para validar frontend y servicios con Docker: `docker compose up --build -d`, luego abre <http://localhost:3000>. El diálogo de establecimiento requiere una membresía real provisionada en la base de datos.

## Validación de arranque

Validado con Docker Compose: `docker compose up --build -d` construyó e inició los tres servicios y `docker compose ps` reportó `healthy` para `db`, `backend` y `frontend`. Las comprobaciones en ejecución devolvieron:

- `/health`: `{"status":"ok"}`
- `/ready`: `{"status":"ready","database":"ok"}`
- PostgreSQL: `pg_isready` y `SELECT 1` exitosos.
- Frontend: HTTP 200; el HTML renderizado mostró la API y PostgreSQL conectados.
- Backend: `python -m pytest -q`: 3 pruebas pasaron en la validación del Día 1.

Para detener el entorno después de validar, ejecuta `docker compose down`; esto conserva el volumen local de PostgreSQL.

### Validación del modelo de datos (Día 2)

- `python -m pytest -q -W error::sqlalchemy.exc.SAWarning`: 8 pruebas pasaron; solo se reporta el aviso deprecado de AnyIO en Starlette.
- Migración `60b458284510`: upgrade, downgrade, reaplicación y `alembic check` completados en PostgreSQL.
- PostgreSQL rechazó una cita transaccional que intentaba enlazar un paciente de otro tenant; la transacción se revirtió.
- `alembic check` confirmó que no hay diferencias entre el esquema aplicado y la metadata SQLAlchemy.

### Validación del aislamiento (Día 3)

- Migración `7f3a2c91d4e6` aplicada a PostgreSQL; `alembic check` informó `No new upgrade operations detected`.
- `docker compose config --quiet` pasó; `db`, `backend` y `frontend` reportaron `healthy`.
- Se ejecutó la suite completa en un contenedor temporal conectado a PostgreSQL como `medigest_app`: 14 pruebas pasaron; un aviso deprecado provino de `starlette.testclient`/AnyIO.
- Las pruebas PostgreSQL confirmaron el filtrado de pacientes e identificaciones del otro tenant, rechazo de inserciones cruzadas, actualización sin filas afectadas, rechazo de contexto HMAC falsificado, imposibilidad de leer la clave o apagar RLS, y limpieza del contexto al finalizar la transacción.

## Administración institucional (Día 6)

La administración se ofrece en la vista autenticada para usuarios con permisos de plataforma o de gestión del establecimiento. El frontend llama al backend mediante un BFF Next.js que adjunta el token OIDC en el servidor; FastAPI vuelve a comprobar RBAC y la membresía, y PostgreSQL aplica RLS. No se envían tokens al navegador ni se confía en permisos proporcionados por el cliente.

Endpoints bajo `/api/v1/admin`:

- `GET/POST /tenants` y `GET/PATCH/DELETE /tenants/{tenant_id}` para establecimientos. La eliminación física se rechaza para preservar auditoría; suspende el establecimiento con `PATCH {"status":"suspended"}`.
- `GET/POST/PATCH/DELETE /specialties` para el catálogo global, exclusivo de superadministración.
- `GET/POST /tenants/{tenant_id}/sites` y `PATCH/DELETE /tenants/{tenant_id}/sites/{site_id}` para sedes.
- `GET/POST /tenants/{tenant_id}/specialties` y `PATCH/DELETE /tenants/{tenant_id}/specialties/{link_id}` para habilitar especialidades del catálogo por establecimiento.
- `GET/POST /tenants/{tenant_id}/sites/{site_id}/rooms` y `PATCH/DELETE .../rooms/{room_id}` para consultorios.
- `GET/POST /tenants/{tenant_id}/sites/{site_id}/hours` y `PATCH/DELETE .../hours/{hours_id}` para horarios; `weekday` usa `datetime.weekday()` (lunes `0`, domingo `6`).
- `GET/POST /tenants/{tenant_id}/settings` y `PATCH/DELETE /tenants/{tenant_id}/settings/{key}` para parámetros JSON institucionales. Se rechazan claves/valores que parezcan secretos y valores mayores a 8 KiB.

La migración `e64b7c2d901f` crea recursos y políticas RLS; `c6a9e3f417b2` concede únicamente el permiso adicional de eliminación por fila en `sites`. Para aplicar y verificar:

```powershell
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose exec backend alembic check
```

La suite PostgreSQL (incluye pruebas de RLS de consultorios, horarios y parámetros) se ejecuta en contenedor con:

```powershell
docker compose run --rm --no-deps `
  -v "$((Get-Location).Path)\backend\tests:/app/tests:ro" `
  backend sh -c 'python -m pip install ".[dev]" && TEST_MIGRATION_DATABASE_URL="$MIGRATION_DATABASE_URL" python -m pytest -q -W error::sqlalchemy.exc.SAWarning'
```

En `.env`, mantén `DATABASE_URL`, `MIGRATION_DATABASE_URL` y `TENANT_CONTEXT_SECRET` alineados con la instalación local. Los fixtures usan únicamente datos sintéticos.

## Usuarios y médicos (Día 7)

La migración `b7d4a9c2e615` agrega roles por sede (`membership_site_roles`), asociaciones médico-especialidad (`doctor_specialties`) y disponibilidad semanal (`doctor_availability`), con claves foráneas, índices, restricciones, backfill de la especialidad principal y RLS forzado. El administrador del establecimiento puede asignar por sede únicamente `doctor`, `service` y `receptionist`; `administrator` y `superadmin` conservan sus alcances tenant/plataforma.

Endpoints administrativos bajo `/api/v1/admin`:

- `GET /tenants/{tenant_id}/managed-roles`: roles operativos asignables.
- `GET/POST /tenants/{tenant_id}/users`: búsqueda por `q`, `status`, `role_code` y `site_id`, con `limit`/`offset` y total. Crear usuario provisiona identidad en Keycloak y manda `VERIFY_EMAIL` y `UPDATE_PASSWORD`; para el rol médico también requiere `CONFIGURE_TOTP`. No acepta ni almacena contraseñas en PostgreSQL.
- `PUT /tenants/{tenant_id}/users/{membership_id}/sites/{site_id}/roles` y `PATCH /tenants/{tenant_id}/users/{membership_id}/status`: reemplaza roles de sede o activa/suspende la membresía.
- `GET/POST /tenants/{tenant_id}/doctors`: filtra por `q`, `specialty_id` e `is_active`, con paginación y total. `PATCH .../doctors/{doctor_id}` cambia licencia/estado; `PUT .../doctors/{doctor_id}/specialties` reemplaza asociaciones y especialidad principal.
- `GET/POST /tenants/{tenant_id}/doctors/{doctor_id}/availability`, `PATCH .../availability/{availability_id}` y `DELETE .../availability/{availability_id}`: gestiona intervalos semanales por sede; lunes es `weekday=0`, domingo `weekday=6`, y no se permiten intervalos superpuestos.

La autorización usa permisos de MediGest y valida membresía activa antes de abrir la transacción tenant. `/api/v1/auth/me` también acepta `X-Site-ID` junto con `X-Tenant-ID` para incluir permisos de sede; el BFF los reenvía desde el servidor. Las operaciones administrativas escriben eventos de auditoría sin registrar correo, credenciales ni datos clínicos.

Keycloak recibe las invitaciones mediante `client_credentials` con un cliente dedicado de servicio y solo los roles `manage-users` y `view-users`; la cuenta maestra no se usa desde FastAPI. En un volumen de Keycloak existente que se creó antes de agregar `medigest-admin-api`, actualiza el cliente una vez con las credenciales locales en `.env`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\keycloak\provision-admin-client.ps1
```

El script es idempotente y no imprime los secretos. En volúmenes nuevos, el realm de `infra/keycloak/realm/medigest-realm.json` ya incluye el cliente de servicio. Mantén `KEYCLOAK_ADMIN_CLIENT_SECRET` alineado entre `.env` y Keycloak; fuera de desarrollo usa un secreto único y HTTPS.

Aplicar/verificar la migración y ejecutar las pruebas PostgreSQL sintéticas:

```powershell
docker compose exec backend alembic upgrade head
docker compose exec backend alembic check
docker compose run --rm --no-deps `
  -v "$((Get-Location).Path)\backend\tests:/app/tests:ro" `
  -e TEST_MIGRATION_DATABASE_URL=postgresql+psycopg://medigest:medigest_dev_only@db:5432/medigest `
  backend sh -c 'python -m pip install ".[dev]" && python -m pytest -q -W error::sqlalchemy.exc.SAWarning'
```

La interfaz autenticada permite invitar usuarios, filtrar/paginar, asignar roles por sede, mantener perfiles médicos/especialidades y editar disponibilidad. La API y RLS son autoritativos; el cliente no envía tokens al navegador ni sustituye permisos del servidor.

## Registro de pacientes (Día 8)

FastAPI expone `GET /api/v1/patients/document-rules`, `PUT /api/v1/patients/document-rules`, `POST /api/v1/patients/records`, `GET /api/v1/patients/records`, `GET /api/v1/patients/records/{patient_id}` y `PATCH /api/v1/patients/records/{patient_id}`. Todos requieren token OIDC, `X-Tenant-ID`, membresía activa y el permiso `patients:manage`; la modificación de reglas también exige rol `administrator` y `tenant:manage`. La interfaz autenticada de Ventanilla usa un BFF Next.js que mantiene el bearer fuera del navegador.

El establecimiento puede configurar reglas de identificación con longitudes, conjunto de caracteres, activación y checksum admitido (ninguno o cédula ecuatoriana). Los valores se normalizan, cifran con Fernet y buscan/deduplican por HMAC-SHA-256; la API solo devuelve tipo y últimos cuatro caracteres. Contactos, dirección y contactos de emergencia se cifran antes de persistirse. Las correcciones generan auditoría con nombres de campos modificados, nunca valores personales.

**Límite de protección de datos:** nombres y fecha de nacimiento siguen en texto claro en las columnas existentes de `patients`; esta entrega no ofrece cifrado/índices privados para esos campos ni representa una evaluación de cumplimiento legal. Revisa esa exposición y el cifrado/gestión de llaves antes de usar datos personales reales.

Para migrar la base y comprobar la metadata desde la raíz:

```powershell
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose exec backend alembic check
```

En `.env`, establece claves únicas para `PATIENT_DATA_ENCRYPTION_KEY` (clave Fernet URL-safe base64 de 32 bytes) y `PATIENT_IDENTIFIER_HMAC_SECRET` (secreto aleatorio de al menos 32 bytes). Los valores de ejemplo son solo de desarrollo. No hay rotación de claves automática: conserva las claves de los datos existentes y planifica un recifrado antes de reemplazarlas.

La suite `backend/tests/test_patients.py` usa PostgreSQL real para probar registro, validación, duplicados, correcciones auditadas, RBAC y lecturas/escrituras entre tenants. Para ejecutarla desde PowerShell con la pila en marcha:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://medigest_app:medigest_app_dev_only@db:5432/medigest"
$env:MIGRATION_DATABASE_URL = "postgresql+psycopg://medigest:medigest_dev_only@db:5432/medigest"
$env:TEST_MIGRATION_DATABASE_URL = $env:MIGRATION_DATABASE_URL
$env:TENANT_CONTEXT_SECRET = "medigest-local-only-tenant-context-secret-change-me"
docker compose run --build --rm --no-deps -v "$((Get-Location).Path)\backend\tests:/app/tests:ro" -e DATABASE_URL -e MIGRATION_DATABASE_URL -e TEST_MIGRATION_DATABASE_URL -e TENANT_CONTEXT_SECRET backend sh -c 'python -m pip install ".[dev]" && python -m pytest -q -W error::sqlalchemy.exc.SAWarning'
```

La búsqueda por documento es exacta; búsquedas por nombre y apellido admiten coincidencias parciales. Los datos de prueba son sintéticos y se eliminan al terminar. No se avanza al Día 9.

## Desarrollo

Consulta [AGENTS.md](./AGENTS.md) para convenciones del repositorio, [docs/PROGRESO.md](./docs/PROGRESO.md) para el estado por día y [docs/modelo-datos-er.md](./docs/modelo-datos-er.md) para el diagrama ER.
