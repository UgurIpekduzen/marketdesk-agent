"""Keeping identifiers out of logs and free text."""

import hashlib
import hmac
import logging
import os
import re
import secrets

logger = logging.getLogger(__name__)

# The environment variable that holds the secret key of the id hashes.
HASH_KEY_VARIABLE = "LOG_HASH_KEY"
# Used when the variable is not set: made once per process, never stored.
_generated_key: str | None = None

# Order, customer, product and seller ids are 32 hexadecimal characters.
RAW_ID_PATTERN = re.compile(r"\b[0-9a-f]{32}\b", re.IGNORECASE)
MASK = "[id]"

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
EMAIL_MASK = "[email]"

# A run of digits with the separators people put in phone numbers. Whether
# such a run is a phone number is decided in looks_like_phone.
PHONE_CANDIDATE = re.compile(
    r"(?<![\w+-])(?<!\d[.,])[+(]?\d[\d\s()-]{8,20}\d(?![\w-])(?![.,]\d)"
)
PHONE_MASK = "[phone]"
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")

# Numbers with a check digit: taken only when the check holds, so an order
# count or an amount of the same length is left alone.
# A Turkish id number (TCKN): 11 digits, maybe grouped.
# Not part of a decimal number: "0.0358..." holds a run of digits too.
NOT_IN_A_NUMBER_BEFORE = r"(?<![\w-])(?<![.,]\d)(?<!\d[.,])"
NOT_IN_A_NUMBER_AFTER = r"(?![\w-])(?![.,]\d)"
TCKN_CANDIDATE = re.compile(
    rf"{NOT_IN_A_NUMBER_BEFORE}\d(?:[ -]?\d){{10}}{NOT_IN_A_NUMBER_AFTER}"
)
TCKN_MASK = "[tckn]"
# An IBAN: country, check digits, then up to 30 letters and digits, maybe in
# groups of four.
IBAN_CANDIDATE = re.compile(
    r"(?<!\w)[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}(?!\w)", re.IGNORECASE
)
IBAN_MASK = "[iban]"
# A card number: 13 to 19 digits, maybe in groups.
CARD_CANDIDATE = re.compile(
    rf"{NOT_IN_A_NUMBER_BEFORE}\d(?:[ -]?\d){{12,18}}{NOT_IN_A_NUMBER_AFTER}"
)
CARD_MASK = "[card]"


def digits_of(text: str) -> str:
    """The digits of a candidate; none when it holds a date, which is never one."""
    if DATE_PATTERN.search(text):
        return ""
    return "".join(character for character in text if character.isdigit())


def is_tckn(candidate: str) -> bool:
    """The official check of a Turkish id number."""
    digits = [int(digit) for digit in digits_of(candidate)]
    if len(digits) != 11 or digits[0] == 0:
        return False
    tenth = (sum(digits[0:9:2]) * 7 - sum(digits[1:8:2])) % 10
    return digits[9] == tenth and digits[10] == sum(digits[:10]) % 10


def is_iban(candidate: str) -> bool:
    """The ISO 13616 check: the number read as base 36 is 1 modulo 97."""
    text = candidate.replace(" ", "").upper()
    rearranged = text[4:] + text[:4]
    return int("".join(str(int(character, 36)) for character in rearranged)) % 97 == 1


def is_card(candidate: str) -> bool:
    """The Luhn check of a payment card number."""
    digits = [int(digit) for digit in reversed(digits_of(candidate))]
    if not 13 <= len(digits) <= 19:
        return False
    doubled = [sum(divmod(2 * digit, 10)) for digit in digits[1::2]]
    return (sum(digits[0::2]) + sum(doubled)) % 10 == 0


def hash_key() -> str:
    """The secret key of the id hashes.

    It comes from the environment. Without one a random key is made for
    this process: the hashes then differ from run to run, but they still
    cannot be turned back into ids.
    """
    global _generated_key
    key = os.environ.get(HASH_KEY_VARIABLE)
    if key:
        return key
    if _generated_key is None:
        _generated_key = secrets.token_hex(32)
        logger.warning(
            "%s is not set: id hashes use a random key and will not match "
            "those of another run",
            HASH_KEY_VARIABLE,
        )
    return _generated_key


def hash_id(raw_id: str) -> str:
    """Return the short hash that stands for an id in logs and traces.

    A keyed hash (HMAC-SHA256), not a plain one: the ids of the data set
    are public, so a plain hash could be matched by hashing them all.
    """
    digest = hmac.new(hash_key().encode(), raw_id.encode(), hashlib.sha256)
    return digest.hexdigest()[:10]


def mask_raw_ids(text: str) -> str:
    """Replace every raw id in a text with a fixed mark."""
    return RAW_ID_PATTERN.sub(MASK, text)


def looks_like_phone(candidate: str) -> bool:
    """Tell a phone number from other digit runs such as dates and counts.

    A phone number has 10 to 15 digits and either starts the way phone
    numbers do (+, 0 or an area code in brackets) or is written in groups.
    A date is never one.
    """
    if DATE_PATTERN.search(candidate):
        return False
    digits = sum(character.isdigit() for character in candidate)
    if not 10 <= digits <= 15:
        return False
    grouped = any(separator in candidate for separator in " -()")
    return candidate[0] in "+0(" or grouped
