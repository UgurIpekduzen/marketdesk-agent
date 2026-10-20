"""Personal data written so a pattern might miss it, for the privacy fuzz
tests. Every value is made up; none comes from the Olist data.

A case is a text that holds one personal value, and the "core" of that
value: what must not be readable in the text after a guard. A guard
"catches" a case when the core cannot be found in what it leaves, even
after normalising the text and keeping only its letters and digits.
"""

import base64
import unicodedata
from dataclasses import dataclass

ZERO_WIDTH = chr(0x200B)  # a zero-width space
FULLWIDTH_DIGITS = str.maketrans("0123456789", "０１２３４５６７８９")
CYRILLIC_LOOKALIKES = str.maketrans("aeoc", "аеос")

RAW_ID = "3f2a9c1be47d4c0f8a6b5e2d1c9f7a30"
EMAIL_USER, EMAIL_DOMAIN = "ayse.yilmaz", "ornekposta"
PHONE = "05321234567"
TCKN = "10000000146"
IBAN = "TR330006100519786457841326"
CARD = "4111111111111111"
CITY = "sao paulo"
ZIP = "01310"
# The known personal values of the session, as the order server gives them.
KNOWN_VALUES = {CITY: "[city]", ZIP: "[zip]"}


@dataclass(frozen=True)
class Case:
    kind: str
    variant: str
    text: str
    core: str


def skeleton(text: str) -> str:
    """The text as letters and digits only, normalised and in lower case."""
    text = unicodedata.normalize("NFKC", text).replace(ZERO_WIDTH, "")
    return "".join(character for character in text.lower() if character.isalnum())


def leaks(left: str, case: Case) -> bool:
    return skeleton(case.core) in skeleton(left)


def spaced(value: str, size: int, separator: str = " ") -> str:
    return separator.join(value[i : i + size] for i in range(0, len(value), size))


def zero_width(value: str) -> str:
    return ZERO_WIDTH.join(value)


def wrap(value: str) -> str:
    return f"Merhaba, bilgim şu: {value} teşekkürler."


def cases() -> list[Case]:
    email = f"{EMAIL_USER}@{EMAIL_DOMAIN}.com"
    raw = [
        ("id", "plain", RAW_ID),
        ("id", "upper case", RAW_ID.upper()),
        ("id", "split by spaces", spaced(RAW_ID, 8)),
        ("id", "split by hyphens", spaced(RAW_ID, 8, "-")),
        ("id", "zero-width inside", zero_width(RAW_ID)),
        ("id", "full-width digits", RAW_ID.translate(FULLWIDTH_DIGITS)),
        ("id", "base64", base64.b64encode(RAW_ID.encode()).decode()),
        ("email", "plain", email),
        ("email", "at and dot words", f"{EMAIL_USER} at {EMAIL_DOMAIN} dot com"),
        ("email", "bracketed at", f"{EMAIL_USER}[at]{EMAIL_DOMAIN}.com"),
        ("email", "full-width at", email.replace("@", "＠")),
        ("email", "spaces around @", email.replace("@", " @ ")),
        ("email", "zero-width inside", zero_width(email)),
        ("email", "cyrillic look-alikes", email.translate(CYRILLIC_LOOKALIKES)),
        ("phone", "plain", PHONE),
        ("phone", "grouped", "0532 123 45 67"),
        ("phone", "dotted", "0532.123.45.67"),
        ("phone", "international", "+90 532 123 45 67"),
        ("phone", "full-width digits", PHONE.translate(FULLWIDTH_DIGITS)),
        ("phone", "zero-width inside", zero_width(PHONE)),
        ("phone", "one digit at a time", " ".join(PHONE)),
        (
            "phone",
            "spelled out",
            "sıfır beş yüz otuz iki yüz yirmi üç kırk beş altmış yedi",
        ),
        ("tckn", "plain", TCKN),
        ("tckn", "grouped", spaced(TCKN, 3)),
        ("iban", "plain", IBAN),
        ("iban", "grouped", spaced(IBAN, 4)),
        ("card", "plain", CARD),
        ("card", "grouped", spaced(CARD, 4)),
        ("city", "plain", CITY),
        ("city", "upper case", CITY.upper()),
        ("city", "with accents", "são paulo"),
        ("city", "zero-width inside", zero_width(CITY)),
        ("city", "cyrillic look-alikes", CITY.translate(CYRILLIC_LOOKALIKES)),
        ("zip", "plain", ZIP),
        ("zip", "with a hyphen", "013-10"),
    ]
    # The core of a spelled-out phone number cannot be found in its letters,
    # so it is checked by the number words the guard would have to remove.
    core = {"spelled out": "beş yüz otuz iki"}
    return [
        Case(kind, variant, wrap(value), core.get(variant, value))
        for kind, variant, value in raw
    ]
