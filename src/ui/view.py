"""Turns an answer of the system into what the page shows.

Plain functions and data, no page framework: the page only draws these.
"""

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal

import config
from src import messages
from src.orchestrator import Answer, Intent
from src.ui.chat_session import MessageTooLong
from src.ui.question_limit import QuestionLimitReached
from src.ui.session_pool import SessionLimitReached

logger = logging.getLogger(__name__)

AGENT_LABELS = {
    Intent.SUPPORT: messages.UI_AGENT_SUPPORT,
    Intent.OPS_METRIC: messages.UI_AGENT_OPS,
}
# Marks in an error text, lower case, and the message shown for them.
ERROR_MARKS = (
    (("429", "resource_exhausted", "quota", "rate limit"), messages.UI_ERROR_QUOTA),
    (
        ("503", "unavailable", "overloaded", "high demand", "connecterror"),
        messages.UI_ERROR_BUSY,
    ),
    (("api_key", "api key"), messages.UI_ERROR_NOT_CONFIGURED),
)
# A markdown image, inline or by reference: the browser would fetch its
# address as soon as the answer is drawn, so a model talked into writing
# one could send data to any site without a click.
IMAGE_PATTERN = re.compile(r"!\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])")
# Every markdown image starts with these two characters, whatever follows
# (nested brackets, a shortcut reference defined elsewhere). Escaped, they
# are drawn as plain text and nothing is fetched.
IMAGE_START = "!["
ESCAPED_IMAGE_START = "!\\["


def without_images(text: str) -> str:
    """The text with no markdown image left to draw.

    The usual forms become a plain note; any other start of an image is
    escaped, so that a form the pattern misses cannot load either.
    """
    cleaned, replaced = IMAGE_PATTERN.subn(messages.UI_IMAGE_REMOVED, text)
    escaped = cleaned.count(IMAGE_START)
    cleaned = cleaned.replace(IMAGE_START, ESCAPED_IMAGE_START)
    if replaced or escaped:
        logger.warning(
            "removed %d markdown images and escaped %d more in an answer",
            replaced,
            escaped,
        )
    return cleaned


@dataclass(frozen=True)
class AnswerView:
    text: str
    agent: str  # who answered, for the steps panel
    tools: list[str] = field(default_factory=list)
    steps: int = 0
    tokens: int = 0
    # Ops answers: the rows behind the numbers, the SQL and the caveats.
    table: dict | None = None
    queries: list[str] = field(default_factory=list)
    queries_heading: str = messages.OPS_USED_SQL_HEADING
    caveats: list[str] = field(default_factory=list)
    # Policy answers: the sections the answer cites.
    sources: list[str] = field(default_factory=list)
    # A return request waiting for the person's approval.
    pending: dict | None = None


def last_table(tool_results: list) -> dict | None:
    """The columns and rows of the last query that returned some."""
    for _, result in reversed(tool_results):
        if isinstance(result, dict) and "columns" in result and "rows" in result:
            return {"columns": result["columns"], "rows": result["rows"]}
    return None


def tr_number(value: float, whole: bool) -> str:
    """A number written the Turkish way: 7.269; 1.255.695,13; 0,0076.

    A whole number keeps no decimals. Otherwise two decimals, or four below
    1, where rates live and two would round them away.
    """
    if whole:
        text = f"{round(value):,}"
    else:
        text = f"{value:,.{2 if abs(value) >= 1 else 4}f}"
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def tr_amount(amount: str) -> str:
    """A money amount written the Turkish way, always with two decimals.

    The amount is read as a Decimal, not a float, so no cent is lost on the
    way; it is only written differently, the value itself is untouched.
    """
    text = f"{Decimal(amount):,.2f}"
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def readable_table(table: dict) -> dict:
    """A result table as the page shows it.

    The columns the semantic layer names get Turkish headers; a plain total
    has a numerator that only repeats the value, and that column is left
    out. For each numeric column it says whether it holds whole numbers,
    decided here on the raw values: the page's table library turns a whole
    column with a gap into decimals.
    """
    columns = list(table["columns"])
    rows = [list(row) for row in table["rows"]]
    if "numerator" in columns and "value" in columns:
        numerator, value = columns.index("numerator"), columns.index("value")
        if all(row[numerator] == row[value] for row in rows):
            del columns[numerator]
            for row in rows:
                del row[numerator]
    headers = [messages.UI_TABLE_COLUMNS.get(column, column) for column in columns]
    numbers = {}
    for position, header in enumerate(headers):
        values = [row[position] for row in rows if row[position] is not None]
        if values and all(
            isinstance(item, int | float) and not isinstance(item, bool)
            for item in values
        ):
            numbers[header] = all(isinstance(item, int) for item in values)
    return {"columns": headers, "rows": rows, "numbers": numbers}


