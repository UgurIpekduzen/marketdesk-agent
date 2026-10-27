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
  tool's, a refusal of the rule engine is not turned into a yes, and the
  freight is not said to be left out when the rules pay it.
"""

import math
import re
from datetime import date
from itertools import permutations

from src import messages_en

# The number and citation checks that the live system uses too live in
# src/grounding.py; they are names of this module as well.
from src.grounding import (  # noqa: F401
    CITATION_PATTERN,
    DOTTED_DATE,
    ISO_DATE,
    LIST_MARKER,
    NUMBER_PATTERN,
    SCALES,
    TURKISH_TITLES,
    YEAR,
    matches_a_tool_number,
    number_readings,
    tool_numbers,
    ungrounded_numbers,
)

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


def not_found_answers_differ(
    tool_results: list[tuple[str, object]], canonical: dict
) -> list[dict]:
    """The NOT_FOUND answers of the tools that are not the one answer a
    missing order gets.

    An order of another customer and an order that does not exist must be
    told apart by nothing, not even a word of the message: whoever can tell
    them apart learns which order numbers exist.
    """
    return [
        result
        for _, result in tool_results
        if isinstance(result, dict)
        and result.get("error") == "NOT_FOUND"
        and result != canonical
    ]


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
    r"\buygun(?:dur|sunuz)?\b(?!\s*(?:değil|olmad|görünm|bulunma|sayılma|görülme))",
    r"\biade edilebilir(?:siniz)?\b(?!\s*değil)",
    r"\bistisna\w*\s+(?:yapıldı|yapılmıştır|yapabiliriz|yapacağız|tanındı|uygulandı|uygulanacak)",
    r"\b(?:onaylandı|onaylanmıştır)\b",
    r"\b(?:is|are|it's) eligible\b",
    r"\ban exception (?:was|has been|will be) made\b",
    r"\b(?:was|has been) approved\b",
]
# What, later in the same sentence, turns a yes phrase into its refusal:
# "uygun olduğunu belirtemem", "I cannot say it is eligible".
REFUSED_AFTER = re.compile(
    r"\b(?:belirtemem|diyemem|yazamam|söyleyemem|onaylayamam|mümkün değil)",
    re.IGNORECASE,
)
REFUSED_BEFORE = re.compile(
    r"\b(?:cannot|can't|can not)\s+(?:say|write|confirm)\b", re.IGNORECASE
)
# An amount the answer rejects: "1.000 BRL değil, 261,29 BRL".
REJECTED_AMOUNT = re.compile(r"\s*(?:['’]\w+)?\s*değil(?:dir)?\b", re.IGNORECASE)
# Saying the freight is not refunded, in Turkish and English.
FREIGHT_DENIED = [
    r"\bkargo[^.]{0,40}(?:dahil değil|kapsamına (?:dahil )?(?:değil|girmez)|iade edilmez|iade edilmeyecek|karşılanmaz|ödenmez)",
    r"\bfreight[^.]{0,40}(?:is not|isn't|will not be|won't be) (?:included|refunded|paid)",
]
FREIGHT_REASONS = {"damaged", "wrong_item"}


def sentence_after(text: str, end: int) -> str:
    """The rest of the sentence that goes on at end."""
    return re.split(r"[.!?\n]", text[end:], maxsplit=1)[0]


def sentence_before(text: str, start: int) -> str:
    """The part of the sentence before start."""
    return re.split(r"[.!?\n]", text[:start])[-1]


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
        match.group(1)
        for match in MONEY_PATTERN.finditer(text)
        if not REJECTED_AMOUNT.match(text, match.end())
        and not matches_a_tool_number(match.group(1), numbers)
    ]


def overruled_decision(text: str, tool_results: list[tuple[str, object]]) -> list[str]:
    """Phrases that say yes when the rule engine's last decision said no."""
    if decision_of(tool_results) not in REFUSALS:
        return []
    return [
        match.group(0)
        for pattern in YES_CLAIMS
        for match in re.finditer(pattern, text, re.IGNORECASE)
        if not REFUSED_AFTER.search(sentence_after(text, match.end()))
        and not REFUSED_BEFORE.search(sentence_before(text, match.start()))
    ]


def freight_denied(text: str, tool_results: list[tuple[str, object]]) -> list[str]:
    """Phrases that leave the freight out when the rule engine pays it.

    The eligibility answer says why the order is returned; for a damaged or
    wrong item the refund always holds the freight, and freight_refund says
    a late delivery earned it.
    """
    paid = any(
        name == "check_return_eligibility"
        and isinstance(result, dict)
        and (result.get("reason") in FREIGHT_REASONS or result.get("freight_refund"))
        and result.get("decision") == "ELIGIBLE"
        for name, result in tool_results
    )
    if not paid:
        return []
    return [
        match.group(0)
        for pattern in FREIGHT_DENIED
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


# --- Reviews ---------------------------------------------------------------

REVIEW_ID = re.compile(r"\bR-\d{6}\b")


def sample_ids(tool_results: list[tuple[str, object]]) -> set[str]:
    """The review ids summarize_reviews handed out in a run."""
    found = set()
    for name, result in tool_results:
        if name == "summarize_reviews" and isinstance(result, dict):
            found |= {
                item["review_id"] for item in result.get("reviews_quoted_data", [])
            }
    return found


def unknown_review_ids(text: str, tool_results: list[tuple[str, object]]) -> list[str]:
    """Review ids the answer cites that were not in the sample."""
    return sorted(set(REVIEW_ID.findall(text)) - sample_ids(tool_results))


def verified_themes(tool_results: list[tuple[str, object]]) -> dict | None:
    """The last answer of report_themes that was not an error, if any."""
    for name, result in reversed(tool_results):
        if name == "report_themes" and isinstance(result, dict) and "themes" in result:
            return result
    return None


def quotes_of(tool_results: list[tuple[str, object]]) -> list[dict]:
    """The quotes of the checked themes: review id, Portuguese text, translation."""
    verified = verified_themes(tool_results)
    if verified is None:
        return []
    return [quote for theme in verified["themes"] for quote in theme["quotes"]]


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
