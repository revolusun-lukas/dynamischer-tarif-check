"""Pydantic-Modelle für die API-Requests/-Responses."""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

ValueType = Literal["power_w", "energy_wh", "energy_kwh", "counter_kwh"]
TimezoneMode = Literal["Europe/Berlin", "UTC"]


class ImportUploadResponse(BaseModel):
    session_id: str
    columns: list[str]
    preview_rows: list[dict]
    suggested_timestamp_column: Optional[str]
    suggested_value_column: Optional[str]
    suggested_value_type: Optional[ValueType]
    suggested_generation_column: Optional[str]
    suggested_timezone: TimezoneMode
    row_count: int
    warnings: list[str]


class ImportConfirmRequest(BaseModel):
    session_id: str
    timestamp_column: str
    value_column: str
    value_type: ValueType
    timezone: TimezoneMode = "Europe/Berlin"
    generation_column: Optional[str] = None
    generation_value_type: Optional[ValueType] = None


class ImportConfirmResponse(BaseModel):
    session_id: str
    start_date: str
    end_date: str
    total_kwh: float
    total_generation_kwh: Optional[float] = None
    hours_count: int
    warnings: list[str]


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
