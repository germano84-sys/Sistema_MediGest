from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models import Appointment
from app.domains.operations.service_queue import ServiceAction, apply_service_action


def _queued_appointment() -> Appointment:
    return Appointment(
        tenant_id=uuid4(),
        site_id=uuid4(),
        patient_id=uuid4(),
        starts_at=datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
        ends_at=datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc),
        status="checked_in",
        queue_entered_at=datetime(2026, 1, 1, 8, 55, tzinfo=timezone.utc),
        service_status="pending",
        service_room_id=None,
        preparation_started_at=None,
        ready_at=None,
        attention_started_at=None,
        attention_completed_at=None,
    )


def test_service_actions_record_room_preparation_and_attention_times() -> None:
    appointment = _queued_appointment()
    room_id = uuid4()
    times = [
        datetime(2026, 1, 1, 8, 56, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 8, 57, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 9, 2, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 9, 5, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 9, 25, tzinfo=timezone.utc),
    ]

    apply_service_action(appointment, "assign-room", times[0], room_id)
    apply_service_action(appointment, "start-preparation", times[1])
    apply_service_action(appointment, "mark-ready", times[2])
    apply_service_action(appointment, "start-attention", times[3])
    apply_service_action(appointment, "finish", times[4])

    assert appointment.service_status == "completed"
    assert appointment.service_room_id == room_id
    assert appointment.preparation_started_at == times[1]
    assert appointment.ready_at == times[2]
    assert appointment.attention_started_at == times[3]
    assert appointment.attention_completed_at == times[4]


@pytest.mark.parametrize(
    ("action", "expected_detail"),
    [
        ("start-preparation", "Assign a room before preparation"),
        ("mark-ready", "Only visits in preparation can be marked ready"),
        ("finish", "Only ready visits can be completed"),
    ],
)
def test_service_rejects_out_of_order_actions(
    action: ServiceAction,
    expected_detail: str,
) -> None:
    with pytest.raises(HTTPException) as error:
        apply_service_action(
            _queued_appointment(),
            action,
            datetime.now(timezone.utc),
        )

    assert error.value.status_code == 409
    assert error.value.detail == expected_detail


def test_service_does_not_change_room_after_attention_starts() -> None:
    appointment = _queued_appointment()
    appointment.service_room_id = uuid4()
    appointment.attention_started_at = datetime.now(timezone.utc)

    with pytest.raises(HTTPException, match="Room assignment cannot change"):
        apply_service_action(
            appointment,
            "assign-room",
            datetime.now(timezone.utc),
            uuid4(),
        )
