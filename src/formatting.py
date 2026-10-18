"""How numbers and money are written for the reader.

Plain functions with no page framework, so the page and the command line
write them alike. They write the Turkish way: a dot between thousands and
a comma before the decimals. Only how a value is written changes; the value
itself is never touched.
"""

from decimal import Decimal

from src import messages


def with_separators(text: str) -> str:
    """Python's separators turned into the reader's: 1,234.5 -> 1.234,5."""
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def format_number(value: float, whole: bool) -> str:
    """A number: 7.269; 1.255.695,13; 0,0076.

    A whole number keeps no decimals. Otherwise two decimals, or four below
    1, where rates live and two would round them away.
    """
    if whole:
        return with_separators(f"{round(value):,}")
    return with_separators(f"{value:,.{2 if abs(value) >= 1 else 4}f}")


def format_amount(amount: str) -> str:
    """A money amount, always with two decimals: 1.250,00.

    Read as a Decimal, not a float, so no cent is lost on the way.
    """
    return with_separators(f"{Decimal(amount):,.2f}")


def format_money(amount: str) -> str:
    """A money amount with its currency: 1.250,00 BRL."""
    return messages.MONEY.format(amount=format_amount(amount))
