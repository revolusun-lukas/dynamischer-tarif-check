"""Erzeugt die ECHTEN Haushaltsprofile mit dem LoadProfileGenerator (LPG) ueber pylpg.

WICHTIG -- vor dem ersten Lauf lesen:
  Dieses Skript ist ein Geruest/Scaffold, kein fertig getesteter Produktionscode.
  pylpg (https://github.com/FZJ-IEK3-VSA/pylpg, PyPI-Paket "pyloadprofilegenerator")
  laedt beim ersten Aufruf die vollstaendige LoadProfileGenerator-Engine (.NET/Java-
  Binaries + Verhaltensdatenbank, mehrere hundert MB) herunter und fuehrt lokal eine
  Simulation aus -- das ist in der Entwicklungsumgebung, in der dieses Projekt gebaut
  wurde, NICHT moeglich (kein Internetzugang fuer derart grosse Downloads, keine
  Java/.NET-Runtime). Der Aufruf unten (LPGExecutor, HouseholdTemplates, ...) folgt der
  in der pylpg-Dokumentation beschriebenen Grundstruktur (JSON-Request -> Binary
  ausfuehren -> Ergebnis als pandas-DataFrame), MUSS aber vor dem produktiven Einsatz
  gegen die tatsaechlich installierte pylpg-Version geprueft/angepasst werden (Klassen-
  und Methodennamen koennen sich zwischen Versionen unterscheiden).

  Ausfuehren (braucht lokal: Python-Umgebung mit installiertem "pyloadprofilegenerator",
  Internetzugang fuer den einmaligen Download der LPG-Engine, spuerbar Rechenzeit --
  7 Haushaltstypen x 3 Seeds x 1 Jahr in 15-Minuten-Aufloesung dauert je nach Maschine
  mehrere Minuten bis Stunden):

      pip install pyloadprofilegenerator
      python tools/generate_household_profiles_lpg.py

  Ergebnis landet in denselben Dateien wie generate_household_profiles_placeholder.py
  (static/data/profiles/<typ>__seed<n>.json, profiles_index.json) -- das Frontend
  unterscheidet nicht zwischen Platzhalter- und LPG-Daten, es liest nur das JSON-Format.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.household_types import HOUSEHOLD_TYPES, SEEDS  # noqa: E402
from tools.profile_shared import (  # noqa: E402
    DATA_DIR,
    RESOLUTION_MIN,
    REFERENCE_YEAR,
    SLOTS_PER_YEAR,
    normalize_to_annual_kwh,
    write_index_json,
    write_profile_json,
)


def run_lpg_simulation(lpg_template_hint: str, seed: int) -> pd.Series:
    """Fuehrt eine Ein-Jahres-Simulation fuer eine LPG-Haushaltsvorlage aus und liefert
    den elektrischen Gesamtverbrauch (kWh) je 15-Minuten-Slot als pandas Series.

    Muss ggf. an die installierte pylpg-Version angepasst werden -- siehe Docstring
    oben. Die grobe Form (Import, Executor, Zeitraum/Aufloesung, Ergebnis als
    DataFrame/Series mit Stromsumme) entspricht dem in der pylpg-Dokumentation
    beschriebenen Ablauf.
    """
    from pylpg import HouseholdTemplates, LPGExecutor  # type: ignore  # pylint: disable=import-error

    executor = LPGExecutor()
    result = executor.run(
        household_template=lpg_template_hint,
        start_date=f"{REFERENCE_YEAR}-01-01",
        end_date=f"{REFERENCE_YEAR + 1}-01-01",
        resolution_minutes=RESOLUTION_MIN,
        random_seed=seed,
    )
    # Erwartung laut Doku: result ist ein DataFrame mit Zeitindex; die Summenlastspalte
    # fuer elektrischen Gesamtverbrauch heisst i.d.R. "Sum" oder aehnlich -- ggf. Spaltennamen
    # nach dem ersten echten Lauf per print(result.columns) pruefen und hier anpassen.
    column = "Sum" if "Sum" in result.columns else result.columns[0]
    return result[column].astype(float)


def main() -> None:
    index_entries = []

    for household in HOUSEHOLD_TYPES:
        for seed in SEEDS:
            series = run_lpg_simulation(household.lpg_template_hint, seed)
            values = series.to_numpy()
            if len(values) != SLOTS_PER_YEAR:
                # LPG liefert ggf. eine andere Aufloesung/Laenge -- auf 35040 Slots resamplen.
                values = np.interp(
                    np.linspace(0, len(values), SLOTS_PER_YEAR, endpoint=False),
                    np.arange(len(values)),
                    values,
                )
            values = normalize_to_annual_kwh(values)

            write_profile_json(DATA_DIR / "profiles" / f"{household.id}__seed{seed}.json", {
                "type": household.id,
                "seed": seed,
                "resolution_min": RESOLUTION_MIN,
                "values_kwh": values.tolist(),
                "source": f"LoadProfileGenerator (pylpg), Vorlage {household.lpg_template_hint}, Seed {seed}",
            })
            print(f"Geschrieben: profiles/{household.id}__seed{seed}.json")

        index_entries.append({
            "id": household.id,
            "display_name": household.display_name,
            "description": household.description,
            "typical_annual_kwh": household.typical_annual_kwh,
            "seeds": list(SEEDS),
            "file_pattern": "profiles/{id}__seed{seed}.json",
        })

    write_index_json(DATA_DIR / "profiles_index.json", {
        "resolution_min": RESOLUTION_MIN,
        "slots_per_year": SLOTS_PER_YEAR,
        "reference_year": REFERENCE_YEAR,
        "data_source": "lpg",
        "households": index_entries,
    })
    print("Geschrieben: profiles_index.json (data_source: lpg)")


if __name__ == "__main__":
    main()
