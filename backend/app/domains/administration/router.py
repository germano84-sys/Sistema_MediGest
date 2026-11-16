from __future__ import annotations

from datetime import time
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AuditEvent,
    ClinicRoom,
    Site,
    SiteHours,
    Specialty,
    Tenant,
    TenantSetting,
    TenantSpecialty,
)
from app.db.session import engine, platform_session, tenant_session
from app.domains.administration.schemas import (
    RoomCreate,
    RoomOut,
    RoomUpdate,
    SiteCreate,
    SiteHoursCreate,
    SiteHoursOut,
    SiteHoursUpdate,
    SiteOut,
    SiteUpdate,
    SpecialtyCreate,
    SpecialtyOut,
    SpecialtyUpdate,
    TenantCreate,
    TenantOut,
    TenantSettingCreate,
    TenantSettingOut,
    TenantSettingUpdate,
    TenantSpecialtyCreate,
    TenantSpecialtyOut,
    TenantSpecialtyUpdate,
    TenantUpdate,
)
from app.domains.identity.authorization import (
    AuthorizationContext,
    load_authorization_context,
)
from app.domains.identity.router import get_verified_claims

router = APIRouter(prefix="/api/v1/admin", tags=["administration"])


def _platform_context(claims: dict[str, Any]) -> AuthorizationContext:
    context = load_authorization_context(claims, None)
    if (
        "superadmin" not in context.role_codes
        or "platform:manage" not in context.permission_codes
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator permission is required",
        )
    return context


def _tenant_context(
    claims: dict[str, Any],
    tenant_id: UUID,
) -> AuthorizationContext:
    context = load_authorization_context(claims, tenant_id)
    is_platform_admin = (
        "superadmin" in context.role_codes
        and "platform:manage" in context.permission_codes
    )
    is_tenant_admin = (
        "administrator" in context.role_codes
        and "tenant:manage" in context.permission_codes
    )
    if not (is_platform_admin or is_tenant_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant administrator permission is required",
        )
    return context


def _require_tenant(
    session: Session,
    tenant_id: UUID,
) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


def _require_site(
    session: Session,
    tenant_id: UUID,
    site_id: UUID,
) -> Site:
    site = session.scalar(
        select(Site).where(Site.tenant_id == tenant_id, Site.id == site_id)
    )
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return site


def _audit(
    session: Session,
    context: AuthorizationContext,
    *,
    tenant_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    event_data: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            id=uuid4(),
            tenant_id=tenant_id,
            actor_user_id=context.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            event_data=event_data or {},
        )
    )


def _conflict(exc: IntegrityError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="The resource conflicts with existing data or is still in use",
    )


def _ensure_values(values: dict[str, Any]) -> None:
    if not values:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one field must be provided",
        )


def _validate_hours(
    *,
    is_closed: bool,
    opens_at: time | None,
    closes_at: time | None,
) -> None:
    if is_closed:
        if opens_at is not None or closes_at is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Closed days cannot define opening hours",
            )
        return
    if opens_at is None or closes_at is None or closes_at <= opens_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Closing time must be after opening time",
        )


@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(
    claims: dict[str, Any] = Depends(get_verified_claims),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Tenant]:
    _platform_context(claims)
    with platform_session() as session:
        return list(
            session.scalars(
                select(Tenant).order_by(Tenant.name).limit(limit).offset(offset)
            ).all()
        )


