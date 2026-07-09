"""Routen für die kuratierten Beispiel-Haushalte (Alternative zum eigenen CSV-Upload)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.importer import examples
from app.schemas import ExampleHousehold, ExampleListResponse, ImportConfirmResponse
from app.session_store import store

router = APIRouter(prefix="/api/examples", tags=["examples"])


@router.get("", response_model=ExampleListResponse)
async def list_examples() -> ExampleListResponse:
    rows = examples.load_registry()
    return ExampleListResponse(examples=[ExampleHousehold(**row) for row in rows])


@router.post("/{example_id}/select", response_model=ImportConfirmResponse)
async def select_example(example_id: str) -> ImportConfirmResponse:
    try:
        hourly_kwh = examples.load_example_series(example_id)
    except examples.ExampleNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    session_id, session = store.create()
    session.hourly_kwh = hourly_kwh

    return ImportConfirmResponse(
        session_id=session_id,
        start_date=hourly_kwh.index.min().isoformat(),
        end_date=hourly_kwh.index.max().isoformat(),
        total_kwh=round(float(hourly_kwh.sum()), 3),
        hours_count=int(len(hourly_kwh)),
        warnings=[],
    )
