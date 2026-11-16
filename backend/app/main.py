from fastapi import FastAPI

from app.api.health import router as health_router
from app.domains.administration.router import router as administration_router
from app.domains.administration.users_router import router as users_administration_router
from app.domains.clinical.router import router as clinical_router
from app.domains.identity.router import router as identity_router
from app.domains.operations.router import router as operations_router
from app.domains.patients.router import router as patients_router
from app.domains.reporting.router import router as reporting_router
from app.domains.scheduling.router import router as scheduling_router

app = FastAPI(
    title="MediGest API",
    description="API base para MediGest",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(identity_router)
app.include_router(operations_router)
app.include_router(clinical_router)
app.include_router(administration_router)
app.include_router(users_administration_router)
app.include_router(patients_router)
app.include_router(reporting_router)
app.include_router(scheduling_router)
