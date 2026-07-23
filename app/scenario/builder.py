"""Baut aus den vorberechneten, statischen Profilen (siehe tools/generate_*.py) eine
reale, stundengenaue Verbrauchszeitreihe fuer ein frei konfiguriertes Szenario -- ohne
eigene Messdaten und ohne passenden Beispiel-Haushalt.

Die Zeitreihe wird serverseitig gebaut, damit sie unveraendert in die bestehende
Session-/Kostenvergleichs-Pipeline passt (session_store, calculate_routes,
calculation/cost.py) -- aus Sicht dieser Pipeline ist ein Szenario nicht anders als ein
CSV-Import oder ein ausgewaehlter Beispiel-Haushalt.

Wichtige Vereinfachung: Verschiebbare Lasten und preisgesteuertes E-Auto-Laden werden
in die Nachtstunden 00-06 Uhr gelegt (generische Annaeherung an "guenstige Stunden").
Zum Zeitpunkt der Szenario-Erstellung ist noch kein Tarif gewaehlt (das passiert erst
in Schritt 3) -- eine echte Preisoptimierung ist hier also nicht moeglich/sinnvoll; die
eigentliche Auszahlung der Flexibilitaet zeigt sich im Kostenvergleich mit dem
dynamischen Tarif in Schritt 4.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from app.schemas import ScenarioBuildRequest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "static" / "data"

RESOLUTION_MIN = 15
SLOTS_PER_HOUR = 60 // RESOLUTION_MIN
SLOTS_PER_DAY = 24 * SLOTS_PER_HOUR
DAYS_PER_YEAR = 365
SLOTS_PER_YEAR = DAYS_PER_YEAR * SLOTS_PER_DAY

EV_KWH_PER_KM = 0.18
NIGHT_START_HOUR = 0
NIGHT_END_HOUR = 6


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


def _allocate_into_night(daily_amounts_kwh: np.ndarray) -> np.ndarray:
    """Verteilt je Tag eine Energiemenge gleichmaessig auf die Nachtstunden."""
    out = np.zeros(SLOTS_PER_YEAR)
    night_slots_per_day = (NIGHT_END_HOUR - NIGHT_START_HOUR) * SLOTS_PER_HOUR
    for day in range(DAYS_PER_YEAR):
        amount = daily_amounts_kwh[day]
        if amount <= 0:
            continue
        start = day * SLOTS_PER_DAY + NIGHT_START_HOUR * SLOTS_PER_HOUR
        out[start:start + night_slots_per_day] += amount / night_slots_per_day
    return out


def _last_full_calendar_year() -> int:
    return datetime.now(timezone.utc).year - 1


def _format_de(value: float, decimals: int = 0) -> str:
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def build_scenario_series(req: ScenarioBuildRequest) -> tuple[pd.Series, list[str]]:
    household = _household_meta(req.household_id)
    base = _average_household_profile(household) * (req.annual_kwh / 1000.0)

    summary = [
        f"Haushaltstyp: {household['display_name']}",
        f"Jahresverbrauch: {_format_de(req.annual_kwh)} kWh",
    ]

    if req.flex_percent > 0:
        flex_fraction = req.flex_percent / 100
        daily_sums = base.reshape(DAYS_PER_YEAR, SLOTS_PER_DAY).sum(axis=1)
        shift_amount_per_day = daily_sums * flex_fraction
        base = base * (1 - flex_fraction) + _allocate_into_night(shift_amount_per_day)
        summary.append(f"Verschiebbare Lasten: {req.flex_percent:.0f} % (Modell: Verlagerung in Nachtstunden 00-06 Uhr)")

    total = base.copy()

    if req.heatpump.enabled and req.heatpump.annual_kwh > 0:
        hp_values = np.array(_load_profile("addons/heatpump.json")["values_kwh"], dtype=float)
        total = total + hp_values * (req.heatpump.annual_kwh / 1000.0)
        summary.append(f"Wärmepumpe: {_format_de(req.heatpump.annual_kwh)} kWh/Jahr")

    if req.ev.enabled and req.ev.km_per_year > 0:
        ev_annual_kwh = req.ev.km_per_year * EV_KWH_PER_KM
        if req.ev.mode == "controlled":
            daily_amounts = np.full(DAYS_PER_YEAR, ev_annual_kwh / DAYS_PER_YEAR)
            total = total + _allocate_into_night(daily_amounts)
            summary.append(
                f"E-Auto: {_format_de(req.ev.km_per_year)} km/Jahr, preisgesteuert "
                "(Modell: Laden in Nachtstunden 00-06 Uhr)"
            )
        else:
            ev_values = np.array(_load_profile("addons/ev_uncontrolled.json")["values_kwh"], dtype=float)
            total = total + ev_values * (ev_annual_kwh / 1000.0)
            summary.append(f"E-Auto: {_format_de(req.ev.km_per_year)} km/Jahr, ungesteuert (Laden nach Heimkehr)")

    if req.pv.enabled and req.pv.kwp > 0:
        pv_profile = _load_profile("addons/pv_south.json")
        pv_values = np.array(pv_profile["values_kwh"], dtype=float)
        pv_production = pv_values * (req.pv.kwp * pv_profile["annual_reference_kwh_per_kwp"] / 1000.0)
        total = np.clip(total - pv_production, 0, None)
        summary.append(f"PV-Anlage: {_format_de(req.pv.kwp, 1)} kWp (Süddach, nur Eigenverbrauch, keine Einspeisevergütung)")

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
