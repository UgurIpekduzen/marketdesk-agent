"""Turns an answer of the system into what the page shows.

Plain functions and data, no page framework: the page only draws these.
"""

import logging
import re
from dataclasses import dataclass, field

import config
from src import failures, messages
from src.formatting import format_money, how_computed
from src.i18n import DEFAULT_LANGUAGE, Language, catalog
from src.orchestrator import Answer, Intent
from src.tools.review_queue import RequestRow, TicketRow
from src.ui.chat_session import ApprovalWaitingError, MessageTooLongError
from src.ui.question_limit import QuestionLimitReachedError
from src.ui.session_pool import SessionLimitReachedError

logger = logging.getLogger(__name__)

# The catalog names of who answered, for the steps panel.
AGENT_LABELS = {
    Intent.SUPPORT: "UI_AGENT_SUPPORT",
    Intent.OPS_METRIC: "UI_AGENT_OPS",
    Intent.REVIEW_INSIGHT: "UI_AGENT_REVIEWS",
}
# Chat avatars: icons of the page framework, so no image files.
USER_AVATAR = ":material/person:"
SUPPORT_AVATAR = ":material/support_agent:"
OPS_AVATAR = ":material/analytics:"
REVIEWS_AVATAR = ":material/rate_review:"
# A person, the support rep: not the support agent's avatar.
REP_AVATAR = ":material/headset_mic:"
# The router answers a message no agent of the session may take.
ROUTER_AVATAR = ":material/smart_toy:"
AGENT_AVATARS = {
    Intent.SUPPORT: SUPPORT_AVATAR,
    Intent.OPS_METRIC: OPS_AVATAR,
    Intent.REVIEW_INSIGHT: REVIEWS_AVATAR,
}
# The message shown for each kind of provider failure, by catalog name.
FAILURE_MESSAGES = {
    failures.QUOTA_EXCEEDED: "UI_ERROR_QUOTA",
    failures.PROVIDER_BUSY: "UI_ERROR_BUSY",
    failures.KEY_REFUSED: "UI_ERROR_KEY_REFUSED",
    failures.KEY_NOT_SET: "UI_ERROR_NOT_CONFIGURED",
    failures.DAILY_BUDGET: "UI_ERROR_DAILY_BUDGET",
    failures.RUN_FAILED: "UI_ERROR_GENERIC",
}
# A markdown image, inline or by reference: the browser would fetch its
# address as soon as the answer is drawn, so a model talked into writing
# one could send data to any site without a click.
IMAGE_PATTERN = re.compile(r"!\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])")
# Every markdown image starts with these two characters, whatever follows
# (nested brackets, a shortcut reference defined elsewhere). Escaped, they
# are drawn as plain text and nothing is fetched.
IMAGE_START = "!["
ESCAPED_IMAGE_START = "!\\["
# Characters markdown reads as formatting, escaped where a text partly comes
# from the model's arguments (a filter value) and must be drawn as written.
MARKDOWN_CHARACTERS = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$])")
# Links in an answer. The system never needs one (the policies hold no
# addresses), and a link a model was talked into writing ("pay here") is a
# way to send a customer anywhere. Each form loses its target:
# [text](address) keeps its text;
INLINE_LINK = re.compile(r"(?<![!\\])\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)")
# a reference definition ("[r]: address") is taken out, so "[text][r]" is text;
LINK_DEFINITION = re.compile(r"^ {0,3}\[[^\]]+\]:[ \t]*\S.*$", re.MULTILINE)
# "<scheme:...>" is drawn as written;
AUTOLINK = re.compile(r"<(?=[a-z][a-z0-9+.\-]*:)", re.IGNORECASE)
# a bare address is drawn as code, which markdown never turns into a link.
BARE_ADDRESS = re.compile(
    r"(?:\b[a-z][a-z0-9+.\-]*://|\bwww\.)[^\s<>`]+", re.IGNORECASE
)


def escape_markdown(text: str) -> str:
    """The text with every markdown character escaped: drawn as written.

    Escaping does not stop a written address from being made a link (the
    link is found in the text once the escapes are read), so an address is
    drawn as code instead.

    Args:
        text (str): Any text.

    Returns:
        The text drawn as written.
    """
    parts, last = [], 0
    for match in BARE_ADDRESS.finditer(text):
        parts.append(MARKDOWN_CHARACTERS.sub(r"\\\1", text[last : match.start()]))
        parts.append(f"`{match.group()}`")
        last = match.end()
    parts.append(MARKDOWN_CHARACTERS.sub(r"\\\1", text[last:]))
    return "".join(parts)


