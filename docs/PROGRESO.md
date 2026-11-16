# Progreso de MediGest

## Día 1 — Monorepositorio y servicios

Completado en la jornada anterior: estructura separada frontend/backend/infra, Compose, variables de ejemplo, scripts, endpoints operativos y documentación. Se verificaron build, arranque, comunicación y estado saludable de los tres contenedores.

## Día 2 — Modelo de datos PostgreSQL

### Alcance implementado

- [x] Modelos SQLAlchemy agrupados por dominios: tenants, identidad, pacientes, agenda, clínica y auditoría.
- [x] 20 tablas: tenants, sedes, usuarios, membresías, roles, permisos, asignaciones de roles/permisos, especialidades, médicos, servicios, pacientes, identificadores, citas, expedientes, atenciones, diagnósticos, recetas, órdenes y auditoría.
- [x] UUID, timestamps, claves primarias/foráneas, restricciones de unicidad y CHECK, e índices de consulta.
- [x] Claves foráneas compuestas para impedir referencias entre tenants y entre pacientes/expedientes/citas inconsistentes.
- [x] Relaciones ORM y registro completo de metadata para Alembic.
- [x] Migración inicial Alembic `60b458284510`.
- [x] Diagrama ER y decisiones de integridad en `docs/modelo-datos-er.md`.
- [x] Pruebas automatizadas de esquema, aislamiento referencial entre tenants y endpoints existentes.

### Validación

- `python -m pytest -q -W error::sqlalchemy.exc.SAWarning`: 8 pruebas pasaron; sin avisos del ORM. Starlette conserva un aviso deprecado de AnyIO en `TestClient`.
- El registro ORM configura correctamente y contiene las 20 tablas esperadas.
- PostgreSQL: `alembic upgrade head`, `alembic downgrade base` y nueva `upgrade head` completados.
- PostgreSQL: `alembic check` informó `No new upgrade operations detected`.
- Una inserción transaccional de cita que referenciaba un paciente de otro tenant fue rechazada por PostgreSQL; la prueba hizo rollback y no conservó datos.

### Criterios de aceptación

- [x] Están definidos todos los conjuntos de datos solicitados.
- [x] Claves, relaciones, índices, restricciones y timestamps están descritos en modelos.
- [x] El aislamiento referencial entre tenants se prueba ante un cruce de paciente/cita en SQLite y PostgreSQL.
- [x] Existe diagrama ER.
- [x] La migración inicial se aplica, revierte, reaplica y se verifica sin drift en PostgreSQL.

No se implementan APIs ni funcionalidades adicionales a la persistencia solicitada para el Día 2. RLS, autorización en backend, cifrado/HMAC de identificadores en la capa de aplicación y gestión de llaves siguen fuera del alcance de esta entrega.

## Día 3 — Multi-tenant y aislamiento

### Alcance implementado

- [x] Políticas RLS `ENABLE` y `FORCE` en tenants, sedes, membresías y roles, médicos, servicios, pacientes e identificaciones, citas, expedientes, atenciones, diagnósticos, recetas, órdenes y auditoría.
- [x] Contexto tenant transaction-local con firma HMAC validada por funciones `SECURITY DEFINER`; el rol runtime no puede leer la clave.
- [x] Separación entre la conexión runtime `medigest_app` y la conexión migradora; la cuenta runtime es `NOBYPASSRLS`, no propietaria, sin privilegios de superusuario/creación y con grants explícitos.
- [x] Script de bootstrap de roles para volúmenes nuevos y existentes, y configuración de conexiones/secreto de ejemplo.
- [x] Pruebas PostgreSQL sintéticas para listar/leer, modificar e insertar entre tenants, identidades de paciente, manipulación del contexto, privilegios y limpieza de contexto.
- [x] Migración Alembic `7f3a2c91d4e6`.

### Validación

- `docker compose config --quiet`: completado sin errores.
- `docker compose up --build -d`: completado; `db`, `backend` y `frontend` saludables.
- `alembic upgrade head`: migración aplicada en PostgreSQL.
- `alembic check`: `No new upgrade operations detected`.
- `python -m pytest -q -W error::sqlalchemy.exc.SAWarning`: 14 pruebas pasaron; un aviso deprecado de AnyIO en `starlette.testclient`.
- Las pruebas comprobaron que el rol runtime no puede leer datos ni identificaciones de otro tenant, que un cambio cruzado no afecta filas y una inserción cruzada se rechaza; manipular GUCs no da contexto válido, no se puede leer la clave ni desactivar RLS, y el contexto deja de existir al cerrar la transacción.

