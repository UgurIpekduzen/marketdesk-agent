"""Keeping identifiers out of logs and free text."""

import hashlib
import re

# Order, customer, product and seller ids are 32 hexadecimal characters.
RAW_ID_PATTERN = re.compile(r"\b[0-9a-f]{32}\b", re.IGNORECASE)
MASK = "[id]"


def hash_id(raw_id: str) -> str:
    """Return the short hash that stands for an id in logs."""
    return hashlib.sha256(raw_id.encode()).hexdigest()[:10]


def mask_raw_ids(text: str) -> str:
    """Replace every raw id in a text with a fixed mark."""
    return RAW_ID_PATTERN.sub(MASK, text)