def cited_sources(text: str, tool_results: list) -> list[str]:
    """Citations of the policy sections found that the answer names."""
    cited = []
    for name, result in tool_results:
        if name != "search_policies" or not isinstance(result, dict):
            continue
        for section in result.get("results", []):
            citation = section.get("citation")
            if citation and citation in text and citation not in cited:
                cited.append(citation)
    return cited


def unsaid_caveats(text: str, caveats: list[str]) -> list[str]:
    """The caveats the answer text does not already hold in full.

    The model is asked to repeat a metric's caveat, and usually does word
    for word; showing it again in a box under the answer only repeats it. A
    caveat the model left out, cut short or reworded is still shown: the
    caveat comes from the code and must reach the reader. Spaces and line
    breaks do not count.
    """
    said = " ".join(text.split())
    return [caveat for caveat in caveats if " ".join(caveat.split()) not in said]


def view_of(answer: Answer) -> AnswerView:
    router = answer.router_log
    if answer.refused:
        return AnswerView(
            text=without_images(answer.display),
            agent=messages.UI_AGENT_ROUTER,
            steps=router.steps,
            tokens=router.input_tokens + router.output_tokens,
        )
    reply = answer.reply
    log = reply.log
    gave_up = getattr(reply, "gave_up", False)
    return AnswerView(
        text=without_images(reply.text),
        agent=AGENT_LABELS[answer.intent],
        tools=list(log.tool_calls),
        steps=router.steps + log.steps,
        tokens=router.input_tokens
        + router.output_tokens
        + log.input_tokens
        + log.output_tokens,
        table=None if gave_up else last_table(log.tool_results),
        queries=list(getattr(reply, "queries", [])),
        queries_heading=(
            messages.OPS_TRIED_SQL_HEADING if gave_up else messages.OPS_USED_SQL_HEADING
        ),
        caveats=unsaid_caveats(reply.text, list(getattr(reply, "caveats", []))),
        sources=cited_sources(reply.text, log.tool_results),
        pending=answer.awaiting_approval,
    )


def tools_text(tools: list[str]) -> str:
    """The tools of an answer for the steps panel, each as inline code.

    Inline code is not read as markdown, so a tool name can never become an
    image or a link; a backtick, which would end the code, is dropped.
    """
    if not tools:
        return messages.UI_STEPS_NO_TOOLS
    return " → ".join(f"`{name.replace('`', '')}`" for name in tools)


def approval_card(pending: dict) -> dict[str, str]:
    """What the person is asked to approve: label -> value."""
    return {
        messages.UI_APPROVAL_ORDER: pending["order"],
        messages.UI_APPROVAL_REASON: messages.RETURN_REASON_LABELS[pending["reason"]],
        messages.UI_APPROVAL_AMOUNT: f"{tr_amount(pending['refund_amount'])} BRL",
        messages.UI_APPROVAL_LEVEL: messages.REQUEST_STATUS_LABELS[
            pending["request_status"]
        ],
    }


def friendly_error(failure: BaseException) -> str:
    """The message shown for a failure. The details go to the log only."""
    logger.error("request failed", exc_info=failure)
    if isinstance(failure, SessionLimitReached):
        return messages.UI_ERROR_FULL
    if isinstance(failure, MessageTooLong):
        return messages.UI_ERROR_TOO_LONG.format(limit=config.MAX_MESSAGE_CHARS)
    if isinstance(failure, QuestionLimitReached):
        return messages.UI_ERROR_QUESTION_LIMIT
    if isinstance(failure, TimeoutError):
        return messages.UI_ERROR_TIMEOUT
    # The whole chain: the provider's error is often wrapped by the framework.
    texts = []
    current: BaseException | None = failure
    while current is not None and len(texts) < 10:
        texts.append(f"{type(current).__name__} {current}".lower())
        current = current.__cause__ or current.__context__
    text = " ".join(texts)
    for marks, message in ERROR_MARKS:
        if any(mark in text for mark in marks):
            return message
    return messages.UI_ERROR_GENERIC