### Criterios de aceptación

- [x] Los datos tenant-aware tienen políticas RLS forzadas y contexto limitado a la transacción.
- [x] La cuenta de aplicación no es propietaria, superusuario ni `BYPASSRLS`; tiene permisos explícitos mínimos y no puede acceder a la clave HMAC.
- [x] Hay pruebas automatizadas PostgreSQL de lectura/listado y modificación entre tenants, con inserción cruzada rechazada.
- [x] Migración aplicada y metadata SQLAlchemy sin diferencias pendientes.

La autorización que verifica que el usuario autenticado pertenece al tenant solicitado debe implementarse antes de abrir `tenant_session`; no se implementó en esta jornada. El rol migrador conserva privilegios elevados y nunca debe usarse desde solicitudes.

## Día 4 — Autenticación y roles

### Alcance implementado

- [x] Keycloak local en Docker Compose, realm `medigest`, cliente OIDC confidencial, Authorization Code y PKCE S256.
- [x] NextAuth con comprobaciones `state` y PKCE, cookie de sesión HttpOnly, renovación del access token y cierre de sesión local más RP-Initiated Logout.
- [x] Separación de issuer público (`localhost:8080`) y endpoints de backchannel (`keycloak:8080`) para que el navegador y los contenedores alcancen sus respectivas URLs.
- [x] FastAPI valida tokens RS256 con JWKS, issuer, audiencia, expiración y claims requeridos; sincroniza el usuario mediante el `sub` del proveedor.
- [x] Endpoint `GET /api/v1/auth/me` con membresía y permisos opcionales por `X-Tenant-ID`; ruta BFF en Next.js que reenvía el access token solo desde el servidor.
- [x] Migración Alembic `9c4e7a1b2d6f` que registra los cinco roles, permisos granulares, rol de plataforma y restricción de privilegios de la cuenta runtime.
- [x] Autorización RBAC en backend basada en permisos de la base de datos. MFA obligatorio en backend para `superadmin`, `administrator` y `doctor`, verificando `amr` o `acr`.
- [x] Recuperación de acceso habilitada en Keycloak y correo local de desarrollo mediante Mailpit.
- [x] Pruebas para tokens OIDC, sincronización de identidad, permisos permitidos/denegados, aislamiento de membresía y requisito MFA.

### Validación

- `docker compose config --quiet`: completado sin errores.
- `docker compose up --build -d`: imágenes de backend y frontend construidas y servicios reiniciados.
- `alembic upgrade head`: migración aplicada; `alembic check` informó `No new upgrade operations detected`.
- Suite backend contra PostgreSQL: 26 pruebas pasaron; un aviso deprecado provino de AnyIO/Starlette.
- Build de Next.js 16.4.5 completado, incluido el chequeo TypeScript.
- Smoke test de autenticación: discovery OIDC accesible desde host y contenedor; el POST de inicio de sesión con CSRF devolvió URL Keycloak con `state`, `code_challenge` y `code_challenge_method=S256`.
- `GET /api/v1/auth/me` sin bearer devolvió `401`; `GET /api/backend/auth/me` sin sesión devolvió `401`.
- `/health` y `/ready` devolvieron `200` con estado de base de datos `ok`; la pila incluye PostgreSQL, Keycloak, Mailpit, backend y frontend.
- `npm audit --omit=dev`: cero vulnerabilidades en dependencias de producción. Quedan ocho avisos moderados en dependencias de desarrollo.

### Criterios de aceptación

- [x] El flujo del navegador usa Authorization Code + PKCE y validación de `state`.
- [x] La API verifica tokens OIDC en backend y rechaza solicitudes sin bearer.
- [x] Se registran los cinco roles y los permisos se consultan desde MediGest.
- [x] Hay pruebas automatizadas para permisos permitidos/denegados y MFA; el runtime no puede asignar el rol de plataforma.
- [x] Se ofrece recuperación de acceso mediante Keycloak y Mailpit para desarrollo.
- [ ] Completar una autenticación interactiva de extremo a extremo con un usuario Keycloak sintético que tenga TOTP, y confirmar el `amr`/`acr` emitido. Para las cuentas privilegiadas, Keycloak debe requerir/configurar TOTP; la aplicación deniega operaciones privilegiadas si el token no acredita MFA.

