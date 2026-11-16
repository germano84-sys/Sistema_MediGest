from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import HTTPException

from app.db.models import Appointment

ServiceAction = Literal[
    "assign-room",
    "start-preparation",
    "mark-ready",
    "start-attention",
    "finish",
]
ServiceStatus = Literal["pending", "preparing", "ready", "completed"]


def apply_service_action(
    appointment: Appointment,
    action: ServiceAction,
    occurred_at: datetime,
    room_id: UUID | None = None,
) -> None:
    if action == "assign-room":
        if appointment.service_status == "completed" or appointment.attention_started_at:
            raise HTTPException(
                status_code=409,
                detail="Room assignment cannot change after attention has started",
            )
        if room_id is None:
            raise HTTPException(status_code=422, detail="room_id is required")
        appointment.service_room_id = room_id
        return

    if action == "start-preparation":
        if appointment.service_status != "pending":
            raise HTTPException(status_code=409, detail="Only pending visits can be prepared")
        if appointment.service_room_id is None:
            raise HTTPException(status_code=409, detail="Assign a room before preparation")
        appointment.service_status = "preparing"
        appointment.preparation_started_at = occurred_at
        return

    if action == "mark-ready":
        if appointment.service_status != "preparing":
            raise HTTPException(
                status_code=409,
                detail="Only visits in preparation can be marked ready",
            )
        appointment.service_status = "ready"
        appointment.ready_at = occurred_at
        return

    if action == "start-attention":
        if appointment.service_status != "ready":
            raise HTTPException(status_code=409, detail="Only ready visits can start attention")
        if appointment.service_room_id is None:
            raise HTTPException(status_code=409, detail="Assign a room before attention")
        if appointment.attention_started_at is not None:
            raise HTTPException(status_code=409, detail="Attention has already started")
        appointment.attention_started_at = occurred_at
        return

    if appointment.service_status != "ready":
        raise HTTPException(status_code=409, detail="Only ready visits can be completed")
    if appointment.attention_started_at is None:
        raise HTTPException(
            status_code=409,
            detail="Start attention before completing the visit",
        )
    appointment.service_status = "completed"
    appointment.attention_completed_at = occurred_at
