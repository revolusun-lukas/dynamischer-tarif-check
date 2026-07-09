"""Kostenvergleich beliebig vieler Fix-/dynamischer Tarife auf Basis stündlicher Verbrauchs- und Preisdaten."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

LOCAL_TZ = "Europe/Berlin"


def _day_hours(
    day: date,
    local_dates: pd.DatetimeIndex,
    usable: pd.Series,
    price_series: dict[str, pd.Series],
    cost_series: dict[str, pd.Series],
    names: list[str],
) -> list[dict]:
    mask = local_dates.date == day
    hours_local = local_dates.hour[mask]
    cons = usable.values[mask]
    prices = {n: price_series[n].values[mask] for n in names}
    costs = {n: cost_series[n].values[mask] for n in names}

    return [
        {
            "hour": f"{h:02d}:00",
            "consumption_kwh": round(float(cons[i]), 3),
            "prices_ct_kwh": {n: round(float(prices[n][i]), 2) for n in names},
            "costs_eur": {n: round(float(costs[n][i]), 4) for n in names},
        }
        for i, h in enumerate(hours_local)
    ]


def calculate_comparison(hourly_kwh: pd.Series, prices_eur_mwh: dict, tariffs: list) -> dict:
    idx = hourly_kwh.index
    has_price = pd.Series([h in prices_eur_mwh for h in idx], index=idx)
    hours_missing = int((~has_price).sum())

    usable = hourly_kwh[has_price]
    if usable.empty:
        raise ValueError("Keine Überschneidung zwischen Verbrauchsdaten und Preisdaten gefunden.")

    # Negative Stundenwerte (z. B. aus älteren, vor dem Aggregations-Fix gespeicherten
    # Beispiel-Datensätzen) würden sonst als "vergütete" Einspeisung in die Kosten einfließen.
    usable = usable.clip(lower=0)

    usable_index = usable.index
    market_eur_mwh = pd.Series([prices_eur_mwh[h] for h in usable_index], index=usable_index)

    # idx.max() ist der Beginn der letzten Stunde, daher +1h um das Intervallende zu erhalten.
    period_days = ((idx.max() + timedelta(hours=1)) - idx.min()).total_seconds() / 86400

    names: list[str] = []
    tariff_types: dict[str, str] = {}
    price_series: dict[str, pd.Series] = {}
    cost_series: dict[str, pd.Series] = {}
    totals: dict[str, float] = {}

    for tariff in tariffs:
        name = tariff.name
        if name in tariff_types:
            raise ValueError(f"Tarifname '{name}' wird mehrfach verwendet. Bitte eindeutige Namen vergeben.")

        if tariff.type == "dynamic":
            price_ct_kwh = (market_eur_mwh / 10) * (1 + tariff.mwst_percent / 100) + tariff.aufschlag_ct_kwh
        else:
            price_ct_kwh = pd.Series(tariff.arbeitspreis_ct_kwh, index=usable_index)

        cost_hourly = usable * price_ct_kwh / 100
        grundgebuehr = tariff.grundgebuehr_eur_monat * (period_days / 30.44)  # 30.44 = mittlere Tage/Monat

        names.append(name)
        tariff_types[name] = tariff.type
        price_series[name] = price_ct_kwh
        cost_series[name] = cost_hourly
        totals[name] = float(cost_hourly.sum() + grundgebuehr)

    cheapest_name = min(names, key=lambda n: totals[n])
    most_expensive_name = max(names, key=lambda n: totals[n])
    savings_vs_most_expensive = totals[most_expensive_name] - totals[cheapest_name]
    savings_percent = (
        (savings_vs_most_expensive / totals[most_expensive_name] * 100) if totals[most_expensive_name] else 0.0
    )

    local_dates = usable_index.tz_convert(LOCAL_TZ)
    daily_df = pd.DataFrame({name: cost_series[name].values for name in names}, index=local_dates)
    daily_df["date"] = daily_df.index.date
    daily_grouped = daily_df.groupby("date")[names].sum().reset_index().sort_values("date").reset_index(drop=True)

    daily_out = [
        {"date": row["date"].isoformat(), "costs": {n: round(float(row[n]), 4) for n in names}}
        for _, row in daily_grouped.iterrows()
    ]

    # Bester/schlechtester Tag: immer aus Sicht des zweiten Tarifs (des "dynamischen") im Vergleich zum ersten.
    reference_name, compare_name = names[0], names[1]
    daily_grouped["diff"] = daily_grouped[reference_name] - daily_grouped[compare_name]

    best_row = daily_grouped.loc[daily_grouped["diff"].idxmax()]
    worst_row = daily_grouped.loc[daily_grouped["diff"].idxmin()]

    def day_highlight(row) -> dict:
        day = row["date"]
        return {
            "date": day.isoformat(),
            "diff_eur": round(float(row["diff"]), 2),
            "reference_name": reference_name,
            "compare_name": compare_name,
            "cost_reference_eur": round(float(row[reference_name]), 2),
            "cost_compare_eur": round(float(row[compare_name]), 2),
            "hours": _day_hours(day, local_dates, usable, price_series, cost_series, [reference_name, compare_name]),
        }

    return {
        "tariffs": [{"name": n, "type": tariff_types[n], "total_eur": round(totals[n], 2)} for n in names],
        "cheapest_name": cheapest_name,
        "most_expensive_name": most_expensive_name,
        "savings_vs_most_expensive_eur": round(savings_vs_most_expensive, 2),
        "savings_vs_most_expensive_percent": round(savings_percent, 2),
        "period_days": round(period_days, 2),
        "hours_total": int(len(idx)),
        "hours_missing_price": hours_missing,
        "daily": daily_out,
        "best_day": day_highlight(best_row),
        "worst_day": day_highlight(worst_row),
    }
