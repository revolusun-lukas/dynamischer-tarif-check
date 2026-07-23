"""Pydantic-Modelle für die API-Requests/-Responses."""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

ValueType = Literal["power_w", "power_kw", "energy_wh", "energy_kwh", "counter_kwh"]
TimezoneMode = Literal["Europe/Berlin", "UTC"]


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
    mode: Literal["uncontrolled", "controlled"] = "uncontrolled"


class ScenarioHeatpumpInput(BaseModel):
    enabled: bool = False
    annual_kwh: float = Field(ge=0, default=0)


class ScenarioPvInput(BaseModel):
    enabled: bool = False
    kwp: float = Field(ge=0, default=0)


class ScenarioBuildRequest(BaseModel):
    household_id: str
    annual_kwh: float = Field(gt=0)
    flex_percent: float = Field(ge=0, le=30, default=0)
    ev: ScenarioEvInput = ScenarioEvInput()
    heatpump: ScenarioHeatpumpInput = ScenarioHeatpumpInput()
    pv: ScenarioPvInput = ScenarioPvInput()


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
    name: str = Field(min_length=1, max_length=40)
    arbeitspreis_ct_kwh: float = Field(gt=0)
    grundgebuehr_eur_monat: float = Field(ge=0)


class DynamicTariffInput(BaseModel):
    type: Literal["dynamic"] = "dynamic"
    name: str = Field(min_length=1, max_length=40)
    mwst_percent: float = Field(ge=0)
    aufschlag_ct_kwh: float = Field(ge=0)
    grundgebuehr_eur_monat: float = Field(ge=0)


TariffInput = Annotated[Union[FixTariffInput, DynamicTariffInput], Field(discriminator="type")]


class CalculateRequest(BaseModel):
    session_id: str
    tariffs: list[TariffInput] = Field(min_length=2, max_length=8)


class TariffTotal(BaseModel):
    name: str
    type: Literal["fix", "dynamic"]
    total_eur: float


class DailyCost(BaseModel):
    date: str
    costs: dict[str, float]


class DayHourDetail(BaseModel):
    hour: str
    consumption_kwh: float
    prices_ct_kwh: dict[str, float]
    costs_eur: dict[str, float]


class DayHighlight(BaseModel):
    date: str
    diff_eur: float
    reference_name: str
    compare_name: str
    cost_reference_eur: float
    cost_compare_eur: float
    hours: list[DayHourDetail]


class CalculateResponse(BaseModel):
    tariffs: list[TariffTotal]
    cheapest_name: str
    most_expensive_name: str
    savings_vs_most_expensive_eur: float
    savings_vs_most_expensive_percent: float
    period_days: float
    hours_total: int
    hours_missing_price: int
    daily: list[DailyCost]
    best_day: DayHighlight
    worst_day: DayHighlight
