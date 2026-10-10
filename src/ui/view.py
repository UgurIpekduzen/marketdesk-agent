"""Turns an answer of the system into what the page shows.

Plain functions and data, no page framework: the page only draws these.
"""

import logging
from dataclasses import dataclass, field

from src import messages
from src.orchestrator import Answer, Intent

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


def view_of(answer: Answer) -> AnswerView:
    router = answer.router_log
    if answer.refused:
        return AnswerView(
            text=answer.display,
            agent=messages.UI_AGENT_ROUTER,
            steps=router.steps,
            tokens=router.input_tokens + router.output_tokens,
        )
    reply = answer.reply
    log = reply.log
    gave_up = getattr(reply, "gave_up", False)
    return AnswerView(
        text=reply.text,
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
        caveats=list(getattr(reply, "caveats", [])),
        sources=cited_sources(reply.text, log.tool_results),
        pending=answer.awaiting_approval,
    )


def approval_card(pending: dict) -> dict[str, str]:
    """What the person is asked to approve: label -> value."""
    return {
        messages.UI_APPROVAL_ORDER: pending["order"],
        messages.UI_APPROVAL_REASON: messages.RETURN_REASON_LABELS[pending["reason"]],
        messages.UI_APPROVAL_AMOUNT: f"{pending['refund_amount']} BRL",
        messages.UI_APPROVAL_LEVEL: messages.REQUEST_STATUS_LABELS[
            pending["request_status"]
        ],
    }


def friendly_error(failure: BaseException) -> str:
    """The message shown for a failure. The details go to the log only."""
    logger.error("request failed", exc_info=failure)
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
