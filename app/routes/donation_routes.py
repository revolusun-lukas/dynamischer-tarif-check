"""Route, um einen bereits importierten Verbrauch als Beispiel-Haushalt vorzuschlagen (per E-Mail)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.notifications.email import EmailNotConfiguredError, EmailSendError, send_donation_email
from app.schemas import DonateRequest, DonateResponse
from app.session_store import SessionNotFoundError, store

router = APIRouter(prefix="/api", tags=["donation"])


@router.post("/donate", response_model=DonateResponse)
async def donate(req: DonateRequest) -> DonateResponse:
    try:
        session = store.get(req.session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    if session.hourly_kwh is None or session.hourly_kwh.empty:
        raise HTTPException(400, "Kein importierter Verbrauch für diese Sitzung gefunden.")

    hourly_kwh = session.hourly_kwh
    csv_bytes = (
        hourly_kwh.rename("kwh").rename_axis("timestamp_utc").reset_index().to_csv(index=False).encode("utf-8")
    )

    properties = {
        "Haushaltsgröße": req.haushaltsgroesse,
        "Balkonkraftwerk": "Ja" if req.balkonkraftwerk else "Nein",
        "PV auf dem Dach": "Ja" if req.pv else "Nein",
        "Batteriespeicher": "Ja" if req.speicher else "Nein",
        "Wärmepumpe": "Ja" if req.waermepumpe else "Nein",
        "Durchlauferhitzer": "Ja" if req.durchlauferhitzer else "Nein",
        "Elektroauto": "Ja" if req.elektroauto else "Nein",
    }
    meta = {
        "start_date": hourly_kwh.index.min().isoformat(),
        "end_date": hourly_kwh.index.max().isoformat(),
        "total_kwh": round(float(hourly_kwh.sum()), 3),
        "hours_count": int(len(hourly_kwh)),
    }

    try:
        await send_donation_email(properties, csv_bytes, meta)
    except EmailNotConfiguredError as exc:
        raise HTTPException(503, str(exc)) from exc
    except EmailSendError as exc:
        raise HTTPException(502, str(exc)) from exc

    return DonateResponse(message="Danke! Dein Datensatz wurde übermittelt und wird geprüft.")
