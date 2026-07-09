"""Umrechnung der vier Werte-Typen in Energie pro Intervall und Verteilung auf ein Stundenraster (UTC)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from app.importer.parsing import ValueType, parse_numeric, parse_timestamp_value


class AggregationError(Exception):
    pass


def _distribute_to_hours(start: datetime, end: datetime, energy_kwh: float) -> dict[datetime, float]:
    """Verteilt die Energie eines Intervalls (start, end] anteilig auf die überlappenden Stundenblöcke."""
    if end <= start or energy_kwh == 0:
        return {}

    total_seconds = (end - start).total_seconds()
    result: dict[datetime, float] = {}
    cursor = start
    while cursor < end:
        hour_start = cursor.replace(minute=0, second=0, microsecond=0)
        next_hour = hour_start + timedelta(hours=1)
        segment_end = min(next_hour, end)
        segment_seconds = (segment_end - cursor).total_seconds()
        share = segment_seconds / total_seconds
        result[hour_start] = result.get(hour_start, 0.0) + energy_kwh * share
        cursor = segment_end
    return result


def build_hourly_series(
    df: pd.DataFrame,
    timestamp_col: str,
    value_col: str,
    value_type: ValueType,
    timezone_name: str,
    decimal: str,
) -> tuple[pd.Series, list[str]]:
    """Baut aus den Rohzeilen eine auf volle Stunden (UTC) aggregierte kWh-Zeitreihe.

    Konvention: der Zeitstempel einer Zeile markiert das ENDE ihres Messintervalls,
    d.h. Intervall = (vorheriger_ts, aktueller_ts].
    """
    tz = ZoneInfo(timezone_name)
    warnings: list[str] = []

    timestamps = [parse_timestamp_value(v, tz) for v in df[timestamp_col].tolist()]
    raw_values = [parse_numeric(v, decimal) for v in df[value_col].tolist()]

    valid_rows = [
        (ts.astimezone(timezone.utc), val)
        for ts, val in zip(timestamps, raw_values)
        if ts is not None and val is not None
    ]

    dropped = len(timestamps) - len(valid_rows)
    if dropped:
        warnings.append(f"{dropped} Zeile(n) wurden übersprungen (Zeitstempel oder Wert nicht lesbar).")

    if len(valid_rows) < 2:
        raise AggregationError(
            "Nach dem Parsen blieben weniger als 2 gültige Datenpunkte übrig. "
            "Bitte Spaltenzuordnung, Werte-Typ und Zeitzone prüfen."
        )

    valid_rows.sort(key=lambda r: r[0])
    ts_utc = [row[0] for row in valid_rows]
    values = [row[1] for row in valid_rows]

    # Median statt Mittelwert, damit einzelne große Datenlücken die angenommene Intervalllänge
    # nicht verzerren. Wird nur für die allererste Zeile gebraucht (die keinen Vorgänger hat).
    deltas = [(t2 - t1) for t1, t2 in zip(ts_utc, ts_utc[1:]) if (t2 - t1).total_seconds() > 0]
    median_delta = sorted(deltas, key=lambda d: d.total_seconds())[len(deltas) // 2] if deltas else timedelta(hours=1)

    hourly: dict[datetime, float] = {}
    reset_count = 0

    if value_type == "counter_kwh":
        for i in range(1, len(values)):
            prev_ts, curr_ts = ts_utc[i - 1], ts_utc[i]
            diff = values[i] - values[i - 1]
            if diff < 0:
                reset_count += 1
                diff = 0.0
            for hour_start, share in _distribute_to_hours(prev_ts, curr_ts, diff).items():
                hourly[hour_start] = hourly.get(hour_start, 0.0) + share
        if reset_count:
            warnings.append(f"{reset_count} Zählerstand-Reset(s)/negative Sprünge wurden ignoriert (auf 0 gesetzt).")
    else:
        for i in range(len(values)):
            prev_ts = ts_utc[i - 1] if i > 0 else ts_utc[i] - median_delta
            curr_ts = ts_utc[i]
            interval_hours = max((curr_ts - prev_ts).total_seconds() / 3600, 1e-9)

            if value_type == "power_w":
                energy_kwh = values[i] * interval_hours / 1000.0
            elif value_type == "energy_wh":
                energy_kwh = values[i] / 1000.0
            elif value_type == "energy_kwh":
                energy_kwh = values[i]
            else:  # pragma: no cover - exhaustive ValueType
                raise AggregationError(f"Unbekannter Werte-Typ: {value_type}")

            for hour_start, share in _distribute_to_hours(prev_ts, curr_ts, energy_kwh).items():
                hourly[hour_start] = hourly.get(hour_start, 0.0) + share

    if not hourly:
        raise AggregationError("Es konnten keine Stundenwerte berechnet werden. Bitte Daten und Zuordnung prüfen.")

    series = pd.Series(hourly).sort_index()
    full_index = pd.date_range(series.index.min(), series.index.max(), freq="h", tz="UTC")
    series = series.reindex(full_index, fill_value=0.0)
    series.index.name = "hour_utc"

    return series, warnings
