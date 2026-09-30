"""Standortbezogene Wetterdaten für das Verbrauchsszenario (Open-Meteo, ohne API-Key).

- PV-Ertrag: stündliche Einstrahlung auf die geneigte Modulfläche (global_tilted_irradiance)
  aus dem historischen Archiv für genau das Vergleichsjahr -- sonnige Tage im Szenario fallen
  damit auf die tatsächlich sonnigen Tage mit ihren (oft günstigen) Börsenpreisen.
- Ortssuche: Open-Meteo Geocoding (sucht Ortsnamen, keine Postleitzahlen).
"""
from __future__ import annotations

import httpx
import numpy as np

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Vereinfachtes PV-Modell: Systemverluste (Wechselrichter, Leitungen, Verschmutzung) wie bei
# PVGIS-Standard 14 %, dazu Temperaturverlust der Module.
SYSTEM_EFFICIENCY = 0.86
# Reflexions-, Spektral- und Schwachlichtverluste (fehlen im reinen Einstrahlungsmodell).
# Kalibriert gegen PVGIS 5.3 seriescalc für 2023 (51°N/10°O): ohne diesen Faktor lagen die
# Jahreserträge über alle Ausrichtungen ~8 % über PVGIS, mit ihm im Mittel innerhalb ±2 %.
OPTICAL_LOSS_FACTOR = 0.92
TEMP_COEFF_PER_K = -0.004  # typisch für kristalline Module
CELL_TEMP_RISE_PER_W_M2 = 0.03  # Modul ~30 K wärmer als Luft bei 1000 W/m²

# Ausrichtung -> Azimut (Open-Meteo: 0 = Süd, -90 = Ost, 90 = West). Ost-West = je halbe
# Leistung auf beide Dachseiten.
ORIENTATIONS: dict[str, list[int]] = {
    "S": [0],
    "SE": [-45],
    "SW": [45],
    "E": [-90],
    "W": [90],
    "EW": [-90, 90],
}


class WeatherError(Exception):
    pass


# Ein Eintrag = ein Jahr Stundenwerte (~70 kB); die Live-Vorschau fragt bei jeder Änderung
# von Ort/Neigung/Ausrichtung neu an, daher Cache -- mit Obergrenze, damit er nicht wächst.
PV_CACHE_MAX_ENTRIES = 200
_pv_cache: dict[tuple, np.ndarray] = {}


async def _fetch_tilted_hourly(lat: float, lon: float, tilt: float, azimuth: int, year: int) -> np.ndarray:
    key = (round(lat, 2), round(lon, 2), round(tilt), azimuth, year)
    if key in _pv_cache:
        return _pv_cache[key]

    params = {
        "latitude": key[0],
        "longitude": key[1],
        "start_date": f"{year}-01-01",
        "end_date": f"{year}-12-31",
        "hourly": "global_tilted_irradiance,temperature_2m",
        "tilt": key[2],
        "azimuth": azimuth,
        "timezone": "UTC",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(ARCHIVE_URL, params=params)
            response.raise_for_status()
            hourly = response.json()["hourly"]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise WeatherError(f"Wetterdaten für die PV-Berechnung nicht abrufbar: {exc}") from exc

    gti = np.array([v or 0.0 for v in hourly["global_tilted_irradiance"]], dtype=float)  # W/m², Stundenmittel
    temp = np.array([v if v is not None else 10.0 for v in hourly["temperature_2m"]], dtype=float)
    cell_temp = temp + CELL_TEMP_RISE_PER_W_M2 * gti
    temp_factor = 1 + TEMP_COEFF_PER_K * (cell_temp - 25)
    # 1 kWp liefert bei 1000 W/m² (STC) 1 kW -> kWh je Stunde = GTI/1000 * Wirkungsgrade.
    kwh_per_kwp = gti / 1000 * SYSTEM_EFFICIENCY * OPTICAL_LOSS_FACTOR * temp_factor
    kwh_per_kwp = np.clip(kwh_per_kwp, 0, None)

    if len(_pv_cache) >= PV_CACHE_MAX_ENTRIES:
        _pv_cache.clear()
    _pv_cache[key] = kwh_per_kwp
    return kwh_per_kwp


async def fetch_pv_yield_per_kwp(lat: float, lon: float, tilt: float, orientation: str, year: int) -> np.ndarray:
    """Stündlicher PV-Ertrag in kWh je kWp für das Kalenderjahr `year` (UTC, ab 1.1. 00:00)."""
    azimuths = ORIENTATIONS[orientation]
    parts = [await _fetch_tilted_hourly(lat, lon, tilt, az, year) for az in azimuths]
    return np.mean(parts, axis=0)


async def geocode(query: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                GEOCODING_URL, params={"name": query, "count": 6, "language": "de", "countryCode": "DE"}
            )
            response.raise_for_status()
            results = response.json().get("results", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise WeatherError(f"Ortssuche nicht erreichbar: {exc}") from exc

    return [
        {
            "name": r["name"],
            "region": r.get("admin1") or "",
            "latitude": round(float(r["latitude"]), 4),
            "longitude": round(float(r["longitude"]), 4),
        }
        for r in results
    ]
