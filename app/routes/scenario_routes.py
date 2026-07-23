"""Routen für das Verbrauchsszenario (Alternative zu CSV-Upload und Beispiel-Haushalt):
baut aus repräsentativen Profilen eine reale Stundenreihe und legt sie wie einen Import
in der Session ab -- danach läuft der Wizard identisch weiter (Tarife konfigurieren,
Ergebnis)."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request

from app.rate_limit import limiter
from app.schemas import (
    ScenarioBuildRequest,
    ScenarioBuildResponse,
    ScenarioHousehold,
    ScenarioHouseholdListResponse,
)
from app.scenario import builder
from app.session_store import store

router = APIRouter(prefix="/api/scenario", tags=["scenario"])


@router.get("/households", response_model=ScenarioHouseholdListResponse)
async def list_households() -> ScenarioHouseholdListResponse:
    households = builder.list_household_types()
    return ScenarioHouseholdListResponse(
        households=[
            ScenarioHousehold(
                id=h["id"],
                display_name=h["display_name"],
                description=h["description"],
                typical_annual_kwh=h["typical_annual_kwh"],
            )
            for h in households
        ]
    )


@router.post("/build", response_model=ScenarioBuildResponse)
@limiter.limit("10/minute")
async def build_scenario(request: Request, req: ScenarioBuildRequest) -> ScenarioBuildResponse:
    try:
        hourly_kwh, summary_lines = builder.build_scenario_series(req)
    except builder.ScenarioError as exc:
        raise HTTPException(400, str(exc)) from exc

    session_id, session = store.create(source="scenario")
    session.hourly_kwh = hourly_kwh

    return ScenarioBuildResponse(
        session_id=session_id,
        start_date=hourly_kwh.index.min().isoformat(),
        end_date=(hourly_kwh.index.max() + timedelta(hours=1)).isoformat(),
        total_kwh=round(float(hourly_kwh.sum()), 3),
        hours_count=int(len(hourly_kwh)),
        warnings=[],
        summary_lines=summary_lines,
    )
