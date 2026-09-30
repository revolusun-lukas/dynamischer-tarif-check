"""Route für den eigentlichen Tarifvergleich (Preisabruf + Kostenberechnung)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from app.calculation.cost import calculate_comparison, day_detail, pair_analysis
from app.pricing.awattar import AwattarError, fetch_prices
from app.rate_limit import limiter
from app.schemas import (
    CalculateRequest,
    CalculateResponse,
    DayDetailRequest,
    DayDetailResponse,
    PairAnalysisRequest,
    PairAnalysisResponse,
    SpotAverageResponse,
)
from app.session_store import SessionNotFoundError, store

router = APIRouter(prefix="/api", tags=["calculate"])


@router.post("/calculate", response_model=CalculateResponse)
@limiter.limit("10/minute")
async def calculate(request: Request, req: CalculateRequest) -> CalculateResponse:
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
        result, detail = calculate_comparison(hourly_kwh, prices, req.tariffs)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    session.calculation_detail = detail
    return result


_spot_average_cache: dict[date, dict] = {}


@router.get("/prices/average-12m", response_model=SpotAverageResponse)
@limiter.limit("30/minute")
async def spot_average_12m(request: Request) -> SpotAverageResponse:
    """Ø-Börsenpreis der letzten 12 Monate (netto). Dient im Tarif-Schritt dazu, aus dem
    "geschätzten Arbeitspreis" eines Angebots den fixen Anteil (Netzentgelt, Steuern, Umlagen)
    herauszurechnen. Einmal pro Tag neu berechnet."""
    today = datetime.now(timezone.utc).date()
    if today not in _spot_average_cache:
        end = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
        start = end - timedelta(days=365)
        try:
            prices = await fetch_prices(start, end)
        except AwattarError as exc:
            raise HTTPException(502, str(exc)) from exc
        _spot_average_cache.clear()
        _spot_average_cache[today] = {
            "avg_ct_kwh_netto": round(sum(prices.values()) / len(prices) / 10, 2),
            "start_date": start.date().isoformat(),
            "end_date": (end - timedelta(days=1)).date().isoformat(),
        }
    return _spot_average_cache[today]


def _calculation_detail(session_id: str):
    try:
        session = store.get(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if session.calculation_detail is None:
        raise HTTPException(400, "Bitte zuerst eine Berechnung durchführen.")
    return session.calculation_detail


@router.post("/day-detail", response_model=DayDetailResponse)
@limiter.limit("60/minute")
async def get_day_detail(request: Request, req: DayDetailRequest) -> DayDetailResponse:
    detail = _calculation_detail(req.session_id)
    try:
        return day_detail(detail, req.date, req.tariff_names)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/pair-analysis", response_model=PairAnalysisResponse)
@limiter.limit("60/minute")
async def get_pair_analysis(request: Request, req: PairAnalysisRequest) -> PairAnalysisResponse:
    detail = _calculation_detail(req.session_id)
    try:
        return pair_analysis(detail, req.tariff_names)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
