"""Checks that an answer's numbers come from what the tools returned.

Plain functions, no model. The evaluation scores answers with them, and the
critic of the operations agent runs the same check on an answer before it
is shown, so the two cannot drift apart.

A number as written in an answer is Turkish (1.234,5) or English (1,234.5);
it passes when some reading of it is a number in a tool's output, rounded
as written, or a share written as a percentage.
"""

import re

from src import messages_en

# Policy documents by their Turkish title, and their English titles.
TURKISH_TITLES = {
    english: turkish for turkish, english in messages_en.POLICY_DOCUMENT_TITLES.items()
}
CITATION_PATTERN = re.compile(
    "("
    + "|".join(
        re.escape(title)
        for title in sorted(
            [*messages_en.POLICY_DOCUMENT_TITLES, *TURKISH_TITLES],
            key=len,
            reverse=True,
        )
    )
    + r"),?\s*(?:Bölüm|Section)\s*(\d+)",
    re.IGNORECASE,
)
# A number as written in an answer: Turkish (1.234,5) or English (1,234.5)
# grouping, a sign, and a word for thousands or millions after it.
NUMBER_PATTERN = re.compile(
    r"(?<![\w.,])-?\d+(?:[.,]\d+)*(?:\s*(bin|milyon|milyar|thousand|million|billion)\b)?",
    re.IGNORECASE,
)
SCALES = {
    "bin": 1e3,
    "thousand": 1e3,
    "milyon": 1e6,
    "million": 1e6,
    "milyar": 1e9,
    "billion": 1e9,
}
# Dates written as 2018-09-01 or 01.09.2018, and years on their own.
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DOTTED_DATE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b")
YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
# A seller's pseudonym in an operations answer (S-1286): its digits are a
# name, not a figure.
PSEUDONYM = re.compile(r"\bS-\d{4}\b")
# The number of an item in a list ("1. SP"), not a figure.
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)


def number_readings(token: str) -> set[tuple[float, int, float]]:
    """The values a number as written may stand for: (value, decimals, scale).

    "1.234" is 1234 in Turkish and 1.234 in English; both are kept, and an
    answer passes if either is in the tool output. A word for thousands or
    millions after the number scales it.
    """
    match = NUMBER_PATTERN.fullmatch(token.strip())
    if not match:
        return set()
    scale = SCALES.get((match.group(1) or "").lower(), 1)
    digits = token.strip().split()[0]
    readings = set()
    for thousands, decimal in ((".", ","), (",", ".")):
        parts = digits.split(decimal)
        if len(parts) > 2:
            continue
        whole, fraction = parts[0], parts[1] if len(parts) == 2 else ""
        groups = whole.lstrip("-").split(thousands)
        if len(groups) > 1 and not all(len(group) == 3 for group in groups[1:]):
            continue
        # The other mark may not appear after the decimal one: "904.322,02"
        # is Turkish, never 904 point "322,02".
        if not fraction.isdigit() and fraction:
            continue
        value = float(
            whole.replace(thousands, "") + ("." + fraction if fraction else "")
        )
        readings.add((value * scale, len(fraction), scale))
    return readings


def tool_numbers(tool_results: list[tuple[str, object]]) -> list[float]:
    """Every number in the tool results, at any depth, also in strings."""
    found: list[float] = []

    def walk(value: object) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, int | float):
            found.append(float(value))
        elif isinstance(value, str):
            found.extend(float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", value))
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list | tuple):
            for item in value:
                walk(item)

    for _, result in tool_results:
        walk(result)
    return found


def matches_a_tool_number(token: str, numbers: list[float]) -> bool:
    """True when the written number is a tool number, rounded as written.

    A share may be written as a percentage (0.123 as 12,3).
    """
    for value, places, scale in number_readings(token):
        tolerance = 0.5 * 10**-places * scale
        for number in numbers:
            if any(
                abs(candidate - value) <= tolerance + 1e-9
                for candidate in (number, number * 100)
            ):
                return True
    return False


def ungrounded_numbers(
    text: str, tool_results: list[tuple[str, object]], question: str = ""
) -> list[str]:
    """Numbers in the answer that no tool returned.

    Left out: dates, citations, and numbers the question itself holds.
    """
    cleaned = LIST_MARKER.sub(" ", text)
    cleaned = ISO_DATE.sub(" ", cleaned)
    cleaned = DOTTED_DATE.sub(" ", cleaned)
    cleaned = PSEUDONYM.sub(" ", cleaned)
    cleaned = CITATION_PATTERN.sub(" ", cleaned)
    asked = {match.group(0).strip() for match in NUMBER_PATTERN.finditer(question)}
    numbers = tool_numbers(tool_results)
    return [
        token
        for token in (
            match.group(0).strip() for match in NUMBER_PATTERN.finditer(cleaned)
        )
        if token not in asked
        and not YEAR.fullmatch(token)
        and not matches_a_tool_number(token, numbers)
    ]
