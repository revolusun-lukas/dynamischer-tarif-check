"""Gemeinsame Definition der Haushaltstypen fuer die (Platzhalter- und echte) Profilpipeline.

Wird von generate_household_profiles_placeholder.py UND generate_household_profiles_lpg.py
importiert, damit Metadaten (Anzeigename, Beschreibung, Vorschlagsverbrauch) in beiden
Pipelines identisch sind -- unabhaengig davon, mit welcher Methode die eigentlichen
15-Minuten-Werte erzeugt wurden.
"""
from __future__ import annotations

from dataclasses import dataclass

SEEDS = (1, 2, 3)


@dataclass(frozen=True)
class HouseholdType:
    id: str
    display_name: str
    description: str
    typical_annual_kwh: int
    # LPG-Vorlage (Household-Template-Code der LoadProfileGenerator-Datenbank), nur fuer
    # generate_household_profiles_lpg.py relevant -- siehe README fuer Details/Anpassung.
    lpg_template_hint: str


HOUSEHOLD_TYPES: list[HouseholdType] = [
    HouseholdType(
        id="single_working",
        display_name="1 Person, berufstätig",
        description="Single-Haushalt, tagsüber unter der Woche außer Haus (Büro).",
        typical_annual_kwh=1800,
        lpg_template_hint="CHR01 (Single, Vollzeit berufstätig)",
    ),
    HouseholdType(
        id="single_home",
        display_name="1 Person, zuhause / Rentner:in",
        description="Single-Haushalt, tagsüber überwiegend zuhause.",
        typical_annual_kwh=1500,
        lpg_template_hint="CHR05 (Single, Rentner:in)",
    ),
    HouseholdType(
        id="couple_both_working",
        display_name="2 Personen, beide berufstätig",
        description="Paarhaushalt, beide tagsüber unter der Woche außer Haus.",
        typical_annual_kwh=2700,
        lpg_template_hint="CHR10 (Paar, beide Vollzeit berufstätig)",
    ),
    HouseholdType(
        id="couple_home_office",
        display_name="2 Personen, Homeoffice",
        description="Paarhaushalt, beide überwiegend im Homeoffice.",
        typical_annual_kwh=3200,
        lpg_template_hint="CHR11 (Paar, Homeoffice) -- ggf. individuell in LPG nachbilden",
    ),
    HouseholdType(
        id="family_one_home",
        display_name="Familie mit Kindern, ein Elternteil zuhause",
        description="Familienhaushalt, ein Elternteil tagsüber zuhause, Kinder im Kindergarten/Schule.",
        typical_annual_kwh=4200,
        lpg_template_hint="CHR20 (Familie, ein Elternteil Teilzeit/zuhause)",
    ),
    HouseholdType(
        id="family_both_working",
        display_name="Familie mit Kindern, beide berufstätig",
        description="Familienhaushalt, beide Elternteile berufstätig, Kinder nachmittags zuhause.",
        typical_annual_kwh=4500,
        lpg_template_hint="CHR21 (Familie, beide Vollzeit berufstätig)",
    ),
    HouseholdType(
        id="senior_couple",
        display_name="Senioren-Paar",
        description="Paarhaushalt im Ruhestand, tagsüber überwiegend zuhause, früherer Tagesablauf.",
        typical_annual_kwh=2600,
        lpg_template_hint="CHR06 (Paar, beide Rentner:innen)",
    ),
]
