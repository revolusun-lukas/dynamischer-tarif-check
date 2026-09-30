"""Pydantic-Modelle für die API-Requests/-Responses."""
from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal, Optional, Union

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

ValueType = Literal["power_w", "power_kw", "energy_wh", "energy_kwh", "counter_kwh"]
TimezoneMode = Literal["Europe/Berlin", "UTC"]

# Tarifnamen landen ungeprueft in mehreren innerHTML-Sinks im Frontend (Ergebnis-Kacheln,
# Tabellen-Header, Chart-Legende) -- da ein Tarifname keinen legitimen Grund hat, HTML-
# Sonderzeichen zu enthalten, wird hier serverseitig hart abgelehnt statt nur escaped.
# Das Frontend escaped zusaetzlich beim Rendern (Defense in Depth), siehe static/js/app.js.
_UNSAFE_NAME_CHARS_RE = re.compile(r'[<>"\'`]')


def _reject_html_like_chars(value: str) -> str:
    if _UNSAFE_NAME_CHARS_RE.search(value):
        raise ValueError("Der Name darf keine der Zeichen < > \" ' ` enthalten.")
    return value


# strip_whitespace, damit "Fix" und "Fix " nicht als zwei verschiedene Tarife durchgehen
# und ein Name nur aus Leerzeichen an min_length scheitert.
SafeName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
    AfterValidator(_reject_html_like_chars),
]


class ImportUploadResponse(BaseModel):
    session_id: str
    columns: list[str]
    preview_rows: list[dict]
    suggested_timestamp_column: Optional[str]
    suggested_value_column: Optional[str]
    suggested_value_type: Optional[ValueType]
    suggested_timezone: TimezoneMode
    row_count: int
    warnings: list[str]


class ImportConfirmRequest(BaseModel):
    session_id: str
    timestamp_column: str
    value_column: str
    value_type: ValueType
    timezone: TimezoneMode = "Europe/Berlin"


class ImportConfirmResponse(BaseModel):
    session_id: str
    start_date: str
    end_date: str
    total_kwh: float
    hours_count: int
    warnings: list[str]


class ExampleHousehold(BaseModel):
    id: str
    haushaltsgroesse: int
    balkonkraftwerk: bool
    pv: bool
    speicher: bool
    waermepumpe: bool
    durchlauferhitzer: bool
    elektroauto: bool
    start_date: str
    end_date: str
    total_kwh: float
    hours_count: int


class ExampleListResponse(BaseModel):
    examples: list[ExampleHousehold]


class DonateRequest(BaseModel):
    session_id: str
    haushaltsgroesse: int = Field(gt=0)
    balkonkraftwerk: bool
    pv: bool
    speicher: bool
    waermepumpe: bool
    durchlauferhitzer: bool
    elektroauto: bool


class DonateResponse(BaseModel):
    message: str


class ScenarioHousehold(BaseModel):
    id: str
    display_name: str
    description: str
    typical_annual_kwh: int


class ScenarioHouseholdListResponse(BaseModel):
    households: list[ScenarioHousehold]


class ScenarioEvInput(BaseModel):
    enabled: bool = False
    km_per_year: float = Field(ge=0, default=0)
    kwh_per_100km: float = Field(gt=0, le=60, default=18)
    mode: Literal["uncontrolled", "controlled"] = "uncontrolled"


class ScenarioHeatpumpInput(BaseModel):
    enabled: bool = False
    annual_kwh: float = Field(ge=0, default=0)


class ScenarioPvInput(BaseModel):
    enabled: bool = False
    kwp: float = Field(ge=0, le=100, default=0)
    orientation: Literal["S", "SE", "SW", "E", "W", "EW"] = "S"
    tilt: float = Field(ge=0, le=90, default=30)


class ScenarioBalconyInput(BaseModel):
    # Modulleistung darf über 0,8 kWp liegen -- eingespeist werden höchstens 800 W (Wechselrichter).
    enabled: bool = False
    kwp: float = Field(ge=0, le=3, default=0.8)
    orientation: Literal["S", "SE", "SW", "E", "W"] = "S"


class ScenarioLocation(BaseModel):
    # Standard: geografische Mitte Deutschlands, solange kein Ort gewählt ist.
    name: str = Field(default="Deutschland-Mitte", max_length=120)
    latitude: float = Field(ge=47, le=55.5, default=51.0)
    longitude: float = Field(ge=5.5, le=15.5, default=10.0)


class GeocodeResult(BaseModel):
    name: str
    region: str
    latitude: float
    longitude: float


class GeocodeResponse(BaseModel):
    results: list[GeocodeResult]


