"""Kostenvergleich beliebig vieler Fix-/dynamischer Tarife auf Basis stündlicher Verbrauchs- und Preisdaten."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

LOCAL_TZ = "Europe/Berlin"


@dataclass
class CalculationDetail:
    """Stundengenaue Zwischenergebnisse der letzten Berechnung. Wird in der Session abgelegt, damit
    die Tagesanalyse für ein beliebiges Tarifpaar nachgeladen werden kann, ohne neu zu rechnen."""

    local_index: pd.DatetimeIndex
    consumption_kwh: pd.Series
    prices_ct_kwh: dict[str, pd.Series]  # Arbeitspreis, NaN bei fehlendem Börsenpreis
    all_in_ct_kwh: dict[str, pd.Series]  # Arbeitspreis + Grundgebühr-Anteil je kWh
    costs_eur: dict[str, pd.Series]  # Energie + Grundgebühr-Anteil


def _month_keys(local_index: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray(local_index.year * 100 + local_index.month)


def _hours_in_month(key: int) -> float:
    year, month = divmod(int(key), 100)
    start = pd.Timestamp(year=year, month=month, day=1, tz=LOCAL_TZ)
    end = start + pd.offsets.MonthBegin(1)
    return (end - start).total_seconds() / 3600


def _base_fee_weights(full_index: pd.DatetimeIndex, local_index: pd.DatetimeIndex, kwh_full: pd.Series):
    """Verteilt je Kalendermonat die Grundgebühr proportional zum Verbrauch des Monats.

    Liefert (weight, per_kwh): weight[h] * Monatsgrundgebühr = Grundgebühr-Anteil der Stunde h;
    per_kwh[h] * Monatsgrundgebühr = Grundgebühr-Anteil je kWh in ct (im Monat konstant).
    Angebrochene Monate am Anfang/Ende zahlen nur ihren zeitlichen Anteil. Monate ganz ohne
    Verbrauch verteilen ihren Anteil gleichmäßig auf die Stunden (die Gebühr fällt trotzdem an).
    """
    months = pd.Series(_month_keys(local_index), index=full_index)
    covered_hours = months.map(months.value_counts())
    month_fraction = months.map({k: n / _hours_in_month(k) for k, n in months.value_counts().items()})
    kwh_month = kwh_full.groupby(months).transform("sum")

    has_kwh = kwh_month > 0
    weight = pd.Series(
        np.where(has_kwh, kwh_full / kwh_month.where(has_kwh, 1.0), 1.0 / covered_hours),
        index=full_index,
    ) * month_fraction
    per_kwh = (month_fraction / kwh_month.where(has_kwh) * 100).fillna(0.0)
    return weight, per_kwh


def calculate_comparison(
    hourly_kwh: pd.Series, prices_eur_mwh: dict, tariffs: list
) -> tuple[dict, CalculationDetail]:
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
    total_kwh = float(usable.sum())

    # Lückenloses Stundenraster über den gesamten Zeitraum: Die Grundgebühr fällt für jeden
    # Monat an -- auch für Stunden ohne Preisdaten oder ohne Verbrauchswert.
    full_index = pd.date_range(idx.min(), idx.max(), freq="h")
    period_days = len(full_index) / 24
    local_index = full_index.tz_convert(LOCAL_TZ)
    # Stunden ohne Börsenpreis gehen mit 0 kWh in die Rechnung ein (bei allen Tarifen gleich).
    kwh_full = usable.reindex(full_index, fill_value=0.0)
    base_weight, base_per_kwh = _base_fee_weights(full_index, local_index, kwh_full)

    names: list[str] = []
    tariff_types: dict[str, str] = {}
    prices: dict[str, pd.Series] = {}
    all_in: dict[str, pd.Series] = {}
    costs: dict[str, pd.Series] = {}
    energy_totals: dict[str, float] = {}
    base_totals: dict[str, float] = {}
    bonus_totals: dict[str, float] = {}
    totals: dict[str, float] = {}

    for tariff in tariffs:
        name = tariff.name
        if name in tariff_types:
            raise ValueError(f"Tarifname '{name}' wird mehrfach verwendet. Bitte eindeutige Namen vergeben.")

        # Alle Tarifangaben sind brutto. Beim dynamischen Tarif ist der Börsenpreis netto und
        # bekommt die MwSt., der Aufschlag enthält bereits alles (Netz, Steuern, Umlagen, Marge, MwSt.).
        if tariff.type == "dynamic":
            price_ct_kwh = (market_eur_mwh / 10) * (1 + tariff.mwst_percent / 100) + tariff.aufschlag_ct_kwh
        else:
            price_ct_kwh = pd.Series(tariff.arbeitspreis_ct_kwh, index=usable_index)
        price_full = price_ct_kwh.reindex(full_index)

        energy = (kwh_full * price_full / 100).fillna(0.0)
        base = base_weight * tariff.grundgebuehr_eur_monat

        # Bonus (Neukunden-/Sofortbonus, nur Fixtarif): gilt einmalig fürs erste Vertragsjahr und
        # wird wie eine negative Grundgebühr verteilt -- 1/12 je Monat. Kürzere Zeiträume bekommen
        # ihn anteilig, längere höchstens einmal (Monatsrate dann entsprechend kleiner).
        bonus_per_month = 0.0
        if getattr(tariff, "bonus_eur", 0) > 0:
            months_in_period = float(base_weight.sum())
            bonus_per_month = tariff.bonus_eur / 12 * min(1.0, 12 / months_in_period)
        bonus = base_weight * bonus_per_month

        names.append(name)
        tariff_types[name] = tariff.type
        prices[name] = price_full
        all_in[name] = price_full + base_per_kwh * (tariff.grundgebuehr_eur_monat - bonus_per_month)
        costs[name] = energy + base - bonus
        energy_totals[name] = float(energy.sum())
        base_totals[name] = float(base.sum())
        bonus_totals[name] = float(bonus.sum())
        totals[name] = energy_totals[name] + base_totals[name] - bonus_totals[name]

    cheapest_name = min(names, key=lambda n: totals[n])
    most_expensive_name = max(names, key=lambda n: totals[n])
    savings_vs_most_expensive = totals[most_expensive_name] - totals[cheapest_name]
    savings_percent = (
        (savings_vs_most_expensive / totals[most_expensive_name] * 100) if totals[most_expensive_name] else 0.0
    )

    # Tageswerte inkl. Grundgebühr-Anteil -- summieren sich exakt zu den Gesamtkosten.
    daily = pd.DataFrame(costs).groupby(local_index.date).sum().sort_index()
    daily_out = [
        {"date": day.isoformat(), "costs": {n: round(float(row[n]), 4) for n in names}}
        for day, row in daily.iterrows()
    ]

    result = {
        "tariffs": [
            {
                "name": n,
                "type": tariff_types[n],
                "total_eur": round(totals[n], 2),
                "energy_cost_eur": round(energy_totals[n], 2),
                "base_fee_eur": round(base_totals[n], 2),
                "bonus_eur": round(bonus_totals[n], 2),
                # Verbrauchsgewichteter Ø-Arbeitspreis (ohne Grundgebühr) -- direkt vergleichbar
                # mit dem Arbeitspreis eines Fixtarifs.
                "avg_price_ct_kwh": round(energy_totals[n] / total_kwh * 100, 2) if total_kwh else 0.0,
            }
            for n in names
        ],
        "total_kwh": round(total_kwh, 1),
        "cheapest_name": cheapest_name,
        "most_expensive_name": most_expensive_name,
        "savings_vs_most_expensive_eur": round(savings_vs_most_expensive, 2),
        "savings_vs_most_expensive_percent": round(savings_percent, 2),
        "period_days": round(period_days, 2),
        "hours_total": int(len(idx)),
        "hours_missing_price": hours_missing,
        "daily": daily_out,
    }
    detail = CalculationDetail(
        local_index=local_index,
        consumption_kwh=kwh_full,
        prices_ct_kwh=prices,
        all_in_ct_kwh=all_in,
        costs_eur=costs,
    )
    return result, detail


def _round_or_none(value: float, digits: int):
    return None if pd.isna(value) else round(float(value), digits)


def pair_analysis(detail: CalculationDetail, names: list[str]) -> dict:
    """Gesamtzeitraum-Analyse für ein Tarifpaar: Tagesprofil (je Stunde des Tages) und Profilfaktor.

    Profilfaktor = verbrauchsgewichteter Ø-Arbeitspreis − zeitlicher Ø-Arbeitspreis. Negativ heißt:
    Der Verbrauch fällt überdurchschnittlich in günstige Stunden (nur bei dynamischen Tarifen != 0).
    """
    for n in names:
        if n not in detail.costs_eur:
            raise ValueError(f"Tarif '{n}' ist in der letzten Berechnung nicht enthalten.")

    hour_of_day = detail.local_index.hour
    kwh = detail.consumption_kwh
    total_kwh = float(kwh.sum())
    kwh_by_hour = kwh.groupby(hour_of_day).sum()
    # Ø je Tag: Summe dieser Uhrzeit ÷ Anzahl Tage, an denen es diese Uhrzeit im Zeitraum gab.
    kwh_avg_by_hour = kwh.groupby(hour_of_day).mean()

    avg_price_by_hour: dict[str, pd.Series] = {}
    cost_by_hour: dict[str, pd.Series] = {}
    profile: dict[str, dict] = {}
    for n in names:
        price = detail.prices_ct_kwh[n]
        has_price = price.notna()
        # Zeitlicher Ø je Tagesstunde -- zeigt den typischen Preisverlauf, unabhängig vom Verbrauch.
        avg_price_by_hour[n] = price[has_price].groupby(hour_of_day[has_price.values]).mean()
        cost_by_hour[n] = detail.costs_eur[n].groupby(hour_of_day).sum()

        kwh_priced = kwh[has_price]
        weighted = float((price[has_price] * kwh_priced).sum() / kwh_priced.sum()) if kwh_priced.sum() > 0 else None
        time_avg = float(price[has_price].mean()) if has_price.any() else None
        profile[n] = {
            "weighted_avg_ct_kwh": _round_or_none(weighted, 2),
            "time_avg_ct_kwh": _round_or_none(time_avg, 2),
            "profile_factor_ct_kwh": _round_or_none(
                weighted - time_avg if weighted is not None and time_avg is not None else None, 2
            ),
        }

    return {
        "profile": profile,
        "hours": [
            {
                "hour": h,
                "consumption_kwh": round(float(kwh_by_hour.get(h, 0.0)), 3),
                "avg_consumption_kwh": round(float(kwh_avg_by_hour.get(h, 0.0)), 3),
                "consumption_share": round(float(kwh_by_hour.get(h, 0.0)) / total_kwh, 4) if total_kwh else 0.0,
                "avg_price_ct_kwh": {n: _round_or_none(avg_price_by_hour[n].get(h), 2) for n in names},
                "costs_eur": {n: round(float(cost_by_hour[n].get(h, 0.0)), 2) for n in names},
            }
            for h in range(24)
        ],
    }


def day_detail(detail: CalculationDetail, day: date, names: list[str]) -> dict:
    """Stundenwerte eines Tages für die gewählten Tarife (Kosten inkl. Grundgebühr-Anteil)."""
    for n in names:
        if n not in detail.costs_eur:
            raise ValueError(f"Tarif '{n}' ist in der letzten Berechnung nicht enthalten.")

    mask = detail.local_index.date == day
    if not mask.any():
        raise ValueError("Für diesen Tag liegen keine Daten vor.")

    hours = detail.local_index[mask]
    cons = detail.consumption_kwh.values[mask]
    prices = {n: detail.prices_ct_kwh[n].values[mask] for n in names}
    all_in = {n: detail.all_in_ct_kwh[n].values[mask] for n in names}
    costs = {n: detail.costs_eur[n].values[mask] for n in names}

    return {
        "date": day.isoformat(),
        "consumption_kwh": round(float(cons.sum()), 3),
        # 4 Nachkommastellen wie bei den Tageswerten, damit die im Frontend gebildete
        # Differenz nicht durch doppeltes Runden um einen Cent abweicht.
        "totals_eur": {n: round(float(costs[n].sum()), 4) for n in names},
        "hours": [
            {
                "hour": f"{ts.hour:02d}:00",
                "consumption_kwh": round(float(cons[i]), 3),
                "prices_ct_kwh": {n: _round_or_none(prices[n][i], 2) for n in names},
                "all_in_ct_kwh": {n: _round_or_none(all_in[n][i], 2) for n in names},
                "costs_eur": {n: round(float(costs[n][i]), 4) for n in names},
            }
            for i, ts in enumerate(hours)
        ],
    }