### Límites

- La asignación de establecimientos, membresías y roles no tiene todavía una interfaz de administración; los roles son canónicos en MediGest y no se confía en RBAC enviado por el cliente.
- El superadministrador inicial requiere asignación mediante credenciales privilegiadas, ya que el usuario runtime no puede cambiar `platform_role_id`.
- La ruta `/api/v1/auth/me` es la superficie de identidad disponible en esta etapa; la dependencia RBAC queda lista para proteger endpoints de dominio futuros.
- `npm run lint` no se pudo completar: la configuración existente `FlatCompat` con ESLint 9 falla al serializar una referencia circular. El build y el chequeo TypeScript sí pasaron.
- No se implementan módulos de negocio ni se avanza al Día 5.

## Día 5 — Diseño y estructura visual

### Alcance implementado

- [x] Tokens visuales médicos y accesibles en Tailwind/CSS, con componentes reutilizables siguiendo convenciones shadcn/ui.
- [x] Login conectado a NextAuth/Keycloak y layout autenticado a partir de la sesión real del servidor.
- [x] Navegación responsive con menú lateral móvil, barra superior, búsqueda de secciones, breadcrumbs, perfil y cierre de sesión.
- [x] Menú de navegación generado solo con permisos recibidos de FastAPI. El selector valida el UUID contra `/api/v1/auth/me` antes de guardar el contexto en `sessionStorage`.
- [x] Tabla de permisos reales del contexto, estados de carga/error/vacío, diálogo de selección, notificaciones accesibles sin métricas ni conteos ficticios.
- [x] Áreas autorizadas muestran placeholders explícitos; no se simulan pacientes, citas ni cifras de producción.
- [x] Pruebas unitarias de navegación por permisos y manejo de permisos desconocidos/sin permisos.
- [x] README actualizado con ejecución y límites de disponibilidad de selección de establecimientos.

### Validación

- `docker compose build frontend`: compilación de producción y chequeo TypeScript completados.
- `npm run test:ui` en Node.js 22: 3 pruebas pasaron; Node emitió un aviso informativo por módulo TypeScript sin `type: module`.
- `docker compose up --build -d`: PostgreSQL, Keycloak, Mailpit, backend y frontend saludables.
- Compose: `docker compose config --quiet` completado.
- Smoke tests: frontend `/` respondió HTTP 200; `/health` y `/ready` respondieron 200.
- El navegador inspeccionó la pantalla de login en escritorio y viewport móvil, y su árbol de accesibilidad; el botón de acceso redirigió a Keycloak con `state` y PKCE S256.
- `npm run lint` se intentó en el builder y falla por un problema preexistente de `FlatCompat`/ESLint 9 al serializar una referencia circular.
- No se creó una cuenta de prueba ni se verificó visualmente el layout autenticado mediante login real; los permisos se verifican en pruebas unitarias y el build.
- La lista de establecimientos no está disponible mediante API; el selector solicita el UUID al usuario y verifica la membresía en el backend antes de actualizar la navegación.

### Criterios de aceptación

- [x] Se integra una base visual responsive y accesible con controles, formularios, diálogos, tabla, breadcrumbs y estados vacíos.
- [x] La navegación se basa en permisos verificados por backend y el acceso/cierre de sesión usan Keycloak/NextAuth existentes.
- [x] Las notificaciones no simulan eventos; los módulos sin datos muestran estados explícitos.
- [x] Validar build, pruebas automatizadas y arranque de servicios; se inspeccionó la pantalla de login en navegador.
- [ ] Validar visualmente el layout autenticado mediante sesión OIDC real. No se creó una cuenta de prueba ni se simularon roles.

No se implementaron módulos de negocio en esta jornada; el Día 6 se documenta a continuación.

## Día 6 — Administración de consultorios

### Alcance implementado

