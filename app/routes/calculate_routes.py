"""Route für den eigentlichen Tarifvergleich (Preisabruf + Kostenberechnung)."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException

from app.calculation.cost import calculate_comparison
from app.pricing.awattar import AwattarError, fetch_prices
from app.schemas import CalculateRequest, CalculateResponse
from app.session_store import SessionNotFoundError, store

router = APIRouter(prefix="/api", tags=["calculate"])


@router.post("/calculate", response_model=CalculateResponse)
async def calculate(req: CalculateRequest) -> CalculateResponse:
    try:
        session = store.get(req.session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    if session.hourly_kwh is None or session.hourly_kwh.empty:
        raise HTTPException(400, "Bitte zuerst einen Verbrauchsimport abschließen.")

    hourly_kwh = session.hourly_kwh
    start = hourly_kwh.index.min()
    end = hourly_kwh.index.max() + timedelta(hours=1)

    if session.price_cache is not None and session.price_cache_range == (start, end):
        prices = session.price_cache
    else:
        try:
            prices = await fetch_prices(start, end)
        except AwattarError as exc:
            raise HTTPException(502, str(exc)) from exc
        session.price_cache = prices
        session.price_cache_range = (start, end)

    try:
        result = calculate_comparison(hourly_kwh, prices, req.tariffs)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return result
