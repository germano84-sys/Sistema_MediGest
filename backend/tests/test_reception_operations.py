from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models import Appointment
from app.domains.operations.reception import ReceptionAction, apply_reception_action


def _appointment(status: str = "scheduled") -> Appointment:
    return Appointment(
        tenant_id=uuid4(),
        site_id=uuid4(),
        patient_id=uuid4(),
        starts_at=datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
        ends_at=datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc),
        status=status,
        arrival_confirmed_at=None,
        checked_in_at=None,
        queue_entered_at=None,
    )


def test_reception_actions_record_arrival_checkin_and_queue_in_order() -> None:
    appointment = _appointment()
    arrival = datetime(2026, 1, 1, 8, 55, tzinfo=timezone.utc)
    checked_in = datetime(2026, 1, 1, 8, 57, tzinfo=timezone.utc)
    queued = datetime(2026, 1, 1, 8, 58, tzinfo=timezone.utc)

    apply_reception_action(appointment, "confirm-arrival", arrival)
    apply_reception_action(appointment, "check-in", checked_in)
    apply_reception_action(appointment, "send-to-queue", queued)

    assert appointment.status == "checked_in"
    assert appointment.arrival_confirmed_at == arrival
    assert appointment.checked_in_at == checked_in
    assert appointment.queue_entered_at == queued


@pytest.mark.parametrize(
    ("action", "expected_detail"),
    [
        ("check-in", "Confirm arrival before check-in"),
        ("send-to-queue", "Check in before sending to the queue"),
    ],
)
def test_reception_rejects_out_of_order_actions(
    action: ReceptionAction,
    expected_detail: str,
) -> None:
    with pytest.raises(HTTPException) as error:
        apply_reception_action(
            _appointment(),
            action,
            datetime.now(timezone.utc),
        )

    assert error.value.status_code == 409
    assert error.value.detail == expected_detail


def test_reception_rejects_duplicate_arrival_confirmation() -> None:
    appointment = _appointment()
    appointment.arrival_confirmed_at = datetime.now(timezone.utc)

    with pytest.raises(HTTPException, match="Arrival is already confirmed"):
        apply_reception_action(
            appointment,
            "confirm-arrival",
            datetime.now(timezone.utc),
        )