- [x] Modelos y relaciones para consultorios físicos, horarios por sede, parámetros institucionales y especialidades habilitadas por establecimiento.
- [x] Migración Alembic `e64b7c2d901f` con claves foráneas compuestas, restricciones, índices, timestamps, RLS forzado y contexto de plataforma firmado; migración `c6a9e3f417b2` con permiso adicional de eliminación solo para sedes.
- [x] API `/api/v1/admin` para establecimientos, sedes, catálogo y asociaciones de especialidades, consultorios, horarios y parámetros. Las operaciones escriben eventos de auditoría sin valores de configuración o datos clínicos.
- [x] Validación de rol y ámbito en FastAPI; administradores limitados a membresías activas y superadministradores habilitados para el ámbito de plataforma. No se usa la cuenta migradora en endpoints.
- [x] BFF Next.js que conserva el access token en el servidor y reenvía contexto de tenant derivado del recurso; interfaz CRUD responsive, con tablas, formularios, selección de contexto/sede y errores accesibles.
- [x] Pruebas API para operaciones permitidas/denegadas, conflictos, validaciones y aislamiento; pruebas PostgreSQL de RLS para consultorios, horarios y parámetros, incluidas lecturas/listados tenant-scoped y escritura cruzada rechazada.
- [x] README actualizado con endpoints, comportamiento de eliminación y comandos de ejecución.

### Validación

- `docker compose config --quiet`: completado sin errores.
- `alembic upgrade head`: migración `c6a9e3f417b2` aplicada; `alembic current` reporta `c6a9e3f417b2 (head)`.
- `alembic check`: `No new upgrade operations detected`.
- Configuración ORM con `SAWarning` convertido en error: completada sin avisos de relaciones.
- Suite backend contra PostgreSQL: **36 pruebas pasaron**; un aviso deprecado proviene de AnyIO/Starlette `TestClient`.
- Build de producción Next.js 16.4.5 completado, incluido el chequeo TypeScript.
- `npm run test:ui`: **3 pruebas pasaron**.
- `docker compose up --build -d`: PostgreSQL, Keycloak, Mailpit, backend y frontend quedaron `healthy`.
- Smoke tests: `/health`, `/ready` y frontend respondieron HTTP 200; el BFF y `/api/v1/admin/tenants` rechazaron solicitudes anónimas con HTTP 401.

### Criterios de aceptación

- [x] Gestión administrativa y operaciones CRUD permitidas por auditoría/integridad implementadas en FastAPI con RBAC y alcance plataforma/tenant; los establecimientos se suspenden en lugar de eliminarse físicamente.
- [x] Pantallas Next.js conectadas al BFF y a datos persistidos, sin arrays ni conteos ficticios.
- [x] Migraciones aplicadas y metadata SQLAlchemy sin drift.
- [x] Pruebas automáticas backend y frontend ejecutadas; aislamiento RLS y denegaciones comprobados.
- [x] Stack iniciado y comunicaciones/estados de salud verificados.
- [x] README y progreso actualizados.

### Límites

- La eliminación física de un establecimiento se rechaza para preservar su historial de auditoría; debe suspenderse mediante el estado `suspended`. Sedes o especialidades referenciadas también pueden responder `409`.
- El catálogo de especialidades es global y sus altas/modificaciones/eliminaciones corresponden al superadministrador; el administrador del establecimiento habilita o deshabilita su asociación.
- No se verificó un inicio de sesión OIDC interactivo con un usuario de prueba que tenga los roles necesarios; las pruebas API inyectan claims sintéticos controlados y comprueban autorización con la base PostgreSQL real.
- No se avanza al Día 7.

## Día 7 — Usuarios y médicos

### Alcance implementado

- [x] Asignación de roles operativos por sede mediante `membership_site_roles`; se excluyen `administrator` y `superadmin` de las asignaciones por sede.
- [x] Esquemas, índices y relaciones para especialidades asociadas a médicos y disponibilidad semanal; la migración `b7d4a9c2e615` hace backfill de especialidades primarias existentes y aplica RLS forzado a las tablas nuevas.
- [x] Invitaciones con Keycloak mediante un cliente `client_credentials` dedicado, con `manage-users` y `view-users`; se envían `VERIFY_EMAIL` y `UPDATE_PASSWORD`, y a médicos también `CONFIGURE_TOTP`. PostgreSQL no almacena contraseñas y se elimina la identidad externa si falla la persistencia local.
- [x] API FastAPI con RBAC de administrador/superadministrador, filtros y paginación de usuarios y médicos, actualización de roles/estado, asociaciones médicas y CRUD de disponibilidad. Las operaciones de gestión se registran en auditoría.
- [x] `/api/v1/auth/me` acepta contexto opcional `X-Site-ID` junto con `X-Tenant-ID`; el BFF traduce los parámetros y conserva el bearer en el servidor.
- [x] Interfaz autenticada conectada a endpoints reales para invitar, buscar/paginar usuarios, gestionar roles/estado por sede, perfiles médicos, especialidades y horarios semanales.
- [x] Script idempotente para provisionar el cliente de servicio en volúmenes Keycloak persistentes anteriores a este cambio.

