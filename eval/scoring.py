"""Scores one evaluation run. Plain functions, no model involved.

- tool-call accuracy: how many of the expected tool calls the agent made,
  in the expected order and with the expected arguments;
- decision accuracy: whether the decision code the agent got from the rule
  engine is the expected one;
- execution match: whether the table the agent produced holds the result of
  the hand-written golden SQL;
- answer checks: text the answer must contain or must not contain.
"""

import math
import re
from itertools import permutations

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