@router.post(
    "/tenants",
    response_model=TenantOut,
    status_code=status.HTTP_201_CREATED,
)
def create_tenant(
    payload: TenantCreate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> Tenant:
    context = _platform_context(claims)
    tenant = Tenant(name=payload.name, slug=payload.slug, status="active")
    try:
        with platform_session() as session:
            session.add(tenant)
            session.flush()
            _audit(
                session,
                context,
                tenant_id=tenant.id,
                action="create",
                entity_type="tenant",
                entity_id=tenant.id,
                event_data={"slug": tenant.slug},
            )
            session.flush()
    except IntegrityError as exc:
        raise _conflict(exc) from exc
    return tenant


@router.get("/tenants/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> Tenant:
    _platform_context(claims)
    with platform_session() as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
def update_tenant(
    tenant_id: UUID,
    payload: TenantUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> Tenant:
    context = _platform_context(claims)
    values = payload.model_dump(exclude_unset=True)
    _ensure_values(values)
    try:
        with platform_session() as session:
            tenant = session.get(Tenant, tenant_id)
            if tenant is None:
                raise HTTPException(status_code=404, detail="Tenant not found")
            for key, value in values.items():
                setattr(tenant, key, value)
            _audit(
                session,
                context,
                tenant_id=tenant.id,
                action="update",
                entity_type="tenant",
                entity_id=tenant.id,
                event_data={"fields": sorted(values)},
            )
            session.flush()
            return tenant
    except IntegrityError as exc:
        raise _conflict(exc) from exc


@router.delete(
    "/tenants/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_tenant(
    tenant_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> None:
    context = _platform_context(claims)
    with platform_session() as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        _audit(
            session,
            context,
            tenant_id=tenant.id,
            action="delete_blocked",
            entity_type="tenant",
            entity_id=tenant.id,
            event_data={"reason": "audit_retention"},
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Tenants are retained for audit; suspend the tenant instead",
    )


@router.get("/specialties", response_model=list[SpecialtyOut])
def list_specialties(
    claims: dict[str, Any] = Depends(get_verified_claims),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Specialty]:
    load_authorization_context(claims, None)
    with Session(engine) as session:
        return list(
            session.scalars(
                select(Specialty)
                .order_by(Specialty.name)
                .limit(limit)
                .offset(offset)
            ).all()
        )


@router.post(
    "/specialties",
    response_model=SpecialtyOut,
    status_code=status.HTTP_201_CREATED,
)
def create_specialty(
    payload: SpecialtyCreate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> Specialty:
    context = _platform_context(claims)
    specialty = Specialty(
        code=payload.code,
        name=payload.name,
        is_active=payload.is_active,
    )
    try:
        with platform_session() as session:
            session.add(specialty)
            session.flush()
            _audit(
                session,
                context,
                tenant_id=None,
                action="create",
                entity_type="specialty",
                entity_id=specialty.id,
                event_data={"code": specialty.code},
            )
    except IntegrityError as exc:
        raise _conflict(exc) from exc
    return specialty


@router.patch("/specialties/{specialty_id}", response_model=SpecialtyOut)
def update_specialty(
    specialty_id: UUID,
    payload: SpecialtyUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> Specialty:
    context = _platform_context(claims)
    values = payload.model_dump(exclude_unset=True)
    _ensure_values(values)
    try:
        with platform_session() as session:
            specialty = session.get(Specialty, specialty_id)
            if specialty is None:
                raise HTTPException(status_code=404, detail="Specialty not found")
            for key, value in values.items():
                setattr(specialty, key, value)
            _audit(
                session,
                context,
                tenant_id=None,
                action="update",
                entity_type="specialty",
                entity_id=specialty.id,
                event_data={"fields": sorted(values)},
            )
            session.flush()
            return specialty
    except IntegrityError as exc:
        raise _conflict(exc) from exc


@router.delete(
    "/specialties/{specialty_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_specialty(
    specialty_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> None:
    context = _platform_context(claims)
    try:
        with platform_session() as session:
            specialty = session.get(Specialty, specialty_id)
            if specialty is None:
                raise HTTPException(status_code=404, detail="Specialty not found")
            _audit(
                session,
                context,
                tenant_id=None,
                action="delete",
                entity_type="specialty",
                entity_id=specialty.id,
                event_data={"code": specialty.code},
            )
            session.delete(specialty)
            session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Specialty is still assigned or referenced",
        ) from exc


@router.get(
    "/tenants/{tenant_id}/sites",
    response_model=list[SiteOut],
)
def list_sites(
    tenant_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Site]:
    _tenant_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        _require_tenant(session, tenant_id)
        return list(
            session.scalars(
                select(Site)
                .where(Site.tenant_id == tenant_id)
                .order_by(Site.name)
                .limit(limit)
                .offset(offset)
            ).all()
        )


@router.post(
    "/tenants/{tenant_id}/sites",
    response_model=SiteOut,
    status_code=status.HTTP_201_CREATED,
)
def create_site(
    tenant_id: UUID,
    payload: SiteCreate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> Site:
    context = _tenant_context(claims, tenant_id)
    site = Site(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        timezone=payload.timezone,
        is_active=payload.is_active,
    )
    try:
        with tenant_session(tenant_id) as session:
            _require_tenant(session, tenant_id)
            session.add(site)
            session.flush()
            _audit(
                session,
                context,
                tenant_id=tenant_id,
                action="create",
                entity_type="site",
                entity_id=site.id,
                event_data={"code": site.code},
            )
    except IntegrityError as exc:
        raise _conflict(exc) from exc
    return site


@router.patch(
    "/tenants/{tenant_id}/sites/{site_id}",
    response_model=SiteOut,
)
def update_site(
    tenant_id: UUID,
    site_id: UUID,
    payload: SiteUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> Site:
    context = _tenant_context(claims, tenant_id)
    values = payload.model_dump(exclude_unset=True)
    _ensure_values(values)
    try:
        with tenant_session(tenant_id) as session:
            site = _require_site(session, tenant_id, site_id)
            for key, value in values.items():
                setattr(site, key, value)
            _audit(
                session,
                context,
                tenant_id=tenant_id,
                action="update",
                entity_type="site",
                entity_id=site.id,
                event_data={"fields": sorted(values)},
            )
            session.flush()
            return site
    except IntegrityError as exc:
        raise _conflict(exc) from exc


@router.delete(
    "/tenants/{tenant_id}/sites/{site_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_site(
    tenant_id: UUID,
    site_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> None:
    context = _tenant_context(claims, tenant_id)
    try:
        with tenant_session(tenant_id) as session:
            site = _require_site(session, tenant_id, site_id)
            _audit(
                session,
                context,
                tenant_id=tenant_id,
                action="delete",
                entity_type="site",
                entity_id=site.id,
                event_data={"code": site.code},
            )
            session.delete(site)
            session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Site is still referenced; deactivate it instead",
        ) from exc


@router.get(
    "/tenants/{tenant_id}/specialties",
    response_model=list[TenantSpecialtyOut],
)
def list_tenant_specialties(
    tenant_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> list[dict[str, Any]]:
    _tenant_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        _require_tenant(session, tenant_id)
        rows = session.execute(
            select(
                TenantSpecialty.id,
                TenantSpecialty.tenant_id,
                Specialty.id.label("specialty_id"),
                Specialty.code,
                Specialty.name,
                TenantSpecialty.is_active,
            )
            .join(Specialty, Specialty.id == TenantSpecialty.specialty_id)
            .where(TenantSpecialty.tenant_id == tenant_id)
            .order_by(Specialty.name)
        ).mappings()
        return [dict(row) for row in rows]


@router.post(
    "/tenants/{tenant_id}/specialties",
    response_model=TenantSpecialtyOut,
    status_code=status.HTTP_201_CREATED,
)
def add_tenant_specialty(
    tenant_id: UUID,
    payload: TenantSpecialtyCreate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> dict[str, Any]:
    context = _tenant_context(claims, tenant_id)
    link = TenantSpecialty(
        tenant_id=tenant_id,
        specialty_id=payload.specialty_id,
        is_active=payload.is_active,
    )
    try:
        with tenant_session(tenant_id) as session:
            _require_tenant(session, tenant_id)
            specialty = session.get(Specialty, payload.specialty_id)
            if specialty is None or not specialty.is_active:
                raise HTTPException(
                    status_code=404,
                    detail="Active catalog specialty not found",
                )
            session.add(link)
            session.flush()
            _audit(
                session,
                context,
                tenant_id=tenant_id,
                action="create",
                entity_type="tenant_specialty",
                entity_id=link.id,
                event_data={"specialty_id": str(link.specialty_id)},
            )
            return {
                "id": link.id,
                "tenant_id": tenant_id,
                "specialty_id": specialty.id,
                "code": specialty.code,
                "name": specialty.name,
                "is_active": link.is_active,
            }
    except IntegrityError as exc:
        raise _conflict(exc) from exc


@router.patch(
    "/tenants/{tenant_id}/specialties/{link_id}",
    response_model=TenantSpecialtyOut,
)
def update_tenant_specialty(
    tenant_id: UUID,
    link_id: UUID,
    payload: TenantSpecialtyUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> dict[str, Any]:
    context = _tenant_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        link = session.scalar(
            select(TenantSpecialty).where(
                TenantSpecialty.tenant_id == tenant_id,
                TenantSpecialty.id == link_id,
            )
        )
        if link is None:
            raise HTTPException(status_code=404, detail="Tenant specialty not found")
        link.is_active = payload.is_active
        specialty = session.get(Specialty, link.specialty_id)
        if specialty is None:
            raise HTTPException(status_code=404, detail="Specialty not found")
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="update",
            entity_type="tenant_specialty",
            entity_id=link.id,
            event_data={"is_active": link.is_active},
        )
        session.flush()
        return {
            "id": link.id,
            "tenant_id": tenant_id,
            "specialty_id": specialty.id,
            "code": specialty.code,
            "name": specialty.name,
            "is_active": link.is_active,
        }


@router.delete(
    "/tenants/{tenant_id}/specialties/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_tenant_specialty(
    tenant_id: UUID,
    link_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> None:
    context = _tenant_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        link = session.scalar(
            select(TenantSpecialty).where(
                TenantSpecialty.tenant_id == tenant_id,
                TenantSpecialty.id == link_id,
            )
        )
        if link is None:
            raise HTTPException(status_code=404, detail="Tenant specialty not found")
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="delete",
            entity_type="tenant_specialty",
            entity_id=link.id,
            event_data={"specialty_id": str(link.specialty_id)},
        )
        session.delete(link)


@router.get(
    "/tenants/{tenant_id}/sites/{site_id}/rooms",
    response_model=list[RoomOut],
)
def list_rooms(
    tenant_id: UUID,
    site_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> list[ClinicRoom]:
    _tenant_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        _require_site(session, tenant_id, site_id)
        return list(
            session.scalars(
                select(ClinicRoom)
                .where(
                    ClinicRoom.tenant_id == tenant_id,
                    ClinicRoom.site_id == site_id,
                )
                .order_by(ClinicRoom.name)
            ).all()
        )


@router.post(
    "/tenants/{tenant_id}/sites/{site_id}/rooms",
    response_model=RoomOut,
    status_code=status.HTTP_201_CREATED,
)
def create_room(
    tenant_id: UUID,
    site_id: UUID,
    payload: RoomCreate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> ClinicRoom:
    context = _tenant_context(claims, tenant_id)
    room = ClinicRoom(
        tenant_id=tenant_id,
        site_id=site_id,
        code=payload.code,
        name=payload.name,
        room_type=payload.room_type,
        is_active=payload.is_active,
    )
    try:
        with tenant_session(tenant_id) as session:
            _require_site(session, tenant_id, site_id)
            session.add(room)
            session.flush()
            _audit(
                session,
                context,
                tenant_id=tenant_id,
                action="create",
                entity_type="clinic_room",
                entity_id=room.id,
                event_data={"site_id": str(site_id), "code": room.code},
            )
    except IntegrityError as exc:
        raise _conflict(exc) from exc
    return room


@router.patch(
    "/tenants/{tenant_id}/sites/{site_id}/rooms/{room_id}",
    response_model=RoomOut,
)
def update_room(
    tenant_id: UUID,
    site_id: UUID,
    room_id: UUID,
    payload: RoomUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> ClinicRoom:
    context = _tenant_context(claims, tenant_id)
    values = payload.model_dump(exclude_unset=True)
    _ensure_values(values)
    try:
        with tenant_session(tenant_id) as session:
            _require_site(session, tenant_id, site_id)
            room = session.scalar(
                select(ClinicRoom).where(
                    ClinicRoom.tenant_id == tenant_id,
                    ClinicRoom.site_id == site_id,
                    ClinicRoom.id == room_id,
                )
            )
            if room is None:
                raise HTTPException(status_code=404, detail="Room not found")
            for key, value in values.items():
                setattr(room, key, value)
            _audit(
                session,
                context,
                tenant_id=tenant_id,
                action="update",
                entity_type="clinic_room",
                entity_id=room.id,
                event_data={"fields": sorted(values)},
            )
            session.flush()
            return room
    except IntegrityError as exc:
        raise _conflict(exc) from exc


@router.delete(
    "/tenants/{tenant_id}/sites/{site_id}/rooms/{room_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_room(
    tenant_id: UUID,
    site_id: UUID,
    room_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> None:
    context = _tenant_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        _require_site(session, tenant_id, site_id)
        room = session.scalar(
            select(ClinicRoom).where(
                ClinicRoom.tenant_id == tenant_id,
                ClinicRoom.site_id == site_id,
                ClinicRoom.id == room_id,
            )
        )
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="delete",
            entity_type="clinic_room",
            entity_id=room.id,
            event_data={"code": room.code},
        )
        session.delete(room)


@router.get(
    "/tenants/{tenant_id}/sites/{site_id}/hours",
    response_model=list[SiteHoursOut],
)
def list_site_hours(
    tenant_id: UUID,
    site_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> list[SiteHours]:
    _tenant_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        _require_site(session, tenant_id, site_id)
        return list(
            session.scalars(
                select(SiteHours)
                .where(
                    SiteHours.tenant_id == tenant_id,
                    SiteHours.site_id == site_id,
                )
                .order_by(SiteHours.weekday)
            ).all()
        )


@router.post(
    "/tenants/{tenant_id}/sites/{site_id}/hours",
    response_model=SiteHoursOut,
    status_code=status.HTTP_201_CREATED,
)
def create_site_hours(
    tenant_id: UUID,
    site_id: UUID,
    payload: SiteHoursCreate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> SiteHours:
    context = _tenant_context(claims, tenant_id)
    hours = SiteHours(
        tenant_id=tenant_id,
        site_id=site_id,
        weekday=payload.weekday,
        opens_at=payload.opens_at,
        closes_at=payload.closes_at,
        is_closed=payload.is_closed,
    )
    try:
        with tenant_session(tenant_id) as session:
            _require_site(session, tenant_id, site_id)
            session.add(hours)
            session.flush()
            _audit(
                session,
                context,
                tenant_id=tenant_id,
                action="create",
                entity_type="site_hours",
                entity_id=hours.id,
                event_data={"site_id": str(site_id), "weekday": hours.weekday},
            )
    except IntegrityError as exc:
        raise _conflict(exc) from exc
    return hours


@router.patch(
    "/tenants/{tenant_id}/sites/{site_id}/hours/{hours_id}",
    response_model=SiteHoursOut,
)
def update_site_hours(
    tenant_id: UUID,
    site_id: UUID,
    hours_id: UUID,
    payload: SiteHoursUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> SiteHours:
    context = _tenant_context(claims, tenant_id)
    values = payload.model_dump(exclude_unset=True)
    _ensure_values(values)
    try:
        with tenant_session(tenant_id) as session:
            _require_site(session, tenant_id, site_id)
            hours = session.scalar(
                select(SiteHours).where(
                    SiteHours.tenant_id == tenant_id,
                    SiteHours.site_id == site_id,
                    SiteHours.id == hours_id,
                )
            )
            if hours is None:
                raise HTTPException(status_code=404, detail="Opening hours not found")
            merged = {
                "opens_at": hours.opens_at,
                "closes_at": hours.closes_at,
                "is_closed": hours.is_closed,
                **values,
            }
            _validate_hours(**merged)
            for key, value in values.items():
                setattr(hours, key, value)
            _audit(
                session,
                context,
                tenant_id=tenant_id,
                action="update",
                entity_type="site_hours",
                entity_id=hours.id,
                event_data={"fields": sorted(values)},
            )
            session.flush()
            return hours
    except IntegrityError as exc:
        raise _conflict(exc) from exc


@router.delete(
    "/tenants/{tenant_id}/sites/{site_id}/hours/{hours_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_site_hours(
    tenant_id: UUID,
    site_id: UUID,
    hours_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> None:
    context = _tenant_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        _require_site(session, tenant_id, site_id)
        hours = session.scalar(
            select(SiteHours).where(
                SiteHours.tenant_id == tenant_id,
                SiteHours.site_id == site_id,
                SiteHours.id == hours_id,
            )
        )
        if hours is None:
            raise HTTPException(status_code=404, detail="Opening hours not found")
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="delete",
            entity_type="site_hours",
            entity_id=hours.id,
            event_data={"weekday": hours.weekday},
        )
        session.delete(hours)


@router.get(
    "/tenants/{tenant_id}/settings",
    response_model=list[TenantSettingOut],
)
def list_tenant_settings(
    tenant_id: UUID,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> list[TenantSetting]:
    _tenant_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        _require_tenant(session, tenant_id)
        return list(
            session.scalars(
                select(TenantSetting)
                .where(TenantSetting.tenant_id == tenant_id)
                .order_by(TenantSetting.key)
            ).all()
        )


@router.post(
    "/tenants/{tenant_id}/settings",
    response_model=TenantSettingOut,
    status_code=status.HTTP_201_CREATED,
)
def create_tenant_setting(
    tenant_id: UUID,
    payload: TenantSettingCreate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> TenantSetting:
    context = _tenant_context(claims, tenant_id)
    setting = TenantSetting(
        tenant_id=tenant_id,
        key=payload.key,
        value=payload.value,
    )
    try:
        with tenant_session(tenant_id) as session:
            _require_tenant(session, tenant_id)
            session.add(setting)
            session.flush()
            _audit(
                session,
                context,
                tenant_id=tenant_id,
                action="create",
                entity_type="tenant_setting",
                entity_id=setting.id,
                event_data={"key": setting.key},
            )
    except IntegrityError as exc:
        raise _conflict(exc) from exc
    return setting


@router.patch(
    "/tenants/{tenant_id}/settings/{key}",
    response_model=TenantSettingOut,
)
def update_tenant_setting(
    tenant_id: UUID,
    key: str,
    payload: TenantSettingUpdate,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> TenantSetting:
    context = _tenant_context(claims, tenant_id)
    try:
        with tenant_session(tenant_id) as session:
            setting = session.scalar(
                select(TenantSetting).where(
                    TenantSetting.tenant_id == tenant_id,
                    TenantSetting.key == key,
                )
            )
            if setting is None:
                raise HTTPException(status_code=404, detail="Institutional setting not found")
            setting.value = payload.value
            _audit(
                session,
                context,
                tenant_id=tenant_id,
                action="update",
                entity_type="tenant_setting",
                entity_id=setting.id,
                event_data={"key": setting.key},
            )
            session.flush()
            return setting
    except IntegrityError as exc:
        raise _conflict(exc) from exc


@router.delete(
    "/tenants/{tenant_id}/settings/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_tenant_setting(
    tenant_id: UUID,
    key: str,
    claims: dict[str, Any] = Depends(get_verified_claims),
) -> None:
    context = _tenant_context(claims, tenant_id)
    with tenant_session(tenant_id) as session:
        setting = session.scalar(
            select(TenantSetting).where(
                TenantSetting.tenant_id == tenant_id,
                TenantSetting.key == key,
            )
        )
        if setting is None:
            raise HTTPException(status_code=404, detail="Institutional setting not found")
        _audit(
            session,
            context,
            tenant_id=tenant_id,
            action="delete",
            entity_type="tenant_setting",
            entity_id=setting.id,
            event_data={"key": setting.key},
        )
        session.delete(setting)