### Validación

- `docker compose config --quiet`: completado sin errores.
- `alembic upgrade head`: migración `b7d4a9c2e615` aplicada en PostgreSQL; `alembic check` informó `No new upgrade operations detected`.
- Suite backend completa contra PostgreSQL como `medigest_app`: **43 pruebas pasaron**, incluyendo filtros/paginación, permisos permitidos/denegados, roles por sede, aislamiento RLS y disponibilidad; un aviso deprecado provino de `starlette.testclient`/AnyIO.
- Build limpio de producción Next.js 16.4.5 completado, incluido el chequeo TypeScript.
- `npm run test:ui`: **3 pruebas pasaron**; Node informó el aviso existente de módulo TypeScript sin `type: module`.
- Keycloak: se provisionó el cliente con alcance limitado en el realm persistente; se adquirió token de servicio y la creación/solicitud de correo de activación (incluyendo `CONFIGURE_TOTP` para médico)/eliminación de una identidad sintética pasó.
- `/health` y `/ready`: HTTP 200; el frontend respondió HTTP 200 y los servicios principales de Compose quedaron saludables.

### Criterios de aceptación

- [x] Administración de usuarios con asignación de roles por sede y estado activo/suspendido.
- [x] Administración de médicos, especialidades asociadas y disponibilidad con validaciones de intervalos.
- [x] Sincronización de identidad e invitaciones de Keycloak sin contraseñas almacenadas en PostgreSQL.
- [x] Autorización de servidor, RLS en tablas nuevas, filtros/paginación y pruebas de denegación/aislamiento.
- [x] Migración aplicada y metadata SQLAlchemy sin diferencias pendientes.
- [x] UI y BFF conectados; build y pruebas disponibles ejecutadas.
- [x] README y comandos de ejecución actualizados.

### Límites

- No se ejecutó login interactivo OIDC de un usuario administrador real ni se verificó en navegador el flujo completo de aceptación de invitación; la autorización API usa claims sintéticos y Keycloak se verificó contra el realm local mediante cliente de servicio.
- En un volumen Keycloak existente, `--import-realm` no actualiza clientes del realm ya creado; ejecutar `infra/keycloak/provision-admin-client.ps1` una vez. Los volúmenes nuevos obtienen la configuración desde el JSON de realm.
- No se avanza al Día 8.

## Día 8 — Registro de pacientes

### Alcance implementado

- [x] Registro, consulta individual, búsqueda paginada y corrección de datos administrativos bajo `/api/v1/patients`, con membresía por tenant y permiso `patients:manage`.
- [x] Reglas configurables por establecimiento para tipos, longitudes, caracteres y checksum; incluye validación de cédula ecuatoriana y controles contra duplicados.
- [x] Identificaciones cifradas con Fernet y buscables/deduplicables mediante HMAC-SHA-256; contacto, dirección y contactos de emergencia cifrados. Las listas exponen solo los últimos cuatro caracteres del documento.
- [x] Correcciones auditadas con nombres de campos, evitando valores personales en `event_data`.
- [x] Migración `d8a1f4c72b90` para contactos cifrados, contactos de emergencia, índice tenant-aware, RLS forzado y grants mínimos.
- [x] Interfaz de Ventanilla conectada al backend autenticado para registrar, buscar y corregir pacientes; administradores pueden configurar reglas documentales.
- [x] `.env.example`, Compose y README incluyen las claves de cifrado/HMAC y pautas de migración/ejecución.

### Validación

- `docker compose config --quiet`: completado sin errores.
- `docker compose up --build -d`: completado; PostgreSQL, Keycloak, Mailpit, backend y frontend quedaron saludables. `/health`, `/ready` y frontend respondieron HTTP 200.
- `alembic upgrade head`: migración `d8a1f4c72b90` aplicada; `alembic current` reporta `d8a1f4c72b90 (head)` y `alembic check` informa `No new upgrade operations detected`.
- Suite backend completa contra PostgreSQL como `medigest_app`: **45 pruebas pasaron**, con una advertencia deprecada de AnyIO/Starlette `TestClient`.
- Build de producción Next.js 16.4.5 completado, incluido el chequeo TypeScript.
- `npm run test:ui`: **3 pruebas pasaron**; Node mostró el aviso existente de módulo TypeScript sin `type: module`.
- `npm run lint`: no ejecutó ESLint debido a un error en la configuración existente `FlatCompat`/`next/core-web-vitals` (error de estructura circular en ESLint 9.28.0), antes de analizar archivos.

