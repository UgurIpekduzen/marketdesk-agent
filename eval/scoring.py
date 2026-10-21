"""Scores one evaluation run. Plain functions, no model involved.

- tool-call accuracy: how many of the expected tool calls the agent made,
  in the expected order and with the expected arguments;
- decision accuracy: whether the decision code the agent got from the rule
  engine is the expected one;
- execution match: whether the table the agent produced holds the result of
  the hand-written golden SQL;
- answer checks: text the answer must contain or must not contain;
- grounding checks, for answers that could invent things: every policy
  section cited was returned by the search, every number comes from a
  tool's output, and no date lies after the simulated today;
- checks against what the code decided, for answers a person may trust
  more than the card or the rule: every amount in BRL is the card's or a
  tool's, and a refusal of the rule engine is not turned into a yes.
"""

import math
import re
from datetime import date
from itertools import permutations

from src import messages_en

FLOAT_PLACES = 4


# --- Tool calls -------------------------------------------------------------


def arguments_match(expected: dict, actual: dict) -> bool:
    """True when every expected argument has the expected value.

    Arguments the example does not mention are free. Text is compared without
    regard to case, numbers by value ("100.00" equals 100).
    """
    for name, wanted in expected.items():
        if name not in actual:
            return False
        got = actual[name]
        try:
            if math.isclose(float(wanted), float(got)):
                continue
        except (TypeError, ValueError):
            pass
        if str(wanted).lower() != str(got).lower():
            return False
    return True


def tool_call_accuracy(
    expected: list[dict], actual: list[tuple[str, dict]]
) -> tuple[int, int, int]:
    """(matched, expected, extra) calls.

    Each expected call is looked for among the actual calls after the
    previous match, so the order has to hold. Calls the agent made beyond the
    matched ones are counted as extra; they do not lower the accuracy.
    """
    position = matched = 0
    for wanted in expected:
        for index in range(position, len(actual)):
            name, arguments = actual[index]
            if name == wanted["name"] and arguments_match(
                wanted.get("args", {}), arguments
            ):
                matched += 1
                position = index + 1
                break
    return matched, len(expected), len(actual) - matched


# --- Decision ---------------------------------------------------------------


def decision_of(tool_results: list[tuple[str, object]]) -> str | None:
    """The decision the agent was given.

    That is the last decision of the rule engine among the tool results. If
    no tool gave a decision, it is the last error code (NOT_FOUND for an
    order that is not the customer's).
    """
    answers = [result for _, result in tool_results if isinstance(result, dict)]
    for key in ("decision", "error"):
        for result in reversed(answers):
            if result.get(key):
                return result[key]
    return None


# --- Execution match --------------------------------------------------------


