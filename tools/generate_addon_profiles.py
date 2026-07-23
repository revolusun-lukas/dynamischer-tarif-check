"""Erzeugt die modularen Zusatzprofile fuer den Live-Rechner (static/data/addons/):

- pv_south.json        PV-Erzeugung Sueddach, echte PVGIS-Einstrahlungsdaten
- heatpump.json         Waermepumpe, vereinfachte Gradtagszahl-Logik
- ev_uncontrolled.json  E-Auto, ungesteuertes Laden nach Heimkehr
- ev_controlled.json    E-Auto, Platzhalter fuer preisgesteuertes Laden
                        (definiert nur die taeglich verschiebbare Energiemenge;
                        die eigentliche Optimierung/Stundenwahl passiert im
                        Frontend anhand der Spotpreise, siehe live_calculator.js)

Alle Profile (ausser ev_controlled) sind wie die Haushaltsprofile auf
1000 kWh/Jahr normiert und liegen in 15-Minuten-Aufloesung vor.

Ausfuehren (PV-Teil braucht Internetzugang fuer PVGIS, laeuft NICHT auf Render):
    python tools/generate_addon_profiles.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.profile_shared import (  # noqa: E402
    DATA_DIR,
    RESOLUTION_MIN,
    SLOTS_PER_DAY,
    SLOTS_PER_YEAR,
    normalize_to_annual_kwh,
    write_profile_json,
    year_datetime_index,
)

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_2/seriescalc"
PVGIS_YEAR = 2019  # nicht-schaltjahr, vollstaendig in PVGIS-SARAH2 verfuegbar
PVGIS_LOCATION = {"lat": 51.0, "lon": 10.0}  # geografische Mitte Deutschlands


def generate_pv_south() -> None:
    print("Lade PVGIS-Einstrahlungsdaten (Sueddach, 1 kWp Referenzanlage)...")
    params = {
        **PVGIS_LOCATION,
        "startyear": PVGIS_YEAR,
        "endyear": PVGIS_YEAR,
        "pvcalculation": 1,
        "peakpower": 1,       # 1 kWp Referenzanlage -> Jahresertrag = spezifischer Ertrag
        "loss": 14,           # typische Systemverluste (Wechselrichter, Verkabelung, Verschmutzung)
        "angle": 35,          # Dachneigung
        "aspect": 0,          # Sueden
        "outputformat": "json",
    }
    resp = httpx.get(PVGIS_URL, params=params, timeout=30.0)
    resp.raise_for_status()
    hourly = resp.json()["outputs"]["hourly"]

    power_w = np.array([row["P"] for row in hourly], dtype=float)
    if len(power_w) != 8760:
        print(f"Warnung: PVGIS lieferte {len(power_w)} Stundenwerte statt 8760.")

    annual_reference_kwh_per_kwp = float((power_w / 1000.0).sum())

    # Jede Stunde gleichmaessig auf 4 Viertelstunden verteilen (PVGIS liefert nur Stundenwerte).
    energy_kwh_hourly = power_w / 1000.0
    energy_15min = np.repeat(energy_kwh_hourly, 4) / 4
    energy_15min = energy_15min[:SLOTS_PER_YEAR]
    if len(energy_15min) < SLOTS_PER_YEAR:
        energy_15min = np.pad(energy_15min, (0, SLOTS_PER_YEAR - len(energy_15min)))

    values = normalize_to_annual_kwh(energy_15min)

    write_profile_json(DATA_DIR / "addons" / "pv_south.json", {
        "type": "pv_south",
        "resolution_min": RESOLUTION_MIN,
        "values_kwh": values.tolist(),
        "annual_reference_kwh_per_kwp": round(annual_reference_kwh_per_kwp, 1),
        "source": (
            f"PVGIS v5.2 (re.jrc.ec.europa.eu), PVGIS-SARAH2, Jahr {PVGIS_YEAR}, "
            f"lat/lon {PVGIS_LOCATION['lat']}/{PVGIS_LOCATION['lon']}, Neigung 35 Grad, Sueden, "
            "Systemverluste 14%."
        ),
    })
    print(f"Geschrieben: addons/pv_south.json (spezifischer Ertrag: {annual_reference_kwh_per_kwp:.0f} kWh/kWp/Jahr)")


def generate_heatpump() -> None:
    """Vereinfachte Gradtagszahl-Logik: synthetisches, sinusfoermiges Temperaturjahr
    (Minimum Ende Januar, Maximum Ende Juli) statt eines echten TRY-Datensatzes. Heizbedarf
    proportional zu max(0, Heizgrenze - Aussentemperatur), mit staerkerer Gewichtung der
    fruehen Morgenstunden (Aufheizen) und Nachtabsenkung.
    """
    idx = year_datetime_index()
    day_of_year = idx.dayofyear.values.astype(float)

    heating_limit_c = 15.0
    mean_temp = 9.0
    amplitude = 10.0
    # Minimum am Tag ~28 (Ende Januar), Periodenlaenge 365 Tage.
    temp_c = mean_temp - amplitude * np.cos(2 * np.pi * (day_of_year - 28) / 365)

    heating_demand_relative = np.clip(heating_limit_c - temp_c, 0, None)

    hour_of_day = idx.hour.values + idx.minute.values / 60.0
    # Nachtabsenkung 22-5 Uhr (70% Leistung), leichte Morgenspitze 5-8 Uhr (120%) durchs Aufheizen.
    intraday_factor = np.ones_like(hour_of_day)
    intraday_factor[(hour_of_day >= 22) | (hour_of_day < 5)] = 0.7
    intraday_factor[(hour_of_day >= 5) & (hour_of_day < 8)] = 1.2

    raw = heating_demand_relative * intraday_factor
    values = normalize_to_annual_kwh(raw)

    write_profile_json(DATA_DIR / "addons" / "heatpump.json", {
        "type": "heatpump",
        "resolution_min": RESOLUTION_MIN,
        "values_kwh": values.tolist(),
        "source": (
            "Vereinfachte Gradtagszahl-Logik: synthetisches sinusfoermiges Temperaturjahr "
            f"(Mittel {mean_temp} Grad C, Amplitude {amplitude} Grad C), Heizgrenze {heating_limit_c} Grad C, "
            "mit Tag/Nacht-Lastprofil. Kein echter TRY-Datensatz."
        ),
    })
    print("Geschrieben: addons/heatpump.json")


def generate_ev_uncontrolled(rng: np.random.Generator) -> None:
    """Ungesteuertes Laden: Ankunft zuhause am Abend, Ladebeginn kurz danach mit ~11 kW
    bis der Tagesbedarf gedeckt ist. Nur an angenommenen 5 Ladetagen/Woche (Pendlerprofil).
    """
    idx = year_datetime_index()
    charge_power_kw = 11.0
    energy_per_slot_at_full_power = charge_power_kw * (RESOLUTION_MIN / 60)

    values = np.zeros(SLOTS_PER_YEAR)
    n_days = SLOTS_PER_YEAR // SLOTS_PER_DAY
    daily_energy_need = 1.0  # Platzhaltergroesse, wird unten global normiert

    weekday = idx[::SLOTS_PER_DAY].dayofweek.values  # 0=Montag
    for day in range(n_days):
        if weekday[day] >= 5:  # am Wochenende meist kein Pendel-Ladebedarf
            continue
        arrival_hour = rng.normal(18.0, 0.75)
        arrival_hour = np.clip(arrival_hour, 16.0, 21.0)
        start_slot = day * SLOTS_PER_DAY + int(round(arrival_hour * (60 / RESOLUTION_MIN)))

        remaining = daily_energy_need
        slot = start_slot
        end_of_day = day * SLOTS_PER_DAY + SLOTS_PER_DAY
        while remaining > 0 and slot < min(end_of_day, SLOTS_PER_YEAR):
            take = min(remaining, energy_per_slot_at_full_power)
            values[slot] += take
            remaining -= take
            slot += 1

    values = normalize_to_annual_kwh(values)
    write_profile_json(DATA_DIR / "addons" / "ev_uncontrolled.json", {
        "type": "ev_uncontrolled",
        "resolution_min": RESOLUTION_MIN,
        "values_kwh": values.tolist(),
        "charge_power_kw": charge_power_kw,
        "source": (
            "Synthetisches Pendlerladeprofil: Ladebeginn ca. 18 Uhr an 5 Tagen/Woche, "
            f"Ladeleistung {charge_power_kw} kW bis Tagesbedarf gedeckt ist."
        ),
    })
    print("Geschrieben: addons/ev_uncontrolled.json")


def generate_ev_controlled() -> None:
    """Platzhalter: definiert nur die taeglich verschiebbare Energiemenge und das
    Zeitfenster, in dem das Fahrzeug typischerweise zuhause verfuegbar ist. Die
    eigentliche Wahl der guenstigsten Ladestunden innerhalb des Fensters passiert
    im Frontend (live_calculator.js) anhand der Spotpreise des Nutzers/Szenarios.
    """
    charge_power_kw = 11.0
    daily_energy_kwh = 1000.0 / 365
    write_profile_json(DATA_DIR / "addons" / "ev_controlled.json", {
        "type": "ev_controlled",
        "resolution_min": RESOLUTION_MIN,
        "annual_reference_kwh": 1000.0,
        "daily_energy_kwh": round(daily_energy_kwh, 4),
        "charge_power_kw": charge_power_kw,
        "availability_window": {"arrival_hour": 17, "departure_hour": 7},
        "note": (
            "Platzhalter fuer preisgesteuertes Laden: nur die taeglich verschiebbare "
            "Energiemenge und das Verfuegbarkeitsfenster sind vorgegeben. Die Wahl der "
            "guenstigsten Stunden im Fenster erfolgt im Frontend anhand der Spotpreise."
        ),
    }, decimals=6)
    print("Geschrieben: addons/ev_controlled.json")


def main() -> None:
    rng = np.random.default_rng(42)
    generate_pv_south()
    generate_heatpump()
    generate_ev_uncontrolled(rng)
    generate_ev_controlled()


if __name__ == "__main__":
    main()