### Criterios de aceptación

- [x] Persistencia en PostgreSQL y endpoints con RBAC, contexto transaccional y RLS por tenant.
- [x] Identificaciones duplicadas o inválidas rechazadas; las correcciones conservan identificaciones previas y registran auditoría sin valores personales.
- [x] UI de Ventanilla trabaja con datos persistidos, búsqueda y corrección; no usa arreglos estáticos como fuente de datos.
- [x] Ejecutar pruebas de API/RLS, verificación Alembic, build y validación de Compose.
- [x] README y progreso actualizados.

### Límites

- El cifrado depende de `PATIENT_DATA_ENCRYPTION_KEY` y `PATIENT_IDENTIFIER_HMAC_SECRET`; la rotación/recifrado de claves no está implementada. Las correcciones actualizan la identificación cifrada existente; la auditoría conserva los nombres de los campos, no los valores anteriores.
- Nombres y fecha de nacimiento permanecen en texto claro en las columnas existentes de `patients`; no se declara cumplimiento legal ni uso en producción con datos personales reales.
- La búsqueda por documento es exacta; nombres y apellidos permiten coincidencia parcial.
- El linter frontend no pudo analizar el código por el error de serialización circular de su configuración actual; el build de producción y las pruebas UI sí pasaron.

## Día 9 — Expediente administrativo

### Alcance implementado

- [x] Apertura idempotente de expediente administrativo por paciente y sede, con código legible y restricción única por tenant/sede.
- [x] Adjuntos limitados a tipos administrativos autorizados (identificación, comprobante de domicilio, formulario administrativo u otro) y formatos PDF/JPEG/PNG de hasta 10 MiB.
- [x] Cifrado Fernet de los adjuntos con clave propia, almacenamiento separado de los modelos clínicos, descarga autenticada y auditoría sin valores personales.
- [x] Las correcciones demográficas existentes registran los nombres de campos modificados sin copiar valores personales o clínicos al evento de auditoría.
- [x] RLS, claves foráneas compuestas y autorización por tenant, sede y permiso `patients:manage` para el expediente y sus documentos.
- [x] Ventanilla conserva `patients:manage` y permisos de agenda, sin `clinical:read` ni `clinical:write`; las rutas clínicas no están expuestas en la API.
- [x] Interfaz autenticada para abrir expedientes, asociar y descargar documentos desde la sede activa.
- [x] Migraciones Alembic `f2c8a4d19e73` y `a1b6c3e8d902`; `.env.example`, Compose y README actualizados.

### Validación

- `docker compose config --quiet`: completado sin errores.
- Build de backend y build de producción Next.js: completados; TypeScript correcto.
- Migraciones aplicadas hasta `a1b6c3e8d902 (head)`; `alembic check` informa `No new upgrade operations detected`.
- Suite backend ejecutada en PostgreSQL como `medigest_app`: **47 pruebas pasaron**, con una advertencia deprecada de AnyIO/Starlette `TestClient`.
- `docker compose up --build -d`: completado; healthchecks de backend y frontend saludables. `/health`, `/ready`, `/` respondieron HTTP 200; OpenAPI incluye la carga de adjuntos y no publica rutas clínicas.
- `npm run test:ui` encontró cero pruebas en el paquete frontend.
- `npm run lint` no se pudo ejecutar: ESLint 9 no encuentra `eslint.config.*`; este fallo de configuración preexistente impide analizar los archivos.

### Criterios de aceptación

- [x] El mismo paciente puede tener un código estable por sede; una restricción de base de datos impide duplicarlo en la misma sede.
- [x] Solo documentos del catálogo permitido y con firma de formato/extensión concordante se guardan; bytes cifrados en reposo.
- [x] Los endpoints administrativos requieren tenant, sede activa y permiso de gestión; RLS impide acceso entre tenants.
- [x] Auditoría registra creación de expediente, documentos asociados y campos demográficos corregidos, sin valores personales.
- [x] Ventanilla no recibe permisos clínicos de lectura/escritura y no existen endpoints de escritura clínica accesibles desde su módulo.
- [x] Ejecutar pruebas de API/RLS, aplicar/verificar migraciones y validar build frontend e infraestructura.

