"""Verschickt gespendete Beispiel-Haushalte per E-Mail (Resend-API) zur manuellen Prüfung.

Es gibt bewusst keine automatische Übernahme in examples/processed/ -- jede Spende
landet erstmal als E-Mail bei Lukas, der sie wie gewohnt über
scripts/process_examples.py von Hand aufnimmt, sobald sie plausibel aussieht.
"""
from __future__ import annotations

import base64
import os

import httpx

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_SENDER = "onboarding@resend.dev"


class EmailNotConfiguredError(Exception):
    pass


class EmailSendError(Exception):
    pass


async def send_donation_email(properties: dict, csv_bytes: bytes, meta: dict) -> None:
    api_key = os.environ.get("RESEND_API_KEY")
    recipient = os.environ.get("DONATION_EMAIL_TO")
    sender = os.environ.get("DONATION_EMAIL_FROM", DEFAULT_SENDER)

    if not api_key or not recipient:
        raise EmailNotConfiguredError(
            "E-Mail-Versand ist nicht konfiguriert (RESEND_API_KEY und/oder DONATION_EMAIL_TO fehlen)."
        )

    property_lines = "\n".join(f"- {label}: {value}" for label, value in properties.items())
    text_body = (
        "Neuer gespendeter Beispiel-Haushalt über den Dynamischer Tarif Check:\n\n"
        f"{property_lines}\n\n"
        f"Zeitraum: {meta['start_date']} bis {meta['end_date']}\n"
        f"Gesamtverbrauch: {meta['total_kwh']} kWh über {meta['hours_count']} Stunden\n\n"
        "Stundenwerte (timestamp_utc,kwh) im Anhang -- vor Aufnahme wie gewohnt mit "
        "scripts/process_examples.py prüfen."
    )

    payload = {
        "from": sender,
        "to": [recipient],
        "subject": "Dynamischer Tarif Check: neuer gespendeter Datensatz",
        "text": text_body,
        "attachments": [
            {"filename": "gespendeter_verbrauch.csv", "content": base64.b64encode(csv_bytes).decode("ascii")}
        ],
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            response = await client.post(
                RESEND_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmailSendError(f"E-Mail-Versand fehlgeschlagen: {exc}") from exc
