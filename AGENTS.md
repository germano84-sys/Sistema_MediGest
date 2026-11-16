# Guía de contribución para agentes

## Alcance del repositorio

- Mantener frontend, backend e infraestructura separados en el monorepo.
- Organizar el backend por dominios bajo `backend/app/domains/`.
- No añadir funcionalidades de negocio ni datos personales/clínicos sin requerimiento explícito.
- No usar datos clínicos reales en pruebas, ejemplos, logs o herramientas.

## Convenciones

- Frontend: Next.js App Router, TypeScript y Tailwind CSS.
- Backend: FastAPI, Pydantic Settings, SQLAlchemy 2.x y Alembic.
- Los endpoints de API nuevos deben ubicarse bajo `/api/v1`; `/health` y `/ready` son comprobaciones operativas.
- Mantener errores explícitos y no registrar secretos o información clínica.
- Añadir pruebas automatizadas para cambios de comportamiento y migraciones para cambios de esquema.
- Mantener `.env` local fuera del control de versiones; actualizar `.env.example` cuando cambien las variables de configuración.

## Validación

- Backend: `python -m pytest` desde `backend/`.
- Infraestructura: `docker compose config` y arranque con `docker compose up --build`.
- Revisar `/health`, `/ready`, el frontend y el estado de salud de los servicios antes de declarar integración verificada.
