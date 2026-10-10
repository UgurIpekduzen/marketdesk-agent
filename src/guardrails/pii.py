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
