"""Cleaning text before it leaves for the model provider.

Whatever is sent to the provider may be kept and used by it, so the aim is
not to send personal data at all. The tools and the safe views already
leave it out; this module is the net underneath them. It looks for:

- raw ids (32 hexadecimal characters). In a customer session each one is
  replaced by the session's alias for it, so the model can still refer to
  the order and the tools can still resolve it; elsewhere it becomes [id];
- e-mail addresses and phone numbers, by their shape;
- values known to be personal in this session: the customer's city and
  zip code prefix.

Limits, stated plainly: text is matched by shape and against known values
only. A name, an address or another city typed into a message is not
recognised, and neither is personal detail inside review texts.
"""

import logging
import re
from collections import Counter
from collections.abc import Callable, Mapping

from src.guardrails.pii import (
    EMAIL_MASK,
    EMAIL_PATTERN,
    MASK,
    PHONE_CANDIDATE,
    PHONE_MASK,
    RAW_ID_PATTERN,
    looks_like_phone,
)

logger = logging.getLogger(__name__)


class Redactor:
    """Replaces personal data in a text and counts what it replaced."""

    def __init__(
        self,
        alias_for: Callable[[str], str] | None = None,
        known_values: Mapping[str, str] | None = None,
    ) -> None:
        """alias_for turns a raw id into its alias; without it ids are masked.

        known_values maps a personal value of this session to the mask that
        replaces it, for example {"sao paulo": "[city]"}.
        """
        self._alias_for = alias_for
        # Longest first, so "sao paulo" is replaced before a shorter value
        # that is part of it. Letters match in any case, digits exactly.
        self._known = [
            (
                re.compile(rf"(?<![\w]){re.escape(value)}(?![\w])", re.IGNORECASE),
                mask,
            )
            for value, mask in sorted(
                (known_values or {}).items(), key=lambda item: -len(item[0])
            )
            if value
        ]

    def redact(self, text: str) -> tuple[str, Counter]:
        """Return the cleaned text and how many values of each kind it held."""
        found: Counter = Counter()

        def replace_id(match: re.Match) -> str:
            found["id"] += 1
            if self._alias_for is None:
                return MASK
            return self._alias_for(match.group().lower())

        def replace_email(match: re.Match) -> str:
            found["email"] += 1
            return EMAIL_MASK

        def replace_phone(match: re.Match) -> str:
            if not looks_like_phone(match.group()):
                return match.group()
            found["phone"] += 1
            return PHONE_MASK

        text = RAW_ID_PATTERN.sub(replace_id, text)
        text = EMAIL_PATTERN.sub(replace_email, text)
        text = PHONE_CANDIDATE.sub(replace_phone, text)
        for pattern, mask in self._known:
            text, count = pattern.subn(mask, text)
            if count:
                found[mask.strip("[]")] += count
        return text, found

    def redact_value(self, value: object, found: Counter) -> object:
        """Clean every string inside nested dicts and lists."""
        if isinstance(value, str):
            cleaned, counts = self.redact(value)
            found.update(counts)
            return cleaned
        if isinstance(value, dict):
            return {key: self.redact_value(item, found) for key, item in value.items()}
        if isinstance(value, list):
            return [self.redact_value(item, found) for item in value]
        return value


def log_findings(found: Counter) -> None:
    """Log what was replaced: kinds and counts, never the values."""
    if found:
        summary = " ".join(f"{kind}={count}" for kind, count in sorted(found.items()))
        logger.warning("outbound guard replaced personal data: %s", summary)