def without_images(text: str, language: Language = DEFAULT_LANGUAGE) -> str:
    """The text with no markdown image left to draw.

    The usual forms become a plain note; any other start of an image is
    escaped, so that a form the pattern misses cannot load either.

    Args:
        text (str): Any text.
        language (Language): The session's language.

    Returns:
        The text with no markdown image left.
    """
    cleaned, replaced = IMAGE_PATTERN.subn(catalog(language).UI_IMAGE_REMOVED, text)
    escaped = cleaned.count(IMAGE_START)
    cleaned = cleaned.replace(IMAGE_START, ESCAPED_IMAGE_START)
    if replaced or escaped:
        logger.warning(
            "removed %d markdown images and escaped %d more in an answer",
            replaced,
            escaped,
        )
    return cleaned


def without_links(text: str) -> str:
    """The text with no markdown link left to click; the words stay.

    Args:
        text (str): Any text.

    Returns:
        The text with no link left to click; the words stay.
    """
    text, inline = INLINE_LINK.subn(r"\1", text)
    text, defined = LINK_DEFINITION.subn("", text)
    text, auto = AUTOLINK.subn("\\\\<", text)
    text, bare = BARE_ADDRESS.subn(lambda match: f"`{match.group()}`", text)
    if inline or defined or auto or bare:
        logger.warning(
            "made %d links, %d link definitions, %d autolinks and %d addresses "
            "plain in a text",
            inline,
            defined,
            auto,
            bare,
        )
    return text


def safe_markdown(text: str, language: Language = DEFAULT_LANGUAGE) -> str:
    """A text from the model or the visitor, as it may be drawn as markdown:
    no image to load, no link to click.

    Args:
        text (str): A text from the model or the visitor.
        language (Language): The session's language.

    Returns:
        The text as it may be drawn as markdown.
    """
    return without_links(without_images(text, language))


@dataclass(frozen=True)
class AnswerView:
    """An answer prepared for display: text, who answered and the step details."""

    text: str
    agent: str  # who answered, for the steps panel
    avatar: str = SUPPORT_AVATAR
    tools: list[str] = field(default_factory=list)
    steps: int = 0
    tokens: int = 0
    # Ops answers: the rows behind the numbers, the SQL and the caveats.
    table: dict | None = None
    queries: list[str] = field(default_factory=list)
    queries_heading: str = messages.OPS_USED_SQL_HEADING
    caveats: list[str] = field(default_factory=list)
    # Ops answers: each metric call in words, escaped to be drawn as markdown.
    computed: list[str] = field(default_factory=list)
    # Policy answers: the sections the answer cites.
    sources: list[str] = field(default_factory=list)
    # A return request waiting for the person's approval.
    pending: dict | None = None


def last_table(tool_results: list) -> dict | None:
    """The columns and rows of the last query that returned some.

    Args:
        tool_results (list): The (tool name, result) pairs of the answer.

    Returns:
        The columns and rows of the last result that has them, or None.
    """
    for _, result in reversed(tool_results):
        if isinstance(result, dict) and "columns" in result and "rows" in result:
            return {"columns": result["columns"], "rows": result["rows"]}
    return None


