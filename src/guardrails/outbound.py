"""Cleaning text before it leaves for the model provider.

Whatever is sent to the provider may be kept and used by it, so the aim is
not to send personal data at all. The tools and the safe views already
leave it out; this module is the net underneath them. It looks for:

- raw ids (32 hexadecimal characters). In a customer session each one is
  replaced by the session's alias for it, so the model can still refer to
  the order and the tools can still resolve it; elsewhere it becomes [id];
- e-mail addresses and phone numbers, by their shape;
- Turkish id numbers, IBANs and card numbers, and the Brazilian CPF and
  CNPJ numbers of the reviews, by their shape and their check digits;
- addresses on the web (http, https or www);
- values known to be personal in this session: the customer's city and
  zip code prefix.

Before matching, the text is normalised (NFKC: full-width letters and
digits become plain ones) and zero-width characters are taken out, so they
cannot hide a value from the patterns. Known values are also matched
without accents ("são paulo" is "sao paulo"); the text sent on keeps its
letters, Turkish ones included.

Limits, stated plainly: text is matched by shape and against known values
only. A name, an address or another city typed into a message is not
recognised, and neither is a name written inside a review text. The
privacy fuzzing in the security review lists the forms still missed.
"""

import logging
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping

from src.guardrails.pii import (
    CARD_CANDIDATE,
    CARD_MASK,
    CNPJ_CANDIDATE,
    CNPJ_MASK,
    CPF_CANDIDATE,
    CPF_MASK,
    EMAIL_MASK,
    EMAIL_PATTERN,
    IBAN_CANDIDATE,
    IBAN_MASK,
    MASK,
    PHONE_CANDIDATE,
    PHONE_MASK,
    RAW_ID_PATTERN,
    TCKN_CANDIDATE,
    TCKN_MASK,
    URL_MASK,
    URL_PATTERN,
    is_card,
    is_cnpj,
    is_cpf,
    is_iban,
    is_tckn,
    looks_like_phone,
)

logger = logging.getLogger(__name__)

# Characters that take no space and can be put inside a value to hide it.
ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))


def normalised(text: str) -> str:
    """The text with compatibility forms made plain and zero-width marks out."""
    return unicodedata.normalize("NFKC", text).translate(ZERO_WIDTH)


def folded(text: str) -> tuple[str, list[int]]:
    """The text without accents and in lower case, for matching only.

    Returns the folded text and, for each of its characters, the position
    of the character it came from, so a match can be replaced in the text
    itself, which keeps its accents.
    """
    letters, origin = [], []
    for position, character in enumerate(text):
        for part in unicodedata.normalize("NFKD", character):
            if not unicodedata.combining(part):
                letters.append(part.lower())
                origin.append(position)
    return "".join(letters), origin


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
        # that is part of it. Matched in the folded text: any case, with or
        # without accents.
        self._known = [
            (re.compile(rf"(?<![\w]){re.escape(folded(value)[0])}(?![\w])"), mask)
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

        def checked(kind: str, mask: str, check: Callable[[str], bool]):
            """Replace a candidate only when its check digits hold."""

            def replace(match: re.Match) -> str:
                if not check(match.group()):
                    return match.group()
                found[kind] += 1
                return mask

            return replace

        def replace_url(match: re.Match) -> str:
            found["url"] += 1
            return URL_MASK

        def replace_phone(match: re.Match) -> str:
            if not looks_like_phone(match.group()):
                return match.group()
            found["phone"] += 1
            return PHONE_MASK

        text = normalised(text)
        text = URL_PATTERN.sub(replace_url, text)
        text = RAW_ID_PATTERN.sub(replace_id, text)
        text = EMAIL_PATTERN.sub(replace_email, text)
        # Before phone numbers, which would take a grouped number first.
        text = IBAN_CANDIDATE.sub(checked("iban", IBAN_MASK, is_iban), text)
        # Brazilian tax numbers, before the card number that a CNPJ could pass for.
        text = CNPJ_CANDIDATE.sub(checked("cnpj", CNPJ_MASK, is_cnpj), text)
        text = CPF_CANDIDATE.sub(checked("cpf", CPF_MASK, is_cpf), text)
        text = CARD_CANDIDATE.sub(checked("card", CARD_MASK, is_card), text)
        text = TCKN_CANDIDATE.sub(checked("tckn", TCKN_MASK, is_tckn), text)
        text = PHONE_CANDIDATE.sub(replace_phone, text)
        for pattern, mask in self._known:
            text, count = self._replace_known(text, pattern, mask)
            if count:
                found[mask.strip("[]")] += count
        return text, found

    @staticmethod
    def _replace_known(text: str, pattern: re.Pattern, mask: str) -> tuple[str, int]:
        """Replace a known value found in the folded text, in the text itself."""
        letters, origin = folded(text)
        spans = [
            (origin[match.start()], origin[match.end() - 1] + 1)
            for match in pattern.finditer(letters)
        ]
        for start, end in reversed(spans):
            text = text[:start] + mask + text[end:]
        return text, len(spans)

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


def findings_summary(found: Counter) -> str:
    """What was replaced, as kinds and counts: "email=1 phone=2"."""
    return " ".join(f"{kind}={count}" for kind, count in sorted(found.items()))


def log_findings(found: Counter) -> None:
    """Log what was replaced: kinds and counts, never the values."""
    if found:
        logger.warning(
            "outbound guard replaced personal data: %s", findings_summary(found)
        )
