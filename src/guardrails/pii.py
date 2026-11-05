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

# Also with spaces around the @ or with "[at]" or "(at)" in its place. The
# last part of the domain is letters, so "fiyat @ 100.50" is not one; "at"
# and "dot" written as words are left alone, as ordinary sentences have them.
EMAIL_PATTERN = re.compile(
    r"[\w.+-]+(?:\s*@\s*|\s*[\[(]at[\])]\s*)[\w-]+(?:\.[\w-]+)*\.[^\W\d_]{2,}",
    re.IGNORECASE,
)
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


# Brazilian numbers, in the free text of customer reviews. A CPF (a person's
# tax number) has 11 digits, written 529.982.247-25, and a CNPJ (a company's)
# 14, written 11.222.333/0001-81; both are taken only when their two check
# digits hold.
CPF_CANDIDATE = re.compile(
    rf"{NOT_IN_A_NUMBER_BEFORE}\d{{3}}\.?\d{{3}}\.?\d{{3}}-?\d{{2}}{NOT_IN_A_NUMBER_AFTER}"
)
CPF_MASK = "[cpf]"
CNPJ_CANDIDATE = re.compile(
    rf"{NOT_IN_A_NUMBER_BEFORE}\d{{2}}\.?\d{{3}}\.?\d{{3}}/?\d{{4}}-?\d{{2}}"
    rf"{NOT_IN_A_NUMBER_AFTER}"
)
CNPJ_MASK = "[cnpj]"
# An address on the web: a review can carry a shop's or a person's page.
# The punctuation that ends a sentence or a bracket is not part of it.
URL_PATTERN = re.compile(
    r"(?:https?://|www\.)[^\s<>\"']*[^\s<>\"'.,;:!?)\]}]", re.IGNORECASE
)
URL_MASK = "[url]"


def digits_of(text: str) -> str:
    """The digits of a candidate; none when it holds a date, which is never one.

    Args:
        text (str): A candidate for an id number.

    Returns:
        The digits, or an empty string when the text is a date.
    """
    if DATE_PATTERN.search(text):
        return ""
    return "".join(character for character in text if character.isdigit())


def is_tckn(candidate: str) -> bool:
    """The official check of a Turkish id number.

    Args:
        candidate (str): Text that may be a Turkish id number.

    Returns:
        True when it passes the check.
    """
    digits = [int(digit) for digit in digits_of(candidate)]
    if len(digits) != 11 or digits[0] == 0:
        return False
    tenth = (sum(digits[0:9:2]) * 7 - sum(digits[1:8:2])) % 10
    return digits[9] == tenth and digits[10] == sum(digits[:10]) % 10


def is_cpf(candidate: str) -> bool:
    """The check of a Brazilian CPF: two check digits, and not one digit repeated.

    Args:
        candidate (str): Text that may be a CPF.

    Returns:
        True when it passes the check.
    """
    digits = [int(digit) for digit in digits_of(candidate)]
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    first = sum(digit * weight for digit, weight in zip(digits, range(10, 1, -1))) * 10
    second = sum(digit * weight for digit, weight in zip(digits, range(11, 1, -1))) * 10
    return digits[9] == first % 11 % 10 and digits[10] == second % 11 % 10


def cnpj_check_digit(digits: list[int], count: int, weights: list[int]) -> int:
    """The check digit that follows the first count digits of a CNPJ.

    Args:
        digits (list[int]): The digits of the CNPJ.
        count (int): How many leading digits the check digit follows.
        weights (list[int]): The weight of each of those digits.

    Returns:
        The check digit.
    """
    remainder = sum(d * w for d, w in zip(digits[:count], weights)) % 11
    return 0 if remainder < 2 else 11 - remainder


def is_cnpj(candidate: str) -> bool:
    """The check of a Brazilian CNPJ: two check digits, and not one digit repeated.

    Args:
        candidate (str): Text that may be a CNPJ.

    Returns:
        True when it passes the check.
    """
    digits = [int(digit) for digit in digits_of(candidate)]
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    weights = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return digits[12] == cnpj_check_digit(digits, 12, weights) and digits[
        13
    ] == cnpj_check_digit(digits, 13, [6, *weights])


def is_iban(candidate: str) -> bool:
    """The ISO 13616 check: the number read as base 36 is 1 modulo 97.

    Args:
        candidate (str): Text that may be an IBAN.

    Returns:
        True when it passes the check.
    """
    text = candidate.replace(" ", "").upper()
    rearranged = text[4:] + text[:4]
    return int("".join(str(int(character, 36)) for character in rearranged)) % 97 == 1


def is_card(candidate: str) -> bool:
    """The Luhn check of a payment card number.

    Args:
        candidate (str): Text that may be a card number.

    Returns:
        True when it passes the Luhn check.
    """
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

    Args:
        raw_id (str): The raw id.

    Returns:
        The first 10 characters of its keyed hash.
    """
    digest = hmac.new(hash_key().encode(), raw_id.encode(), hashlib.sha256)
    return digest.hexdigest()[:10]


def mask_raw_ids(text: str) -> str:
    """Replace every raw id in a text with a fixed mark.

    Args:
        text (str): Any text.

    Returns:
        The text with every raw id masked.
    """
    return RAW_ID_PATTERN.sub(MASK, text)


def looks_like_phone(candidate: str) -> bool:
    """Tell a phone number from other digit runs such as dates and counts.

    A phone number has 10 to 15 digits and either starts the way phone
    numbers do (+, 0 or an area code in brackets) or is written in groups.
    A date is never one.

    Args:
        candidate (str): A run of digits and separators.

    Returns:
        True when it looks like a phone number.
    """
    if DATE_PATTERN.search(candidate):
        return False
    digits = sum(character.isdigit() for character in candidate)
    if not 10 <= digits <= 15:
        return False
    grouped = any(separator in candidate for separator in " -()")
    return candidate[0] in "+0(" or grouped
