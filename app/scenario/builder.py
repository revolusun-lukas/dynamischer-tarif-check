"""Baut aus den vorberechneten, statischen Profilen (siehe tools/generate_*.py) eine
reale, stundengenaue Verbrauchszeitreihe fuer ein frei konfiguriertes Szenario -- ohne
eigene Messdaten und ohne passenden Beispiel-Haushalt.

Die Zeitreihe wird serverseitig gebaut, damit sie unveraendert in die bestehende
Session-/Kostenvergleichs-Pipeline passt (session_store, calculate_routes,
calculation/cost.py) -- aus Sicht dieser Pipeline ist ein Szenario nicht anders als ein
CSV-Import oder ein ausgewaehlter Beispiel-Haushalt.

Flexibilität: Verschiebbare Lasten und preisgesteuertes E-Auto-Laden werden anhand der
echten Day-Ahead-Börsenpreise des Vergleichsjahres in die günstigsten Stunden gelegt
(verschiebbare Lasten wahlweise in die Stunden mit der meisten PV-Erzeugung). Day-Ahead-
Preise stehen am Vortag fest -- eine Zeitschaltuhr/Wallbox mit Preissteuerung kann das
real so umsetzen. Welcher Tarif am Ende günstiger ist, zeigt der Kostenvergleich in Schritt 4.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from app.pricing.awattar import AwattarError, fetch_prices
from app.scenario import weather
from app.schemas import ScenarioBuildRequest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "static" / "data"

RESOLUTION_MIN = 15
SLOTS_PER_HOUR = 60 // RESOLUTION_MIN
SLOTS_PER_DAY = 24 * SLOTS_PER_HOUR
DAYS_PER_YEAR = 365
SLOTS_PER_YEAR = DAYS_PER_YEAR * SLOTS_PER_DAY

HOURS_PER_YEAR = DAYS_PER_YEAR * 24
LOCAL_TZ = "Europe/Berlin"

# Verschiebbare Lasten: die je Tag verschobene Menge verteilt sich auf die besten 4 Stunden
# (typische Laufzeit von Spül-/Waschmaschine + Trockner über den Tag verteilt).
FLEX_HOURS_PER_DAY = 4


class ScenarioError(Exception):
    pass


@lru_cache(maxsize=1)
def _load_index() -> dict:
    with (DATA_DIR / "profiles_index.json").open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=32)
def _load_profile(relative_path: str) -> dict:
    with (DATA_DIR / relative_path).open(encoding="utf-8") as f:
        return json.load(f)


def list_household_types() -> list[dict]:
    return _load_index()["households"]


def _household_meta(household_id: str) -> dict:
    for household in list_household_types():
        if household["id"] == household_id:
            return household
    raise ScenarioError(f"Unbekannter Haushaltstyp: {household_id}")


def _average_household_profile(household: dict) -> np.ndarray:
    """Mittelt die 3 simulierten Haushaltsvarianten (Seeds) zu einem einzelnen,
    repraesentativen Verlauf -- fuer den konkreten Kostenvergleich in Schritt 3/4 wird
    ein einzelner Verbrauch gebraucht, nicht die Bandbreite."""
    arrays = [
        np.array(_load_profile(household["file_pattern"].format(id=household["id"], seed=seed))["values_kwh"], dtype=float)
        for seed in household["seeds"]
    ]
    return np.mean(arrays, axis=0)


def _hours_to_slots(hourly_kwh: np.ndarray) -> np.ndarray:
    return np.repeat(hourly_kwh / SLOTS_PER_HOUR, SLOTS_PER_HOUR)


def _allocate_to_best_hours(daily_amounts_kwh: np.ndarray, score: np.ndarray, lower_is_better: bool) -> np.ndarray:
    """Verteilt je Tag die Menge gleichmäßig auf die FLEX_HOURS_PER_DAY besten Stunden des Tages.

    score: ein Wert je Stunde (Börsenpreis -> niedrig ist gut; PV-Ertrag -> hoch ist gut).
    """
    out = np.zeros(HOURS_PER_YEAR)
    for day in range(DAYS_PER_YEAR):
        day_scores = score[day * 24:(day + 1) * 24]
        order = np.argsort(day_scores if lower_is_better else -day_scores, kind="stable")
        best = day * 24 + order[:FLEX_HOURS_PER_DAY]
        out[best] += daily_amounts_kwh[day] / FLEX_HOURS_PER_DAY
    return out


def _ev_controlled_hourly(annual_kwh: float, prices: np.ndarray, local_hours: np.ndarray, evening_day: np.ndarray) -> np.ndarray:
    """Preisgesteuertes Laden: je Abend die Tagesmenge in die günstigsten Stunden legen, in denen
    das Auto zu Hause ist (Ankunft bis Abfahrt laut ev_controlled.json), begrenzt durch die
    Ladeleistung je Stunde."""
    meta = _load_profile("addons/ev_controlled.json")
    arrival = meta["availability_window"]["arrival_hour"]
    departure = meta["availability_window"]["departure_hour"]
    max_per_hour = meta["charge_power_kw"]
    daily_kwh = annual_kwh / DAYS_PER_YEAR

    at_home = (local_hours >= arrival) | (local_hours < departure)
    out = np.zeros(HOURS_PER_YEAR)
    for day in np.unique(evening_day[at_home]):
        window = np.flatnonzero(at_home & (evening_day == day))
        remaining = daily_kwh
        for h in window[np.argsort(prices[window], kind="stable")]:
            charge = min(max_per_hour, remaining)
            out[h] += charge
            remaining -= charge
            if remaining <= 1e-9:
                break
    # Die Morgenstunden am 1.1. bilden ein angeschnittenes zusätzliches Fenster (Abend des
    # 31.12. fehlt) -- auf die exakte Jahresmenge normieren.
    return out * (annual_kwh / out.sum()) if out.sum() > 0 else out


def _reference_calendar(year: int) -> tuple[np.ndarray, np.ndarray]:
    """Lokale Uhrzeit je Stunde des Szenariojahres und der "Abend-Tag" (Ladefenster über
    Mitternacht gehört zum Vortag): Zeit − 12 h, davon das Datum."""
    index = pd.date_range(datetime(year, 1, 1, tzinfo=timezone.utc), periods=HOURS_PER_YEAR, freq="h").tz_convert(LOCAL_TZ)
    evening = (index - pd.Timedelta(hours=12)).normalize()
    return np.asarray(index.hour), np.asarray(evening.dayofyear + evening.year * 1000)


def _last_full_calendar_year() -> int:
    return datetime.now(timezone.utc).year - 1


def _format_de(value: float, decimals: int = 0) -> str:
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


ORIENTATION_LABELS = {"S": "Süd", "SE": "Südost", "SW": "Südwest", "E": "Ost", "W": "West", "EW": "Ost-West"}

# Balkonkraftwerk: Module am Balkongeländer stehen steil; eingespeist werden höchstens 800 W,
# mehr Modulleistung wird am Wechselrichter gekappt (kWh je Stunde = kW im Stundenmittel).
BALCONY_TILT_DEG = 60
BALCONY_MAX_KW = 0.8


def _build_profile(
    req: ScenarioBuildRequest, solar: dict[str, np.ndarray | None], prices: np.ndarray
) -> tuple[np.ndarray, dict, list[str]]:
    """Baut den 15-Minuten-Netzbezug eines Jahres und die Mengenbilanz dazu.

    Bilanz: Haushaltsstrom + E-Auto + Wärmepumpe = Verbrauch gesamt;
    Verbrauch gesamt − Solar-Eigenverbrauch = Netzbezug (das, was im Tarifvergleich bezahlt wird).
    solar: stündliche Erzeugung in kWh von "pv" (PV-Anlage) und "balcony" (Balkonkraftwerk), je None = nicht vorhanden.
    prices: Börsenpreis je Stunde des Vergleichsjahres (EUR/MWh) -- Grundlage für das Verschieben.
    """
    solar_parts = [a for a in (solar["pv"], solar["balcony"]) if a is not None]
    pv_hourly = np.sum(solar_parts, axis=0) if solar_parts else None
    household = _household_meta(req.household_id)
    base = _average_household_profile(household) * (req.annual_kwh / 1000.0)
    breakdown = {
        "household_kwh": float(req.annual_kwh),
        "ev_kwh": 0.0,
        "heatpump_kwh": 0.0,
        "pv_production_kwh": float(solar["pv"].sum()) if solar["pv"] is not None else 0.0,
        "balcony_production_kwh": float(solar["balcony"].sum()) if solar["balcony"] is not None else 0.0,
        "pv_self_consumption_kwh": 0.0,  # PV-Anlage + Balkonkraftwerk zusammen
        "pv_only_self_consumption_kwh": 0.0,
        "balcony_self_consumption_kwh": 0.0,
    }

    summary = [
        f"Haushaltstyp: {household['display_name']}",
        f"Haushaltsstrom: {_format_de(req.annual_kwh)} kWh/Jahr",
    ]

    if req.flex_percent > 0:
        flex_fraction = req.flex_percent / 100
        daily_sums = base.reshape(DAYS_PER_YEAR, SLOTS_PER_DAY).sum(axis=1)
        shift_amount_per_day = daily_sums * flex_fraction
        if req.flex_target == "sunny" and pv_hourly is not None:
            # An Tagen ganz ohne PV-Ertrag (sehr selten) greift die Reihenfolge nach Preis.
            score = pv_hourly - prices / 1e6
            shifted = _allocate_to_best_hours(shift_amount_per_day, score, lower_is_better=False)
            target = "Stunden mit der meisten Solarerzeugung"
        else:
            shifted = _allocate_to_best_hours(shift_amount_per_day, prices, lower_is_better=True)
            target = "günstigsten Börsenstunden"
        base = base * (1 - flex_fraction) + _hours_to_slots(shifted)
        summary.append(f"Verschiebbare Lasten: {req.flex_percent:.0f} %, je Tag in die {FLEX_HOURS_PER_DAY} {target}")

    total = base.copy()

    if req.heatpump.enabled and req.heatpump.annual_kwh > 0:
        hp_values = np.array(_load_profile("addons/heatpump.json")["values_kwh"], dtype=float)
        total = total + hp_values * (req.heatpump.annual_kwh / 1000.0)
        breakdown["heatpump_kwh"] = float(req.heatpump.annual_kwh)
        summary.append(f"Wärmepumpe: {_format_de(req.heatpump.annual_kwh)} kWh/Jahr")

    if req.ev.enabled and req.ev.km_per_year > 0:
        ev_annual_kwh = req.ev.km_per_year * req.ev.kwh_per_100km / 100
        breakdown["ev_kwh"] = float(ev_annual_kwh)
        ev_desc = (
            f"E-Auto: {_format_de(req.ev.km_per_year)} km/Jahr × {_format_de(req.ev.kwh_per_100km, 1)} kWh/100 km "
            f"= {_format_de(ev_annual_kwh)} kWh"
        )
        if req.ev.mode == "controlled":
            local_hours, evening_day = _reference_calendar(_last_full_calendar_year())
            total = total + _hours_to_slots(_ev_controlled_hourly(ev_annual_kwh, prices, local_hours, evening_day))
            summary.append(f"{ev_desc}, preisgesteuert (günstigste Stunden, während das Auto zu Hause ist: 17–7 Uhr)")
        else:
            ev_values = np.array(_load_profile("addons/ev_uncontrolled.json")["values_kwh"], dtype=float)
            total = total + ev_values * (ev_annual_kwh / 1000.0)
            summary.append(f"{ev_desc}, ungesteuert (Laden nach Heimkehr)")

    if pv_hourly is not None:
        solar_slots = _hours_to_slots(pv_hourly)
        grid = np.clip(total - solar_slots, 0, None)
        self_slots = total - grid
        breakdown["pv_self_consumption_kwh"] = float(self_slots.sum())
        # Aufteilung auf die Anlagen: je 15 Minuten im Verhältnis ihrer Erzeugung -- die beiden
        # Anteile ergeben zusammen exakt den gesamten Eigenverbrauch.
        for key, part in (("pv_only_self_consumption_kwh", solar["pv"]), ("balcony_self_consumption_kwh", solar["balcony"])):
            if part is None:
                continue
            share = np.divide(_hours_to_slots(part), solar_slots, out=np.zeros_like(solar_slots), where=solar_slots > 0)
            breakdown[key] = float((self_slots * share).sum())
        total = grid
        year = _last_full_calendar_year()
        if solar["pv"] is not None:
            summary.append(
                f"PV-Anlage: {_format_de(req.pv.kwp, 1)} kWp, {ORIENTATION_LABELS[req.pv.orientation]}, "
                f"{_format_de(req.pv.tilt)}° Neigung – Erzeugung {year}: {_format_de(breakdown['pv_production_kwh'])} kWh"
            )
        if solar["balcony"] is not None:
            summary.append(
                f"Balkonkraftwerk: {_format_de(req.balcony.kwp, 2)} kWp, {ORIENTATION_LABELS[req.balcony.orientation]}, "
                f"{BALCONY_TILT_DEG}° Neigung, max. 800 W – Erzeugung {year}: {_format_de(breakdown['balcony_production_kwh'])} kWh"
            )
        summary.append(
            f"Solar-Eigenverbrauch: {_format_de(breakdown['pv_self_consumption_kwh'])} kWh (Standort {req.location.name}, "
            f"Wetter {year}; Überschuss wird nicht vergütet)"
        )

    breakdown["total_consumption_kwh"] = breakdown["household_kwh"] + breakdown["ev_kwh"] + breakdown["heatpump_kwh"]
    breakdown["grid_kwh"] = float(total.sum())
    return total, breakdown, summary


async def _solar_hourly(req: ScenarioBuildRequest) -> dict[str, np.ndarray | None]:
    """Stündliche Erzeugung (kWh) von PV-Anlage und Balkonkraftwerk am Standort im Vergleichsjahr."""
    year = _last_full_calendar_year()
    lat, lon = req.location.latitude, req.location.longitude
    solar: dict[str, np.ndarray | None] = {"pv": None, "balcony": None}
    try:
        if req.pv.enabled and req.pv.kwp > 0:
            yield_per_kwp = await weather.fetch_pv_yield_per_kwp(lat, lon, req.pv.tilt, req.pv.orientation, year)
            solar["pv"] = yield_per_kwp[:HOURS_PER_YEAR] * req.pv.kwp
        if req.balcony.enabled and req.balcony.kwp > 0:
            yield_per_kwp = await weather.fetch_pv_yield_per_kwp(lat, lon, BALCONY_TILT_DEG, req.balcony.orientation, year)
            solar["balcony"] = np.minimum(yield_per_kwp[:HOURS_PER_YEAR] * req.balcony.kwp, BALCONY_MAX_KW)
    except weather.WeatherError as exc:
        raise ScenarioError(str(exc)) from exc
    return solar


_price_cache: dict[int, np.ndarray] = {}


async def _reference_prices() -> np.ndarray:
    """Börsenpreise (EUR/MWh) je Stunde des Vergleichsjahres, ab 1.1. 00:00 UTC. Fehlende
    Stunden bekommen den Jahresmittelwert (neutral für die Reihenfolge)."""
    year = _last_full_calendar_year()
    if year not in _price_cache:
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        index = pd.date_range(start, periods=HOURS_PER_YEAR, freq="h")
        try:
            raw = await fetch_prices(start, index[-1] + pd.Timedelta(hours=1))
        except AwattarError as exc:
            raise ScenarioError(str(exc)) from exc
        prices = np.array([raw.get(ts.to_pydatetime(), np.nan) for ts in index], dtype=float)
        _price_cache[year] = np.where(np.isnan(prices), np.nanmean(prices), prices)
    return _price_cache[year]


async def preview_scenario(req: ScenarioBuildRequest) -> dict:
    """Nur die Mengenbilanz (für die Live-Summe im Szenario-Fenster), ohne Session."""
    _, breakdown, _ = _build_profile(req, await _solar_hourly(req), await _reference_prices())
    return {**{k: round(v, 1) for k, v in breakdown.items()}, "reference_year": _last_full_calendar_year()}


async def build_scenario_series(req: ScenarioBuildRequest) -> tuple[pd.Series, list[str]]:
    total, breakdown, summary = _build_profile(req, await _solar_hourly(req), await _reference_prices())
    summary.append(f"Netzbezug gesamt: {_format_de(breakdown['grid_kwh'])} kWh/Jahr")

    # 15-Minuten-Werte -> Stundenwerte (Summe je 4 Slots), da calculation/cost.py auf Stundenbasis arbeitet.
    hourly_values = total.reshape(SLOTS_PER_YEAR // SLOTS_PER_HOUR, SLOTS_PER_HOUR).sum(axis=1)

    reference_year = _last_full_calendar_year()
    start = datetime(reference_year, 1, 1, tzinfo=timezone.utc)
    index = pd.date_range(start, periods=len(hourly_values), freq="h", tz="UTC")
    series = pd.Series(hourly_values, index=index).sort_index()
    series.index.name = "hour_utc"

    summary.append(
        f"Vergleichszeitraum: reales Kalenderjahr {reference_year} mit echten aWATTar-Börsenpreisen "
        "(Verbrauchsmuster ist positionsbasiert, nicht wochentagsgenau kalibriert)."
    )

    return series, summary
