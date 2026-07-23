"""Gemeinsame Helfer fuer alle Profilgenerierungs-Skripte unter tools/.

Definiert das gemeinsame Format, in dem alle Verbrauchs-/Erzeugungsprofile
fuer den Live-Rechner (static/live-check.html) abgelegt werden: 15-Minuten-
Aufloesung, ein volles (synthetisches) Kalenderjahr, normiert auf eine feste
Jahressumme in kWh. So kann das Frontend jedes Profil mit dem gleichen Code
laden, auf den tatsaechlichen Jahresverbrauch skalieren und ueberlagern.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

RESOLUTION_MIN = 15
SLOTS_PER_DAY = 24 * 60 // RESOLUTION_MIN  # 96
REFERENCE_YEAR = 2023  # nicht-schaltjahr -> exakt 365 Tage / 35040 Slots
SLOTS_PER_YEAR = 365 * SLOTS_PER_DAY  # 35040

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "static" / "data"


def year_datetime_index() -> pd.DatetimeIndex:
    """Zeitstempel (tz-naiv) fuer jeden 15-Minuten-Slot eines generischen Jahres.

    Dient nur zur Ableitung von Wochentag/Uhrzeit fuer die synthetischen
    Modelle -- nicht als echter Kalenderbezug (siehe README, Abschnitt
    "Live-Rechner": Profile sind repraesentativ, kein historischer Bezug).
    """
    start = pd.Timestamp(year=REFERENCE_YEAR, month=1, day=1)
    return pd.date_range(start, periods=SLOTS_PER_YEAR, freq="15min")


def normalize_to_annual_kwh(values: np.ndarray, target_kwh: float = 1000.0) -> np.ndarray:
    """Skaliert values so, dass die Jahressumme exakt target_kwh ergibt."""
    values = np.clip(np.asarray(values, dtype=float), 0.0, None)
    total = values.sum()
    if total <= 0:
        raise ValueError("Profil ist leer/komplett null, kann nicht normiert werden.")
    return values * (target_kwh / total)


def write_profile_json(path: Path, payload: dict, decimals: int = 5) -> None:
    """Schreibt ein Profil-JSON, rundet 'values_kwh' (falls vorhanden) zur Groessenreduktion.

    Die eigentliche gzip-Kompression passiert nicht hier, sondern zur
    Laufzeit ueber GZipMiddleware in app/main.py (siehe README) -- so bleiben
    die Dateien im Repo als lesbares, diff-bares JSON.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload)
    if "values_kwh" in out:
        out["values_kwh"] = [round(float(v), decimals) for v in out["values_kwh"]]
    with path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))


def write_index_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
