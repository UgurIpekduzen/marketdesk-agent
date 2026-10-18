"""Tests for how numbers and money are written for the reader."""

import pytest

from src.formatting import format_amount, format_money, format_number, with_separators


def test_separators_are_swapped_the_turkish_way():
    assert with_separators("1,234,567.89") == "1.234.567,89"


@pytest.mark.parametrize(
    ("value", "whole", "text"),
    [
        (7269, True, "7.269"),
        (494, True, "494"),
        (1255695.13, False, "1.255.695,13"),
        (4.04, False, "4,04"),
        (0.007619, False, "0,0076"),
        (-1234.5, False, "-1.234,50"),
        # A whole column the table library turned into decimals.
        (7269.0, True, "7.269"),
    ],
)
def test_numbers_are_written_the_turkish_way(value, whole, text):
    assert format_number(value, whole) == text


@pytest.mark.parametrize(
    ("amount", "text"),
    [
        ("133.14", "133,14"),
        ("1250.00", "1.250,00"),
        ("1250", "1.250,00"),
        ("0.5", "0,50"),
        ("1234567.89", "1.234.567,89"),
    ],
)
def test_money_is_written_the_turkish_way_with_two_decimals(amount, text):
    assert format_amount(amount) == text


def test_money_carries_its_currency():
    assert format_money("115.00") == "115,00 BRL"