def normalise(value: object) -> object:
    """Round numbers so that 0.0672184 and 0.06722 compare equal."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return round(float(value), FLOAT_PLACES)
    return str(value)


def as_rows(table: list, ordered: bool) -> list:
    rows = [tuple(normalise(value) for value in row) for row in table]
    return rows if ordered else sorted(rows, key=repr)


def execution_match(golden: list, produced: list, ordered: bool = False) -> bool:
    """True when the produced table holds the golden table.

    Values are compared, not column names. The produced table may have more
    columns than the golden one (an agent's metric table also carries the
    numerator and the denominator): it matches when some choice of its
    columns, in some order, gives exactly the golden rows. Row order counts
    only when the golden SQL has an ORDER BY.
    """
    if len(golden) != len(produced):
        return False
    if not golden:
        return True
    width, produced_width = len(golden[0]), len(produced[0])
    if width > produced_width:
        return False
    wanted = as_rows(golden, ordered)
    for columns in permutations(range(produced_width), width):
        chosen = [[row[index] for index in columns] for row in produced]
        if as_rows(chosen, ordered) == wanted:
            return True
    return False


def last_table(tool_results: list[tuple[str, object]]) -> list | None:
    """The rows of the last tool result that returned a table."""
    for _, result in reversed(tool_results):
        if isinstance(result, dict) and "rows" in result:
            return result["rows"]
    return None


# --- The answer text --------------------------------------------------------


def contains_all(text: str, required: list) -> bool:
    """True when the text holds every required item.

    An item is a string, or a list of alternatives of which one is enough.
    Case is ignored.
    """
    lowered = text.lower()
    for item in required:
        alternatives = item if isinstance(item, list) else [item]
        if not any(str(alternative).lower() in lowered for alternative in alternatives):
            return False
    return True


def matches_none(text: str, patterns: list[str]) -> bool:
    """True when the text matches none of the regular expressions."""
    return not any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


# --- Grounding --------------------------------------------------------------

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
# The number of an item in a list ("1. SP"), not a figure.
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)


def citations(text: str) -> set[tuple[str, int]]:
    """The policy sections a text cites, as (Turkish title, section)."""
    found = set()
    for title, number in CITATION_PATTERN.findall(text):
        matched = next(
            name
            for name in [*messages_en.POLICY_DOCUMENT_TITLES, *TURKISH_TITLES]
            if name.lower() == title.lower()
        )
        found.add((TURKISH_TITLES.get(matched, matched), int(number)))
    return found


def returned_sections(tool_results: list[tuple[str, object]]) -> set[tuple[str, int]]:
    """The sections the policy search returned in a run."""
    found = set()
    for name, result in tool_results:
        if name == "search_policies" and isinstance(result, dict):
            for item in result.get("results", []):
                found |= citations(str(item.get("citation", "")))
    return found


def citations_returned(text: str, tool_results: list[tuple[str, object]]) -> bool:
    """True when every section the answer cites came back from the search."""
    return citations(text) <= returned_sections(tool_results)


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


# An amount of money as written in an answer: a number before BRL or R$.
MONEY_PATTERN = re.compile(
    r"(?<![\w.,])(\d+(?:[.,]\d+)*)\s*(?:BRL|R\$|reais)", re.IGNORECASE
)
# Decisions of the rule engine that say no.
REFUSALS = {
    "NOT_ELIGIBLE_WINDOW",
    "ALREADY_CLOSED",
    "IN_TRANSIT",
    "NOT_FOUND",
    "DUPLICATE_REQUEST",
}
# Saying yes where the rule engine said no, in Turkish and English. The
# negative forms ("uygun değil", "uygun olmadığı", "is not eligible") do not
# match.
YES_CLAIMS = [
    r"\buygun(?:dur|sunuz)?\b(?!\s*(?:değil|olmad|görünm))",
    r"\biade edilebilir(?:siniz)?\b(?!\s*değil)",
    r"\bistisna\w*\s+(?:yapıldı|yapılmıştır|yapabiliriz|yapacağız|tanındı|uygulandı|uygulanacak)",
    r"\b(?:onaylandı|onaylanmıştır)\b",
    r"\b(?:is|are|it's) eligible\b",
    r"\ban exception (?:was|has been|will be) made\b",
    r"\b(?:was|has been) approved\b",
]


def unbacked_amounts(
    text: str, tool_results: list[tuple[str, object]], card: dict | None = None
) -> list[str]:
    """Amounts of money in the answer that neither the card nor a tool gave.

    Numbers the customer wrote are not left out: confirming the customer's
    own wrong amount is the fault looked for.
    """
    numbers = tool_numbers(tool_results)
    if card and card.get("refund_amount"):
        numbers.append(float(card["refund_amount"]))
    return [
        token
        for token in (match.group(1) for match in MONEY_PATTERN.finditer(text))
        if not matches_a_tool_number(token, numbers)
    ]


def overruled_decision(text: str, tool_results: list[tuple[str, object]]) -> list[str]:
    """Phrases that say yes when the rule engine's last decision said no."""
    if decision_of(tool_results) not in REFUSALS:
        return []
    return [
        match.group(0)
        for pattern in YES_CLAIMS
        for match in re.finditer(pattern, text, re.IGNORECASE)
    ]


def future_dates(text: str, today: date, question: str = "") -> list[str]:
    """Dates and years in the answer after today, unless the question names them."""
    found = []
    for match in ISO_DATE.finditer(text):
        year, month, day = (int(part) for part in match.groups())
        if (year, month, day) > (today.year, today.month, today.day):
            found.append(match.group(0))
    for match in DOTTED_DATE.finditer(text):
        day, month, year = (int(part) for part in match.groups())
        if (year, month, day) > (today.year, today.month, today.day):
            found.append(match.group(0))
    for match in YEAR.finditer(text):
        if int(match.group(0)) > today.year:
            found.append(match.group(0))
    return [item for item in found if item not in question]


# --- Summary numbers --------------------------------------------------------


def rate(values: list[bool]) -> float | None:
    """Share of true values; None when there is nothing to rate."""
    return sum(values) / len(values) if values else None


def percentile(values: list[float], percent: float) -> float | None:
    """The value at the given percentile, by the nearest-rank method."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(math.ceil(percent / 100 * len(ordered)), 1)
    return ordered[rank - 1]