### Límites

- Los documentos se guardan como blobs cifrados en PostgreSQL; no se integra almacenamiento de objetos ni antimalware. El máximo por archivo es 10 MiB y no se implementa rotación automática de la clave de documentos.

## Día 10 — Dashboard administrativo

### Alcance implementado

- [x] Endpoint `GET /api/v1/admin/tenants/{tenant_id}/dashboard` con consultas SQL agregadas para registros de pacientes, citas por estado, disponibilidad de médicos, atenciones completadas y productividad.
- [x] Filtros inclusivos por fecha, sede y especialidad; rango máximo de 366 días y errores explícitos para fechas invertidas o especialidades no habilitadas.
- [x] Todos los agregados se limitan al tenant solicitado, usan `tenant_session` y quedan protegidos por RLS; se exige administrador de tenant o superadministrador y sede activa cuando se filtra por sede.
- [x] Productividad por médico con atenciones completadas, citas elegibles y tasa de finalización excluyendo canceladas y ausencias.
- [x] Dashboard frontend autenticado con KPIs, distribución de estados, filtros y tabla de productividad; visible solo para roles administrativos.
- [x] Pruebas de API con datos sintéticos para filtros, estados, agregaciones, aislamiento de tenant, fechas y RBAC.
- [x] README actualizado. No se requieren cambios de esquema ni migraciones.

### Validación

- `docker compose build backend` y `docker compose build frontend`: completados; el build frontend incluye verificación TypeScript.
- Suite backend completa contra PostgreSQL: **49 pruebas pasaron**, con una advertencia deprecada de AnyIO/Starlette `TestClient`.
- `npm run test:ui`: ejecutado, pero el paquete no contiene pruebas UI (0 pruebas).
- `npm run lint`: no ejecutable porque ESLint 9 no encuentra `eslint.config.*`; este problema de configuración preexistente impide analizar los archivos.
- `docker compose config --quiet` y `git diff --check`: completados sin errores.

### Criterios de aceptación

- [x] Los cinco indicadores se calculan desde las tablas existentes, sin datos simulados en runtime.
- [x] Fechas, sede y especialidad restringen los agregados; las definiciones de pacientes por sede y de disponibilidad se explican en la interfaz/README.
- [x] La consulta y cada agregado permanecen limitados al tenant, con autorización RBAC y RLS.
- [x] Pruebas de agregación verifican estados, filtros, KPIs, productividad, rechazo de fechas inválidas, denegación de no administradores y aislamiento de tenant.
- [x] Build TypeScript, configuración Compose y suite backend verificados.

### Límites

- El modelo actual no guarda sede de registro del paciente, por lo que, al filtrar sede/especialidad, el indicador de pacientes nuevos cuenta altas del período con cita en el contexto seleccionado.
- Disponibilidad representa médicos activos con un horario configurado como disponible en al menos un día del rango; no evalúa bloqueos, solapamientos ni ocupación en tiempo real.
- Los días del filtro se interpretan en UTC, no en la zona horaria configurada para la sede.

## Día 11 — Agenda de citas

### Alcance implementado

- [x] Calendario autenticado con vistas diaria, semanal y mensual; agenda filtrable por sede, médico, especialidad, servicio y estado.
- [x] Catálogo y endpoint de disponibilidad por médico, sede, especialidad y servicio. Las duraciones de servicio se aplican al generar horarios y la disponibilidad usa intervalos de 15 minutos en la zona horaria de la sede.
- [x] Creación de citas con paciente, médico, servicio opcional, inicio con zona horaria, duración, motivo administrativo, estado inicial y observaciones operativas.
- [x] Validación de paciente/médico/servicio activos, horario médico, horario de sede cuando está configurado, feriados, fechas pasadas y solapamientos de médico y paciente.
- [x] Bloqueos transaccionales por médico/paciente/fecha y feriado para impedir reservas concurrentes incompatibles.
- [x] Confirmación/cancelación de citas pendientes con auditoría; los eventos no incluyen motivo, observaciones ni datos personales.
- [x] Feriados de día completo por sede con endpoints de administración, restricción única por fecha, RLS tenant-aware y UI administrativa.
- [x] Migración Alembic `c4e8a7b19d32`; pruebas PostgreSQL con datos sintéticos y actualización del README. El módulo no crea ni modifica datos clínicos.

### Validación

