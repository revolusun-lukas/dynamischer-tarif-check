"""Laden der kuratierten Beispiel-Haushalte (siehe scripts/process_examples.py).

Die Rohdaten dahinter (examples/raw/, das Verarbeitungsskript) sind bewusst nicht
Teil des Deployments -- hier wird nur das bereits aggregierte, anonymisierte Ergebnis
gelesen: eine Registry-CSV mit den Haushaltseigenschaften und je eine Stunden-kWh-Datei
pro Haushalt.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = PROJECT_ROOT / "examples" / "processed" / "registry.csv"
DATA_DIR = PROJECT_ROOT / "examples" / "processed" / "data"

BOOL_COLUMNS = ["balkonkraftwerk", "pv", "speicher", "waermepumpe", "durchlauferhitzer", "elektroauto"]


class ExampleNotFoundError(Exception):
    pass


def load_registry() -> list[dict]:
    """Liste aller kuratierten Beispiel-Haushalte. Leer, solange noch keine gepflegt wurden."""
    if not REGISTRY_PATH.exists():
        return []

    df = pd.read_csv(REGISTRY_PATH)
    for col in BOOL_COLUMNS:
        df[col] = df[col].astype(str).str.strip().str.lower().isin(["true", "1", "ja"])
    return df.to_dict(orient="records")


def load_example_series(example_id: str) -> pd.Series:
    """Lädt die Stunden-kWh-Zeitreihe eines Beispiel-Haushalts (Format wie von
    aggregation.build_hourly_series() erzeugt, damit die Kostenberechnung sie
    unverändert weiterverarbeiten kann)."""
    data_path = DATA_DIR / f"{example_id}.csv"
    if not data_path.exists():
        raise ExampleNotFoundError(f"Unbekannter Beispiel-Haushalt: {example_id}")

    df = pd.read_csv(data_path)
    index = pd.to_datetime(df["timestamp_utc"], utc=True)
    series = pd.Series(df["kwh"].values, index=index).sort_index()
    series.index.name = "hour_utc"
    return series
