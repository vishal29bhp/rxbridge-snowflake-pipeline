from datetime import date

import pytest

from rxpipe.normalise import (make_nhs_number, nhs_checksum_ok, nhs_digits, normalise_unit,
                              parse_uk_date, squash_ws)


def test_valid_nhs_number_passes():
    assert nhs_checksum_ok("943 476 5919")          # the NHS's published test number


@pytest.mark.parametrize("bad", ["943 476 5918", "9434765", "", None, "abcdefghij", "4505577014"])
def test_invalid_nhs_numbers_fail(bad):
    assert not nhs_checksum_ok(bad)


def test_swapping_two_digits_breaks_the_check_digit():
    good = make_nhs_number("450557710")
    swapped = good[:7] + good[8] + good[7] + good[9:]
    assert nhs_checksum_ok(good) and not nhs_checksum_ok(swapped)


def test_nhs_digits_strips_spaces():
    assert nhs_digits("943 476 5919") == "9434765919"


def test_uk_dates_are_day_first():
    assert parse_uk_date("03/04/2019") == date(2019, 4, 3)     # 3 April, never 4 March
    assert parse_uk_date("Date: 15/08/22") == date(2022, 8, 15)
    assert parse_uk_date("31/02/2024") is None                 # impossible date -> None, not a guess


@pytest.mark.parametrize("raw,unit", [("MCG", "microgram"), ("mg", "mg"), ("Tablets", "tablet"), ("ml", "ml")])
def test_units_normalised(raw, unit):
    assert normalise_unit(raw) == unit


def test_unknown_unit_kept_so_dbt_can_flag_it():
    assert normalise_unit("drops") == "drops"


def test_squash_ws():
    assert squash_ws("  Dose:   500\n mg ") == "Dose: 500 mg"