- Build del backend y build frontend/TypeScript: completados.
- Migración `c4e8a7b19d32` aplicada; `alembic check` informa que no hay diferencias entre esquema y metadata.
- Suite backend completa contra PostgreSQL: **52 pruebas pasaron**, con una advertencia deprecada de AnyIO/Starlette `TestClient`.
- Pruebas UI: **4 pasaron**; Node muestra el aviso existente de paquete sin `type: module`.
- `docker compose config --quiet` y `git diff --check`: completados sin errores.

### Criterios de aceptación

- [x] Se puede navegar entre día, semana y mes y consultar citas reales de la sede seleccionada.
- [x] Disponibilidad se calcula por horarios semanales, médico, especialidad, servicio/duración y feriados; respeta zona horaria y horas de sede si están configuradas.
- [x] Reservas incluyen los campos administrativos requeridos y se rechazan cuando el médico/paciente ya tiene una cita superpuesta.
- [x] RBAC distingue lectura, gestión de citas y administración de feriados; todas las consultas usan el contexto del tenant/RLS.
- [x] Migración, pruebas backend y UI, build TypeScript y verificación Alembic ejecutados.

### Límites

- Los feriados son fechas completas, no se soportan cierres parciales ni reglas recurrentes.
- Los servicios están ligados a una sede, no a una especialidad; el filtro de especialidad restringe médicos mediante sus asociaciones configuradas.
- La agenda ofrece inicios en incrementos de 15 minutos; la API permite reservas en otros minutos si siguen dentro del horario y no se solapan.
- El motivo y las observaciones son campos administrativos/operativos; no se deben usar para diagnósticos ni notas médicas.

## Día 12 — Reprogramación y cancelación

### Alcance implementado

- [x] Transiciones explícitas: `scheduled` puede confirmarse; `scheduled` y `confirmed` pueden cancelarse o reprogramarse; los estados `checked_in`, `completed`, `cancelled` y `no_show` no admiten esos cambios.
- [x] Endpoint PATCH exige acción, motivo y `expected_version`; devuelve HTTP 409 para transiciones no permitidas, versión obsoleta, solapamientos, días feriados y horarios no disponibles.
- [x] Reprogramación puede cambiar fecha/hora y opcionalmente médico, servicio o duración; valida zona horaria, servicio, disponibilidad, horario de sede, feriados y solapamientos del médico/paciente.
- [x] Registro append-only `appointment_history` con actor, motivo y estado/campos antes/después; protegida por RLS y privilegios de solo lectura/inserción para el runtime.
- [x] Versionado optimista de cita con ORM y bloqueo de fila; bloqueos asesorados comunes serializan creación, confirmación, cancelación y reprogramación por recursos para impedir conflictos simultáneos.
- [x] Calendario actualizado con motivo requerido, selección de nuevos horarios para reprogramar, confirmación/cancelación y consulta del historial.
- [x] Migración Alembic `d1a7c9e5b204`; pruebas sintéticas para conflictos concurrentes, transiciones, historial y versiones; README actualizado.

### Validación

- Suite backend completa contra PostgreSQL: **53 pruebas pasaron**.
- Build de backend y build frontend/TypeScript: **pasaron** mediante `docker compose up --build -d`.
- Pruebas frontend: **4 pasaron**.
- Migración aplicada; `alembic current` reporta `d1a7c9e5b204 (head)` y `alembic check` no detectó diferencias.
- `docker compose config --quiet` y `git diff --check`: pasaron.
- Integración: contenedores backend y frontend saludables; `/health`, `/ready`, `/openapi.json` y frontend respondieron HTTP 200.

### Criterios de aceptación

- [x] Los cambios requieren motivo, registran historial y detectan escrituras con una versión obsoleta.
- [x] Las transiciones de estado se validan en backend; los conflictos devuelven 409 con explicación.
- [x] Reservas y cambios de horario usan locks compartidos para serializar solicitudes concurrentes del mismo médico/paciente/fecha.
- [x] La interfaz expone reprogramación, confirmación, cancelación e historial y refresca el calendario después de cambios.
- [x] Revalidar suite completa, build, migración/metadata y salud de servicios antes de cerrar la jornada.

### Límites

- Para el historial operativo se conservan los motivos introducidos por usuarios; no deben incluir datos clínicos ni identificadores personales.
- Las citas en estado terminal no se reabren mediante el endpoint de cambios de agenda.
