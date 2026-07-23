"""Erzeugt SYNTHETISCHE Platzhalter-Haushaltsprofile fuer den Live-Rechner.

Dies ist NICHT die in der Aufgabenstellung vorgesehene LPG-Simulation (siehe
generate_household_profiles_lpg.py) -- das braucht eine lokale Installation von
pylpg + der LoadProfileGenerator-Engine (Java, mehrere hundert MB), die in dieser
Umgebung nicht verfuegbar ist. Damit der Live-Rechner trotzdem sofort mit
plausiblen, unterscheidbaren Profilen funktioniert, generiert dieses Skript
stattdessen handmodellierte Tagesverlaufskurven (Wochentag/Wochenende, saisonale
Schwankung, Zufallsrauschen je Seed) je Haushaltstyp.

Ausfuehren (keine externen Abhaengigkeiten, laeuft ueberall inkl. Render-Build):
    python tools/generate_household_profiles_placeholder.py

Sobald generate_household_profiles_lpg.py erfolgreich mit echten LPG-Daten lief,
werden die hier erzeugten Dateien 1:1 durch echte ersetzt (identisches JSON-Format).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.household_types import HOUSEHOLD_TYPES, SEEDS  # noqa: E402
from tools.profile_shared import (  # noqa: E402
    DATA_DIR,
    RESOLUTION_MIN,
    SLOTS_PER_YEAR,
    normalize_to_annual_kwh,
    write_index_json,
    write_profile_json,
    year_datetime_index,
)

# Je Haushaltstyp: 24 relative Stundengewichte fuer Wochentag und Wochenende.
# Grobe, plausible Tagesverlaeufe -- kein Anspruch auf empirische Genauigkeit,
# dient nur als Platzhalter bis echte LPG-Profile vorliegen.
HOURLY_CURVES: dict[str, dict[str, list[float]]] = {
    "single_working": {
        "weekday": [0.35, 0.3, 0.3, 0.3, 0.3, 0.5, 1.2, 1.6, 0.9, 0.5, 0.4, 0.4,
                    0.5, 0.4, 0.4, 0.4, 0.5, 0.9, 1.5, 1.9, 1.7, 1.2, 0.7, 0.45],
        "weekend": [0.4, 0.35, 0.3, 0.3, 0.3, 0.35, 0.5, 0.8, 1.1, 1.2, 1.1, 1.0,
                    1.1, 1.0, 0.9, 0.9, 1.0, 1.2, 1.5, 1.6, 1.4, 1.1, 0.7, 0.5],
    },
    "single_home": {
        "weekday": [0.5, 0.4, 0.4, 0.4, 0.4, 0.5, 0.8, 1.0, 1.1, 1.1, 1.1, 1.2,
                    1.3, 1.1, 1.0, 1.0, 1.1, 1.3, 1.5, 1.5, 1.3, 1.0, 0.7, 0.55],
        "weekend": [0.5, 0.4, 0.4, 0.4, 0.4, 0.5, 0.7, 0.9, 1.1, 1.2, 1.2, 1.3,
                    1.4, 1.2, 1.1, 1.1, 1.1, 1.3, 1.5, 1.5, 1.3, 1.0, 0.7, 0.55],
    },
    "couple_both_working": {
        "weekday": [0.4, 0.35, 0.35, 0.35, 0.35, 0.6, 1.4, 1.9, 1.1, 0.55, 0.45, 0.45,
                    0.55, 0.45, 0.45, 0.45, 0.55, 1.0, 1.8, 2.2, 2.0, 1.4, 0.8, 0.5],
        "weekend": [0.45, 0.4, 0.35, 0.35, 0.35, 0.4, 0.6, 0.95, 1.3, 1.4, 1.3, 1.2,
                    1.3, 1.2, 1.1, 1.1, 1.2, 1.4, 1.8, 1.9, 1.6, 1.2, 0.8, 0.55],
    },
    "couple_home_office": {
        "weekday": [0.45, 0.4, 0.4, 0.4, 0.4, 0.55, 0.9, 1.2, 1.3, 1.3, 1.3, 1.4,
                    1.5, 1.3, 1.2, 1.2, 1.3, 1.5, 1.9, 2.1, 1.8, 1.3, 0.8, 0.55],
        "weekend": [0.5, 0.4, 0.4, 0.4, 0.4, 0.45, 0.6, 0.9, 1.2, 1.3, 1.3, 1.3,
                    1.4, 1.3, 1.2, 1.2, 1.2, 1.4, 1.8, 1.9, 1.6, 1.2, 0.8, 0.55],
    },
    "family_one_home": {
        "weekday": [0.5, 0.4, 0.4, 0.4, 0.4, 0.6, 1.1, 1.4, 1.3, 1.2, 1.2, 1.3,
                    1.5, 1.3, 1.3, 1.4, 1.6, 1.9, 2.3, 2.2, 1.8, 1.2, 0.8, 0.6],
        "weekend": [0.5, 0.4, 0.4, 0.4, 0.4, 0.5, 0.8, 1.1, 1.3, 1.4, 1.4, 1.4,
                    1.6, 1.4, 1.4, 1.4, 1.5, 1.8, 2.1, 2.1, 1.7, 1.2, 0.8, 0.6],
    },
    "family_both_working": {
        "weekday": [0.5, 0.4, 0.4, 0.4, 0.4, 0.6, 1.3, 1.7, 1.0, 0.6, 0.55, 0.6,
                    0.7, 0.7, 1.0, 1.4, 1.7, 2.0, 2.5, 2.3, 1.8, 1.2, 0.8, 0.6],
        "weekend": [0.55, 0.45, 0.4, 0.4, 0.4, 0.5, 0.75, 1.1, 1.4, 1.5, 1.5, 1.5,
                    1.7, 1.5, 1.4, 1.4, 1.5, 1.8, 2.2, 2.2, 1.8, 1.3, 0.85, 0.6],
    },
    "senior_couple": {
        "weekday": [0.45, 0.4, 0.4, 0.4, 0.4, 0.5, 0.75, 1.0, 1.1, 1.1, 1.15, 1.25,
                    1.4, 1.2, 1.1, 1.05, 1.1, 1.3, 1.6, 1.5, 1.2, 0.9, 0.65, 0.5],
        "weekend": [0.45, 0.4, 0.4, 0.4, 0.4, 0.5, 0.7, 1.0, 1.1, 1.15, 1.2, 1.3,
                    1.45, 1.25, 1.1, 1.05, 1.1, 1.3, 1.6, 1.5, 1.2, 0.9, 0.65, 0.5],
    },
}


def seasonal_multiplier(day_of_year: np.ndarray, amplitude: float = 0.08) -> np.ndarray:
    """Leicht erhoehter Verbrauch im Winter (Licht, mehr Zeit zuhause), Minimum im Sommer."""
    return 1.0 + amplitude * np.cos(2 * np.pi * (day_of_year - 15) / 365)


def build_profile(household_id: str, seed: int, idx) -> np.ndarray:
    curves = HOURLY_CURVES[household_id]
    weekday_curve = np.array(curves["weekday"])
    weekend_curve = np.array(curves["weekend"])

    hour = idx.hour.values
    is_weekend = idx.dayofweek.values >= 5
    base = np.where(is_weekend, weekend_curve[hour], weekday_curve[hour])

    base = base * seasonal_multiplier(idx.dayofyear.values.astype(float))

    rng = np.random.default_rng(abs(hash((household_id, seed))) % (2**32))
    noise = rng.normal(loc=1.0, scale=0.12, size=len(idx))
    values = np.clip(base * noise, 0.01, None)
    return normalize_to_annual_kwh(values)


def main() -> None:
    idx = year_datetime_index()
    index_entries = []

    for household in HOUSEHOLD_TYPES:
        for seed in SEEDS:
            values = build_profile(household.id, seed, idx)
            write_profile_json(DATA_DIR / "profiles" / f"{household.id}__seed{seed}.json", {
                "type": household.id,
                "seed": seed,
                "resolution_min": RESOLUTION_MIN,
                "values_kwh": values.tolist(),
                "source": "SYNTHETISCHER PLATZHALTER (kein LPG) -- siehe generate_household_profiles_lpg.py",
            })
        index_entries.append({
            "id": household.id,
            "display_name": household.display_name,
            "description": household.description,
            "typical_annual_kwh": household.typical_annual_kwh,
            "seeds": list(SEEDS),
            "file_pattern": "profiles/{id}__seed{seed}.json",
        })
        print(f"Geschrieben: profiles/{household.id}__seed{{1,2,3}}.json")

    write_index_json(DATA_DIR / "profiles_index.json", {
        "resolution_min": RESOLUTION_MIN,
        "slots_per_year": SLOTS_PER_YEAR,
        "reference_year": idx[0].year,
        "data_source": "placeholder",
        "households": index_entries,
    })
    print("Geschrieben: profiles_index.json")
    print(
        "\nHinweis: Dies sind SYNTHETISCHE PLATZHALTERPROFILE. Fuer realistische, "
        "verhaltensbasierte Lastprofile tools/generate_household_profiles_lpg.py lokal "
        "mit installiertem pylpg/LoadProfileGenerator ausfuehren (siehe README)."
    )


if __name__ == "__main__":
    main()
