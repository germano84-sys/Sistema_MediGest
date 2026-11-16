from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DashboardModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DashboardSiteOption(DashboardModel):
    id: UUID
    code: str
    name: str


class DashboardSpecialtyOption(DashboardModel):
    id: UUID
    code: str
    name: str


class AppointmentStatusCount(DashboardModel):
    status: str
    count: int


class DoctorProductivity(DashboardModel):
    doctor_id: UUID
    doctor_name: str
    completed_encounters: int
    appointments_total: int
    completed_appointments: int
    completion_rate_percent: float


class DashboardFilters(DashboardModel):
    start_date: date
    end_date: date
    site_id: UUID | None
    specialty_id: UUID | None


class AdminDashboard(DashboardModel):
    generated_at: datetime
    filters: DashboardFilters
    sites: list[DashboardSiteOption]
    specialties: list[DashboardSpecialtyOption]
    patients_registered: int
    appointments_by_status: list[AppointmentStatusCount]
    available_doctors: int
    completed_encounters: int
    productivity: list[DoctorProductivity]