def cited_sources(text: str, tool_results: list) -> list[str]:
    """Citations of the policy sections found that the answer names.

    Args:
        text (str): The answer.
        tool_results (list): The (tool name, result) pairs of the answer.

    Returns:
        The citations of the policy sections the answer names.
    """
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

    Args:
        text (str): The answer.
        caveats (list[str]): The caveats of the metrics used.

    Returns:
        The caveats the answer does not already hold in full.
    """
    said = " ".join(text.split())
    return [caveat for caveat in caveats if " ".join(caveat.split()) not in said]


def view_of(answer: Answer, language: Language = DEFAULT_LANGUAGE) -> AnswerView:
    """Turn an Answer into the AnswerView the page shows.

    Args:
        answer (Answer): The router's answer.
        language (Language): The session's language.

    Returns:
        The answer prepared for display.
    """
    texts = catalog(language)
    router = answer.router_log
    if answer.refused:
        return AnswerView(
            text=safe_markdown(answer.display, language),
            agent=texts.UI_AGENT_ROUTER,
            avatar=ROUTER_AVATAR,
            steps=router.steps,
            tokens=router.input_tokens + router.output_tokens,
        )
    reply = answer.reply
    log = reply.log
    gave_up = getattr(reply, "gave_up", False)
    return AnswerView(
        text=safe_markdown(reply.text, language),
        agent=getattr(texts, AGENT_LABELS[answer.intent]),
        avatar=AGENT_AVATARS[answer.intent],
        tools=list(log.tool_calls),
        steps=router.steps + log.steps,
        tokens=router.input_tokens
        + router.output_tokens
        + log.input_tokens
        + log.output_tokens,
        # The table the agent made for its answer (the themes of the reviews,
        # the seller report), else the rows of the last tool result.
        table=None
        if gave_up
        else (getattr(reply, "table", None) or last_table(log.tool_results)),
        queries=list(getattr(reply, "queries", [])),
        queries_heading=(
            texts.OPS_TRIED_SQL_HEADING if gave_up else texts.OPS_USED_SQL_HEADING
        ),
        computed=[]
        if gave_up
        else [
            escape_markdown(how_computed(computation, language))
            for computation in getattr(reply, "computations", [])
        ],
        caveats=unsaid_caveats(reply.text, list(getattr(reply, "caveats", []))),
        sources=cited_sources(reply.text, log.tool_results),
        pending=answer.awaiting_approval,
    )


def tools_text(tools: list[str], language: Language = DEFAULT_LANGUAGE) -> str:
    """The tools of an answer for the steps panel, each as inline code.

    Inline code is not read as markdown, so a tool name can never become an
    image or a link; a backtick, which would end the code, is dropped.

    Args:
        tools (list[str]): The tools the answer called.
        language (Language): The session's language.

    Returns:
        The tool names as inline code.
    """
    if not tools:
        return catalog(language).UI_STEPS_NO_TOOLS
    return " → ".join(f"`{name.replace('`', '')}`" for name in tools)


def approval_card(
    pending: dict, language: Language = DEFAULT_LANGUAGE
) -> dict[str, str]:
    """What the person is asked to approve: label -> value.

    Args:
        pending (dict): The request waiting for approval.
        language (Language): The session's language.

    Returns:
        The label and value of each line of the card.
    """
    texts = catalog(language)
    return {
        texts.UI_APPROVAL_ORDER: pending["order"],
        texts.UI_APPROVAL_REASON: texts.RETURN_REASON_LABELS[pending["reason"]],
        texts.UI_APPROVAL_AMOUNT: format_money(pending["refund_amount"], language),
        texts.UI_APPROVAL_LEVEL: texts.REQUEST_STATUS_LABELS[pending["request_status"]],
    }


def friendly_error(
    failure: BaseException, language: Language = DEFAULT_LANGUAGE
) -> str:
    """The message shown for a failure. The details go to the log only.

    Args:
        failure (BaseException): What went wrong; logged, not shown.
        language (Language): The session's language.

    Returns:
        The message to show.
    """
    logger.error("request failed", exc_info=failure)
    texts = catalog(language)
    if isinstance(failure, SessionLimitReachedError):
        return texts.UI_ERROR_FULL
    if isinstance(failure, MessageTooLongError):
        return texts.UI_ERROR_TOO_LONG.format(limit=config.MAX_MESSAGE_CHARS)
    if isinstance(failure, QuestionLimitReachedError):
        return texts.UI_ERROR_QUESTION_LIMIT
    if isinstance(failure, ApprovalWaitingError):
        return texts.UI_ERROR_APPROVAL_WAITING
    if isinstance(failure, TimeoutError):
        return texts.UI_ERROR_TIMEOUT
    return getattr(texts, FAILURE_MESSAGES[failures.failure_code(failure)])


def request_card(
    row: RequestRow, language: Language = DEFAULT_LANGUAGE
) -> tuple[str, str]:
    """A return request in the rep's queue: its title line and its details.

    Every value comes from the database and the rules, none from the model;
    ids are shown as hashes.

    Args:
        row (RequestRow): A return request.
        language (Language): The session's language.

    Returns:
        The title line and the details.
    """
    texts = catalog(language)
    title = texts.UI_REVIEW_REQUEST_TITLE.format(
        id=row.request_id, order=row.order_key, customer=row.customer_key
    )
    details = texts.UI_REVIEW_REQUEST_DETAILS.format(
        reason=texts.RETURN_REASON_LABELS.get(row.reason, row.reason),
        amount=format_money(row.amount, language),
        date=row.created_at[:10],
        status=texts.REQUEST_STATUS_LABELS.get(row.status, row.status),
    )
    return title, details


def ticket_title(row: TicketRow, language: Language = DEFAULT_LANGUAGE) -> str:
    """A ticket's title line; its summary is drawn apart, as plain text.

    Args:
        row (TicketRow): An escalation ticket.
        language (Language): The session's language.

    Returns:
        The title line.
    """
    texts = catalog(language)
    return texts.UI_REVIEW_TICKET_TITLE.format(
        number=row.number,
        priority=texts.PRIORITY_LABELS.get(row.priority, row.priority),
        date=row.created_at[:10],
        customer=row.customer_key,
    )
