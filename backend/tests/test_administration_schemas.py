import pytest
from pydantic import ValidationError

from app.domains.administration.schemas import (
    RoomCreate,
    SiteCreate,
    SiteHoursCreate,
    SiteHoursUpdate,
    SpecialtyCreate,
    TenantCreate,
    TenantSettingCreate,
    TenantUpdate,
)


def test_site_code_is_normalized_and_timezone_is_validated() -> None:
    site = SiteCreate(code="north_01", name="North clinic", timezone="America/Guayaquil")

    assert site.code == "NORTH_01"
    assert site.timezone == "America/Guayaquil"

    with pytest.raises(ValidationError):
        SiteCreate(code="NORTH", name="North clinic", timezone="Mars/Olympus")


def test_tenant_and_specialty_codes_reject_untrusted_formats() -> None:
    with pytest.raises(ValidationError):
        TenantCreate(name="Clinic", slug="../other")
    with pytest.raises(ValidationError):
        SpecialtyCreate(code="invalid code", name="Specialty")
    with pytest.raises(ValidationError):
        TenantUpdate(status="deleted")


def test_room_fields_are_bounded_and_validated() -> None:
    room = RoomCreate(code="CONSULT-01", name="Consultation room")

    assert room.room_type == "consultation"
    with pytest.raises(ValidationError):
        RoomCreate(code="bad code", name="Room")


def test_opening_hours_require_valid_same_day_interval() -> None:
    with pytest.raises(ValidationError):
        SiteHoursCreate(weekday=0, opens_at="17:00", closes_at="09:00")
    with pytest.raises(ValidationError):
        SiteHoursCreate(weekday=7, is_closed=True)

    closed_day = SiteHoursCreate(weekday=6, is_closed=True)
    closed_patch = SiteHoursUpdate(
        is_closed=True,
        opens_at=None,
        closes_at=None,
    )
    assert closed_day.is_closed
    assert closed_patch.is_closed


def test_institution_settings_reject_credentials_and_large_values() -> None:
    with pytest.raises(ValidationError):
        TenantSettingCreate(key="smtp.password", value={"enabled": True})
    with pytest.raises(ValidationError):
        TenantSettingCreate(
            key="theme",
            value={"provider": {"api_token": "do-not-store"}},
        )
    with pytest.raises(ValidationError):
        TenantSettingCreate(key="theme", value={"text": "x" * 9000})

    setting = TenantSettingCreate(key="locale.timezone", value={"name": "es-EC"})
    assert setting.value == {"name": "es-EC"}
