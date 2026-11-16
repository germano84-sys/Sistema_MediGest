from datetime import datetime
from typing import Literal

from fastapi import HTTPException

from app.db.models import Appointment

ReceptionAction = Literal["confirm-arrival", "check-in", "send-to-queue"]


def apply_reception_action(
    appointment: Appointment,
    action: ReceptionAction,
    occurred_at: datetime,
) -> None:
    if action == "confirm-arrival":
        if appointment.status not in {"scheduled", "confirmed"}:
            raise HTTPException(status_code=409, detail="Appointment cannot confirm arrival")
        if appointment.arrival_confirmed_at is not None:
            raise HTTPException(status_code=409, detail="Arrival is already confirmed")
        appointment.arrival_confirmed_at = occurred_at
        return

    if action == "check-in":
        if appointment.arrival_confirmed_at is None:
            raise HTTPException(status_code=409, detail="Confirm arrival before check-in")
        if appointment.status not in {"scheduled", "confirmed"}:
            raise HTTPException(status_code=409, detail="Appointment cannot be checked in")
        if appointment.checked_in_at is not None:
            raise HTTPException(status_code=409, detail="Appointment is already checked in")
        appointment.status = "checked_in"
        appointment.checked_in_at = occurred_at
        return

    if appointment.status != "checked_in" or appointment.checked_in_at is None:
        raise HTTPException(status_code=409, detail="Check in before sending to the queue")
    if appointment.queue_entered_at is not None:
        raise HTTPException(status_code=409, detail="Appointment is already in the queue")
    appointment.queue_entered_at = occurred_at
