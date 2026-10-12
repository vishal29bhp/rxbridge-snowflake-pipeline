"""Small, pure helpers used by every stage. Pure functions = easy to unit-test."""

from __future__ import annotations

import re
from datetime import date

# Units we accept, mapped to one canonical spelling.
UNIT_ALIASES = {
    "mg": "mg",
    "milligram": "mg",
    "milligrams": "mg",
    "mcg": "microgram",
    "ug": "microgram",
    "µg": "microgram",
    "microgram": "microgram",
    "micrograms": "microgram",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "ml": "ml",
    "unit": "unit",
    "units": "unit",
    "tablet": "tablet",
    "tablets": "tablet",
}


def squash_ws(text: str | None) -> str:
    """Collapse all runs of whitespace to one space and trim. Used before quote checks."""
    return re.sub(r"\s+", " ", text or "").strip()


def nhs_digits(value: str | None) -> str | None:
    """'943 476 5919' -> '9434765919'. None if nothing numeric is present."""
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return digits or None


def nhs_checksum_ok(value: str | None) -> bool:
    """NHS number modulus 11 check.

    Multiply the first nine digits by weights 10..2, sum, take 11 - (sum mod 11).
    A result of 11 means the check digit is 0; 10 means the number is invalid.
    """
    digits = nhs_digits(value)
    if not digits or len(digits) != 10:
        return False
    total = sum(int(d) * w for d, w in zip(digits[:9], range(10, 1, -1)))
    check = 11 - (total % 11)
    if check == 11:
        check = 0
    if check == 10:
        return False
    return check == int(digits[9])


def make_nhs_number(first_nine: str) -> str:
    """Append a valid check digit to nine digits (for generating synthetic test data)."""
    for last in "0123456789":
        if nhs_checksum_ok(first_nine + last):
            return first_nine + last
    raise ValueError(f"{first_nine} has no valid check digit")


def parse_uk_date(value: str | None) -> date | None:
    """UK dates are day-first: '03/04/2019' is 3 April 2019, never 4 March."""
    if not value:
        return None
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", value)
    if not m:
        return None
    day, month, year = (int(x) for x in m.groups())
    if year < 100:
        year += 2000 if year < 50 else 1900
    try:
        return date(year, month, day)
    except ValueError:
        return None


def normalise_unit(unit: str | None) -> str | None:
    """'MCG' -> 'microgram'. Unknown units are returned lower-cased so a test can flag them."""
    if not unit:
        return None
    key = unit.strip().lower()
    return UNIT_ALIASES.get(key, key)