class ScenarioBuildRequest(BaseModel):
    household_id: str
    location: ScenarioLocation = ScenarioLocation()
    annual_kwh: float = Field(gt=0)
    flex_percent: float = Field(ge=0, le=30, default=0)
    # Wohin verschiebbare Lasten wandern: günstigste Börsenstunden oder Stunden mit PV-Erzeugung.
    flex_target: Literal["cheap", "sunny"] = "cheap"
    ev: ScenarioEvInput = ScenarioEvInput()
    heatpump: ScenarioHeatpumpInput = ScenarioHeatpumpInput()
    pv: ScenarioPvInput = ScenarioPvInput()
    balcony: ScenarioBalconyInput = ScenarioBalconyInput()


class ScenarioPreviewResponse(BaseModel):
    household_kwh: float
    ev_kwh: float
    heatpump_kwh: float
    total_consumption_kwh: float
    pv_production_kwh: float
    balcony_production_kwh: float
    pv_self_consumption_kwh: float  # Eigenverbrauch aus PV-Anlage und Balkonkraftwerk zusammen
    pv_only_self_consumption_kwh: float  # davon PV-Anlage
    balcony_self_consumption_kwh: float  # davon Balkonkraftwerk
    grid_kwh: float
    reference_year: int  # Kalenderjahr, dessen Wetter/Preise verwendet werden


class ScenarioBuildResponse(BaseModel):
    session_id: str
    start_date: str
    end_date: str
    total_kwh: float
    hours_count: int
    warnings: list[str]
    summary_lines: list[str]


class FixTariffInput(BaseModel):
    type: Literal["fix"] = "fix"
    name: SafeName
    arbeitspreis_ct_kwh: float = Field(gt=0)
    grundgebuehr_eur_monat: float = Field(ge=0)
    # Einmaliger Bonus fürs erste Vertragsjahr (Neukunden- + Sofortbonus, in €).
    bonus_eur: float = Field(ge=0, le=2000, default=0)


class DynamicTariffInput(BaseModel):
    type: Literal["dynamic"] = "dynamic"
    name: SafeName
    mwst_percent: float = Field(ge=0)
    aufschlag_ct_kwh: float = Field(ge=0)
    grundgebuehr_eur_monat: float = Field(ge=0)
    # Einmaliger Bonus/Rabatt fürs erste Vertragsjahr (z.B. Grundpreisrabatt), in €.
    bonus_eur: float = Field(ge=0, le=2000, default=0)
    # Einmalige Kosten für den Einbau des Smart Meters (intelligentes Messsystem mit Gateway),
    # gesetzliche Obergrenze beim Einbau auf Wunsch 100 €; wird aufs erste Jahr verteilt.
    smartmeter_einbau_eur: float = Field(ge=0, le=2000, default=0)


class SpotAverageResponse(BaseModel):
    avg_ct_kwh_netto: float  # zeitlicher Ø-Börsenpreis ohne MwSt.
    start_date: str
    end_date: str


TariffInput = Annotated[Union[FixTariffInput, DynamicTariffInput], Field(discriminator="type")]


class CalculateRequest(BaseModel):
    session_id: str
    tariffs: list[TariffInput] = Field(min_length=2, max_length=8)


class TariffTotal(BaseModel):
    name: str
    type: Literal["fix", "dynamic"]
    total_eur: float
    energy_cost_eur: float
    base_fee_eur: float
    bonus_eur: float
    smartmeter_einbau_eur: float
    avg_price_ct_kwh: float


class DailyCost(BaseModel):
    date: str
    costs: dict[str, float]


class DayDetailRequest(BaseModel):
    session_id: str
    date: date
    tariff_names: list[str] = Field(min_length=2, max_length=2)


class DayHourDetail(BaseModel):
    hour: str
    consumption_kwh: float
    prices_ct_kwh: dict[str, Optional[float]]  # None = kein Börsenpreis für diese Stunde
    all_in_ct_kwh: dict[str, Optional[float]]
    costs_eur: dict[str, float]


class DayDetailResponse(BaseModel):
    date: str
    consumption_kwh: float
    totals_eur: dict[str, float]
    hours: list[DayHourDetail]


class PairAnalysisRequest(BaseModel):
    session_id: str
    tariff_names: list[str] = Field(min_length=2, max_length=2)


class TariffProfile(BaseModel):
    weighted_avg_ct_kwh: Optional[float]
    time_avg_ct_kwh: Optional[float]
    profile_factor_ct_kwh: Optional[float]


class HourOfDayStats(BaseModel):
    hour: int
    consumption_kwh: float
    avg_consumption_kwh: float
    consumption_share: float
    avg_price_ct_kwh: dict[str, Optional[float]]
    costs_eur: dict[str, float]


class PairAnalysisResponse(BaseModel):
    profile: dict[str, TariffProfile]
    hours: list[HourOfDayStats]


class CalculateResponse(BaseModel):
    tariffs: list[TariffTotal]
    cheapest_name: str
    most_expensive_name: str
    savings_vs_most_expensive_eur: float
    savings_vs_most_expensive_percent: float
    total_kwh: float
    period_days: float
    hours_total: int
    hours_missing_price: int
    daily: list[DailyCost]
