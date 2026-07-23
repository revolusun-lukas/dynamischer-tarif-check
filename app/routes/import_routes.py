"""Routen für den Verbrauchsdaten-Import (Upload + Spaltenzuordnung bestätigen)."""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.importer import aggregation, parsing
from app.rate_limit import limiter
from app.schemas import ImportConfirmRequest, ImportConfirmResponse, ImportUploadResponse
from app.session_store import SessionNotFoundError, store

router = APIRouter(prefix="/api/import", tags=["import"])

MAX_PREVIEW_ROWS = 15
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB -- schützt einen öffentlich erreichbaren Server vor Missbrauch


@router.post("/upload", response_model=ImportUploadResponse)
@limiter.limit("10/minute")
async def upload_csv(request: Request, file: UploadFile = File(...)) -> ImportUploadResponse:
    content = await file.read()
    if not content:
        raise HTTPException(400, "Die Datei ist leer.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Die Datei ist zu groß (Limit: {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")

    try:
        df, parse_meta = parsing.read_csv_raw(content)
    except parsing.ParsingError as exc:
        raise HTTPException(400, str(exc)) from exc

    if df.shape[1] < 2:
        raise HTTPException(400, "Es wurden weniger als 2 Spalten erkannt. Bitte Trennzeichen der CSV prüfen.")
    if df.empty:
        raise HTTPException(400, "Die CSV enthält keine Datenzeilen.")

    ts_col, ts_warnings = parsing.suggest_timestamp_column(df)
    value_col = parsing.suggest_value_column(df, exclude=ts_col)
    value_type = None
    if value_col is not None:
        value_type = parsing.suggest_value_type(value_col, df[value_col], parse_meta["decimal"])

    session_id, session = store.create(source="upload")
    session.raw_df = df
    session.parse_meta = parse_meta

    preview_rows = df.head(MAX_PREVIEW_ROWS).to_dict(orient="records")

    return ImportUploadResponse(
        session_id=session_id,
        columns=list(df.columns),
        preview_rows=preview_rows,
        suggested_timestamp_column=ts_col,
        suggested_value_column=value_col,
        suggested_value_type=value_type,
        suggested_timezone="Europe/Berlin",
        row_count=len(df),
        warnings=ts_warnings,
    )


@router.post("/confirm", response_model=ImportConfirmResponse)
@limiter.limit("10/minute")
async def confirm_import(request: Request, req: ImportConfirmRequest) -> ImportConfirmResponse:
    try:
        session = store.get(req.session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    if session.raw_df is None:
        raise HTTPException(400, "Kein Import-Vorgang für diese Session gefunden. Bitte CSV erneut hochladen.")

    df = session.raw_df
    if req.timestamp_column not in df.columns or req.value_column not in df.columns:
        raise HTTPException(400, "Ungültige Spaltenauswahl.")
    if req.timestamp_column == req.value_column:
        raise HTTPException(400, "Zeitstempel- und Werte-Spalte dürfen nicht identisch sein.")

    try:
        hourly_kwh, warnings = aggregation.build_hourly_series(
            df,
            timestamp_col=req.timestamp_column,
            value_col=req.value_column,
            value_type=req.value_type,
            timezone_name=req.timezone,
            decimal=session.parse_meta.get("decimal", "."),
        )
    except aggregation.AggregationError as exc:
        raise HTTPException(400, str(exc)) from exc

    session.hourly_kwh = hourly_kwh
    session.price_cache = None
    session.price_cache_range = None

    return ImportConfirmResponse(
        session_id=req.session_id,
        start_date=hourly_kwh.index.min().isoformat(),
        end_date=hourly_kwh.index.max().isoformat(),
        total_kwh=round(float(hourly_kwh.sum()), 3),
        hours_count=int(len(hourly_kwh)),
        warnings=warnings,
    )
