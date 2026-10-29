"""The MarketDesk chat page.

Run with:  streamlit run app.py

The page only draws and passes clicks on. Who the session belongs to, what
it may ask, the rules, the approval of a return request and every text, in
Turkish and English, live in src/; nothing is decided here.
"""

import functools
import logging
import os
import random
from functools import partial
from pathlib import Path

import pandas as pd
import streamlit as st

import config
from src import tracing, tracing_dashboard
from src.formatting import (
    format_number,
    readable_sql,
    readable_table,
    seller_report_sources,
    seller_report_table,
    worth_a_table,
)
from src.i18n import Language, catalog, from_locale
from src.knowledge.seller_report import build_seller_report
from src.knowledge.sql_runner import connect_read_only
from src.rules.returns import RequestStatus
from src.tools.review_queue import REP_IDENTITY, ReviewQueue
from src.ui import examples, resources
from src.ui.call_budget import CallBudget
from src.ui.chat_session import ChatSession
from src.ui.question_limit import QuestionLimit
from src.ui.session_pool import SessionPool
from src.ui.view import (
    OPS_AVATAR,
    REP_AVATAR,
    SUPPORT_AVATAR,
    USER_AVATAR,
    AnswerView,
    approval_card,
    friendly_error,
    request_card,
    safe_markdown,
    ticket_title,
    tools_text,
    view_of,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO = ASSETS / "logo.svg"  # the mark and the name, at the top of the sidebar
ICON = ASSETS / "icon.svg"  # the mark alone: the browser tab, a closed sidebar
# A button label stays on one line and is cut with "..."; an example
# question is read whole, so its buttons wrap. Reached through the class
# the framework gives an element with a key, so no other button changes.
EXAMPLE_BUTTON_STYLE = """<style>
[class*="st-key-example_"] button * {
    white-space: normal;
    overflow: visible;
    text-overflow: clip;
}
</style>"""
# The languages as the switch shows them, each in its own words.
LANGUAGE_CHOICES = {Language.TR: "Türkçe", Language.EN: "English"}


@st.cache_resource
def start_tracing() -> bool:
    """Once per server process; does nothing while the target is "off"."""
    tracing.setup_tracing()
    return True


@st.cache_resource
def session_pool() -> SessionPool:
    """One per server process: closes idle sessions, caps open ones."""
    pool = SessionPool(config.SESSION_IDLE_MINUTES * 60, config.MAX_OPEN_SESSIONS)
    pool.start_checking()
    return pool


@st.cache_resource
def question_limit() -> QuestionLimit:
    """One per server process, shared by every visitor."""
    return QuestionLimit(config.MAX_QUESTIONS_PER_HOUR)


@st.cache_resource
def call_budget() -> CallBudget:
    """One per server process: the model calls of every visitor in a day."""
    return CallBudget(config.MAX_MODEL_CALLS_PER_DAY)


@st.cache_resource
def policy_index():
    return resources.load_policy_index()


def page_language() -> Language:
    """The page's language: the browser's at first, then the visitor's choice.

    Held by the session like the session type; no message can change it.
    """
    if "language" not in st.session_state:
        st.session_state.language = from_locale(st.context.locale)
    try:
        return Language(st.session_state.language)
    except ValueError:
        st.session_state.language = from_locale(None)
        return Language(st.session_state.language)


def page_texts():
    """The strings of the page's language."""
    return catalog(page_language())


def language_changed() -> None:
    """A new language starts a new conversation, like a new customer.

    The conversation so far, and a request waiting for approval in it, go:
    the agents are told the language when a conversation starts.
    """
    if "turns" in st.session_state:
        close_session()
        st.session_state.pop("turns")
        st.session_state.language_notice = True


def draw_language_switch() -> None:
    texts = page_texts()
    st.radio(
        texts.UI_LANGUAGE_SWITCH,
        list(LANGUAGE_CHOICES),
        key="language",
        format_func=LANGUAGE_CHOICES.get,
        horizontal=True,
        help=texts.UI_LANGUAGE_HELP,
        on_change=language_changed,
    )


@st.cache_resource(show_spinner=False)
def database(path: Path) -> Path:
    """The database, built once per server process if it is missing."""
    if not path.exists():
        with st.spinner(page_texts().UI_PREPARING_DATABASE):
            resources.build_database(path)
    return path


@st.cache_data
def demo_customers(path: str):
    return resources.load_demo_customers(path)


@st.cache_data(show_spinner=False)
def seller_report(path: str, language: Language) -> dict:
    """The seller report: the data does not change while the page runs."""
    conn = connect_read_only(path)
    try:
        return build_seller_report(conn, language=language)
    finally:
        conn.close()


@st.cache_data(ttl=60, show_spinner=False)
def error_counts() -> tuple:
    """(observations read, the error rows, a failure or None), kept 60 seconds.

    A failure is kept too, so a Langfuse that is down is asked once a minute,
    not at every click of every visitor.
    """
    try:
        public, secret = tracing_dashboard.credentials()
        observations = tracing_dashboard.fetch_observations(public, secret)
    except tracing_dashboard.DashboardUnavailable as failure:
        return 0, [], failure
    return len(observations), tracing_dashboard.count_errors(observations), None


def draw_error_tracing(texts) -> None:
    """How often each error kind is marked in the traces (numbers only).

    Read only when asked: Streamlit draws every tab at every page run, and the
    read takes seconds (more if Langfuse is slow), which the queue must not
    wait for.
    """
    st.caption(texts.DASH_CAPTION)
    if st.button(texts.UI_TRACING_LOAD, key="tracing_load"):
        st.session_state.tracing_result = error_counts()
    result = st.session_state.get("tracing_result")
    if result is None:
        return
    observed, rows, failure = result
    if failure is not None:
        st.warning(tracing_dashboard.failure_text(texts, failure))
        return
    columns = st.columns(3)
    columns[0].metric(texts.DASH_OBSERVATIONS, observed)
    columns[1].metric(texts.DASH_ERRORS, sum(row.count for row in rows))
    columns[2].metric(texts.DASH_KINDS, len({row.kind for row in rows}))
    if not rows:
        st.info(texts.DASH_NO_ERRORS)
        return
    frame = pd.DataFrame(
        {
            texts.DASH_COLUMN_KIND: [row.kind for row in rows],
            texts.DASH_COLUMN_WHERE: [texts.DASH_WHERE[row.where] for row in rows],
            texts.DASH_COLUMN_COUNT: [row.count for row in rows],
        }
    )
    st.subheader(texts.DASH_BY_KIND)
    st.bar_chart(
        frame.pivot_table(
            index=texts.DASH_COLUMN_KIND,
            columns=texts.DASH_COLUMN_WHERE,
            values=texts.DASH_COLUMN_COUNT,
            aggfunc="sum",
            fill_value=0,
        )
    )
    st.dataframe(frame, hide_index=True, use_container_width=True)


def close_session() -> None:
    session = st.session_state.pop("session", None)
    if session is not None:
        session.close()


def open_session(identity: tuple, customer_unique_id: str | None) -> None:
    """Start a new conversation for the chosen identity."""
    close_session()
    st.session_state.identity = identity
    st.session_state.turns = []
    st.session_state.pending = None
    # Picked once, so they stay the same until the next conversation.
    st.session_state.examples = examples.pick_examples(
        identity, random.Random(), page_language()
    )
    index = policy_index() if customer_unique_id else None
    try:
        st.session_state.session = session_pool().open(
            lambda: ChatSession(
                resources.db_path(),
                index,
                customer_unique_id,
                question_limit=question_limit(),
                language=page_language(),
                call_budget=call_budget(),
            )
        )
    except Exception as failure:  # noqa: BLE001
        st.session_state.turns.append(
            ("error", friendly_error(failure, page_language()))
        )


def sign_out() -> None:
    """Back to the choice screen: the conversation and its identity go."""
    close_session()
    for name in (
        "identity",
        "turns",
        "pending",
        "examples",
        "review_notice",
        "language_notice",
        "tracing_result",
    ):
        st.session_state.pop(name, None)


def draw_choice(customers: list) -> tuple | None:
    """The choice screen: as a customer in a situation, or as the ops team.

    Returns the chosen identity, or None until a start button is clicked.
    The customer comes from the server-side list; only its situation is
    kept, and the id is looked up again on every page run.
    """
    texts = page_texts()
    st.subheader(texts.UI_CHOICE_HEADING)
    st.caption(texts.UI_CHOICE_NOTE)
    customer_card, ops_card, rep_card = st.columns(3)
    chosen = None
    with customer_card.container(border=True):
        st.markdown(f"{USER_AVATAR} **{texts.UI_CHOICE_CUSTOMER}**")
        st.write(texts.UI_CHOICE_CUSTOMER_TEXT)
        if customers:
            # A radio, not a drop-down: the labels are read whole.
            customer = st.radio(
                texts.UI_CUSTOMER_PICKER,
                customers,
                format_func=lambda choice: texts.DEMO_CUSTOMER_LABELS[choice.situation],
            )
            clicked = st.button(
                texts.UI_START_CUSTOMER, type="primary", use_container_width=True
            )
            # A value written by hand comes back as the text sent, not as one
            # of the customers: it is no choice.
            if clicked and customer in customers:
                chosen = ("customer", customer.situation)
        else:
            st.error(texts.UI_NO_CUSTOMERS)
    with ops_card.container(border=True):
        st.markdown(f"{OPS_AVATAR} **{texts.UI_CHOICE_OPS}**")
        st.write(texts.UI_CHOICE_OPS_TEXT)
        if st.button(texts.UI_START_OPS, use_container_width=True):
            chosen = ("ops",)
    with rep_card.container(border=True):
        st.markdown(f"{REP_AVATAR} **{texts.UI_CHOICE_REP}**")
        st.write(texts.UI_CHOICE_REP_TEXT)
        if st.button(texts.UI_START_REP, use_container_width=True):
            chosen = REP_IDENTITY
    return chosen


def draw_examples() -> str | None:
    """The example questions of an empty conversation; the one clicked."""
    texts = page_texts()
    st.html(EXAMPLE_BUTTON_STYLE)
    st.caption(texts.UI_EXAMPLES_HEADING)
    left, right = st.columns(2)
    clicked = None
    for number, question in enumerate(st.session_state.examples):
        column = left if number % 2 == 0 else right
        if column.button(question, key=f"example_{number}", use_container_width=True):
            clicked = question
    return clicked


def draw_review(queue: ReviewQueue) -> None:
    """The support rep's console: the person decides, the code writes.

    No model is called here. Each button sends one decision on one row; the
    queue makes it only if the row is still in the state it was shown in.
    """
    language = page_language()
    texts = catalog(language)
    notice = st.session_state.pop("review_notice", None)
    if notice is not None:
        kind, text = notice
        (st.success if kind == "done" else st.warning)(text)
    st.subheader(texts.UI_REVIEW_HEADING)
    st.caption(texts.UI_REVIEW_NOTE)
    waiting, tickets = queue.waiting_requests(), queue.open_tickets()
    requests_tab, tickets_tab, tracing_tab = st.tabs(
        [
            texts.UI_REVIEW_REQUESTS_TAB.format(count=len(waiting)),
            texts.UI_REVIEW_TICKETS_TAB.format(count=len(tickets)),
            texts.UI_REVIEW_TRACING_TAB,
        ]
    )
    clicked = None
    with requests_tab:
        if not waiting:
            st.info(texts.UI_REVIEW_NO_REQUESTS)
        for row in waiting:
            title, details = request_card(row, language)
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.write(details)
                if row.status != RequestStatus.PENDING_REVIEW:
                    st.caption(texts.UI_REVIEW_SENIOR_NOTE)
                    continue
                approve, reject = st.columns(2)
                if approve.button(
                    texts.UI_REVIEW_APPROVE,
                    key=f"approve_{row.request_id}",
                    type="primary",
                    use_container_width=True,
                ):
                    clicked = ("decide", row.request_id, RequestStatus.APPROVED)
                if reject.button(
                    texts.UI_REVIEW_REJECT,
                    key=f"reject_{row.request_id}",
                    use_container_width=True,
                ):
                    clicked = ("decide", row.request_id, RequestStatus.REJECTED)
        decided = queue.decided_requests()
        if decided:
            with st.expander(texts.UI_REVIEW_DECIDED.format(count=len(decided))):
                for row in decided:
                    title, details = request_card(row, language)
                    st.markdown(f"**{title}**  \n{details}")
    with tickets_tab:
        if not tickets:
            st.info(texts.UI_REVIEW_NO_TICKETS)
        for ticket in tickets:
            with st.container(border=True):
                st.markdown(f"**{ticket_title(ticket, language)}**")
                # Written by the model: plain text, never read as markdown.
                st.text(ticket.summary)
                if st.button(texts.UI_REVIEW_CLOSE, key=f"close_{ticket.ticket_id}"):
                    clicked = ("close", ticket.ticket_id, None)
    with tracing_tab:
        draw_error_tracing(texts)
    if clicked is None:
        return
    action, number, decision = clicked
    if action == "decide":
        result = queue.decide(number, decision)
        done = texts.UI_REVIEW_DECIDED_DONE.format(
            id=number, status=texts.REQUEST_STATUS_LABELS[decision]
        )
    else:
        result = queue.close_ticket(number)
        done = texts.UI_REVIEW_TICKET_CLOSED.format(number=result.get("ticket"))
    if "error" in result:
        # The queue's own message is Turkish; the page says it in its language.
        refusal = getattr(texts, f"REVIEW_{result['error']}", result["message"])
        st.session_state.review_notice = ("refused", refusal)
    else:
        st.session_state.review_notice = ("done", done)
    st.rerun()


def draw_table(table: dict, language: Language) -> None:
    """A readable table, its numbers written the page language's way."""
    frame = pd.DataFrame(table["rows"], columns=table["columns"])
    # Written the page language's way whatever the browser's settings; only
    # the display changes, so a column still sorts as numbers.
    st.dataframe(
        frame.style.format(
            {
                header: partial(format_number, whole=whole, language=language)
                for header, whole in table["numbers"].items()
            },
            na_rep="",
        ),
        hide_index=True,
    )


def draw_seller_report(path: Path) -> None:
    """The seller report of the operations page, built when it is asked for."""
    language = page_language()
    texts = catalog(language)
    with st.expander(texts.UI_SELLER_REPORT):
        if not st.toggle(texts.UI_SELLER_REPORT_SHOW, key="seller_report_on"):
            return
        report = seller_report(str(path), language)
        if "error" in report:
            st.error(report["message"])
            return
        st.caption(
            texts.UI_SELLER_REPORT_INTRO.format(
                items=report["min_items"], rows=config.SELLER_REPORT_ROWS
            )
        )
        if not report["rows"]:
            st.info(texts.UI_SELLER_REPORT_EMPTY)
            return
        draw_table(seller_report_table(report, language), language)
        for item in report["caveats"]:
            st.info(item["caveat"])
        st.caption(texts.UI_SELLER_REPORT_SOURCES)
        # Not an expander each: an expander cannot sit inside one.
        for words, sql in seller_report_sources(report, language):
            st.markdown(f"**{words}**")
            st.code(readable_sql(sql), language="sql", wrap_lines=True)


def draw_answer(view: AnswerView) -> None:
    language = page_language()
    texts = catalog(language)
    st.markdown(view.text)
    if view.sources:
        st.caption(f"{texts.UI_SOURCES}: {'; '.join(view.sources)}")
    table = readable_table(view.table, language) if view.table else None
    if table and table["rows"] and worth_a_table(table):
        st.caption(texts.UI_RESULT_TABLE)
        draw_table(table, language)
    for line in view.computed:
        st.caption(f"{texts.COMPUTED_HEADING}: {line}")
    for caveat in view.caveats:
        st.info(caveat)


def show_sql(heading: str, queries: list[str]) -> None:
    """The SQL in a wide window, where a long query has room to be read."""

    # Made here, so that its title is in the page's language.
    @st.dialog(page_texts().UI_SQL_DIALOG_TITLE, width="large")
    def window() -> None:
        st.caption(heading)
        for query in queries:
            st.code(readable_sql(query), language="sql", wrap_lines=True)

    window()


def draw_steps(view: AnswerView) -> None:
    """Who answered, which tools were called, steps and tokens."""
    texts = page_texts()
    st.write(f"**{texts.UI_STEPS_AGENT}:** {view.agent}")
    st.write(f"**{texts.UI_STEPS_TOOLS}:** {tools_text(view.tools, page_language())}")
    st.caption(texts.UI_STEPS_COUNTS.format(steps=view.steps, tokens=view.tokens))


def latest_answer() -> AnswerView | None:
    """The newest answer of the conversation, if there is one."""
    for role, content in reversed(st.session_state.get("turns", [])):
        if role == "answer":
            return content
    return None


def draw_turns() -> None:
    for role, content in st.session_state.turns:
        if role == "error":
            st.error(content)
            continue
        if role == "notice":
            st.info(content)
            continue
        # An answer is known by its role, not its class: the framework may
        # load the modules again, and an older answer is then of a class
        # that no longer matches.
        if role == "answer":
            with st.chat_message("assistant", avatar=content.avatar):
                draw_answer(content)
            continue
        # The person's messages, and the support agent's word on an approval
        # (a fixed text). What the person typed loads no image and makes no
        # link, as in an answer.
        avatar = USER_AVATAR if role == "user" else SUPPORT_AVATAR
        with st.chat_message(role, avatar=avatar):
            st.markdown(safe_markdown(content, page_language()))


def draw_approval(session: ChatSession) -> None:
    """The request that waits for the person: approve or give up."""
    language = page_language()
    texts = catalog(language)
    pending = st.session_state.pending
    with st.container(border=True):
        st.subheader(texts.UI_APPROVAL_HEADING)
        for label, value in approval_card(pending, language).items():
            st.write(f"**{label}:** {value}")
        approve, decline = st.columns(2)
        # The click is all the page sends: the approval itself is made and
        # checked in code, on the order server.
        choice = None
        if approve.button(texts.UI_APPROVE, type="primary", use_container_width=True):
            # The card goes with the click: the server writes the request
            # only if it is still the one that waits.
            choice = functools.partial(session.approve, pending)
        if decline.button(texts.UI_DECLINE, use_container_width=True):
            choice = session.decline
    if choice is not None:
        # The card goes first: a run cut short by a second click must not
        # find the request still waiting and send the choice again.
        st.session_state.pending = None
        try:
            st.session_state.turns.append(("assistant", choice()))
        except Exception as failure:  # noqa: BLE001
            st.session_state.turns.append(("error", friendly_error(failure, language)))
        st.rerun()


def answer(session: ChatSession, question: str) -> None:
    language = page_language()
    st.session_state.turns.append(("user", question))
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(safe_markdown(question, language))
    try:
        with st.spinner(catalog(language).UI_THINKING):
            view = view_of(session.ask(question), language)
    except Exception as failure:  # noqa: BLE001
        st.session_state.turns.append(("error", friendly_error(failure, language)))
    else:
        st.session_state.turns.append(("answer", view))
        st.session_state.pending = view.pending
    st.rerun()


def draw_rep_session(path: Path, identity: tuple) -> None:
    """The support rep's page: who is signed in, and the review queue."""
    texts = page_texts()
    with st.sidebar:
        draw_language_switch()
        st.header(texts.UI_SESSION_HEADING)
        st.markdown(f"{REP_AVATAR} **{texts.UI_SESSION_REP}**")
        change, refresh = st.columns(2)
        if change.button(texts.UI_CHANGE, use_container_width=True):
            sign_out()
            st.rerun()
        # A click is a new page run, which reads the queue again.
        refresh.button(texts.UI_REFRESH, use_container_width=True)
        st.caption(texts.UI_DATA_NOTE)
    draw_review(ReviewQueue(path, identity))


def main() -> None:
    texts = page_texts()
    st.set_page_config(page_title=texts.UI_TITLE, page_icon=str(ICON))
    st.logo(str(LOGO), size="large", icon_image=str(ICON))
    start_tracing()
    st.title(texts.UI_TITLE)
    if os.environ.get(config.PAUSE_VARIABLE) == "1":
        # Before the database, the sessions and the model: nothing runs.
        st.info(texts.UI_PAUSED)
        st.stop()

    try:
        path = database(resources.db_path())
    except Exception:
        # Not cached: the next page run tries again.
        logging.getLogger(__name__).exception("the demo database could not be built")
        st.error(texts.UI_NO_DATABASE)
        st.stop()

    customers = demo_customers(str(path))
    identity = st.session_state.get("identity")
    if identity is None:
        with st.sidebar:
            st.caption(texts.UI_DATA_NOTE)
        # On the choice screen, not in the sidebar: a phone shows the sidebar
        # closed, and the language is chosen before anything else.
        draw_language_switch()
        # The session type is chosen here, on the choice screen, and nowhere
        # else: a message cannot change it.
        chosen = draw_choice(customers)
        if chosen is not None:
            st.session_state.identity = chosen
            st.rerun()
        return

    if tuple(identity) == REP_IDENTITY:
        draw_rep_session(path, identity)
        return

    is_customer = identity[0] == "customer"
    customer = None
    if is_customer:
        # The situation was chosen from the list; the id comes from it here.
        customer = next((c for c in customers if c.situation == identity[1]), None)
        if customer is None:
            sign_out()
            st.rerun()

    with st.sidebar:
        draw_language_switch()
        st.header(texts.UI_SESSION_HEADING)
        if is_customer:
            st.markdown(f"{USER_AVATAR} **{texts.UI_SESSION_CUSTOMER}**")
            st.caption(texts.DEMO_CUSTOMER_LABELS[customer.situation])
        else:
            st.markdown(f"{OPS_AVATAR} **{texts.UI_SESSION_OPS}**")
        change, new = st.columns(2)
        if change.button(texts.UI_CHANGE, use_container_width=True):
            sign_out()
            st.rerun()
        restart = new.button(texts.UI_NEW_CONVERSATION, use_container_width=True)
        st.caption(texts.UI_DATA_NOTE)

    st.caption(texts.UI_CAPTION_CUSTOMER if is_customer else texts.UI_CAPTION_OPS)
    if not is_customer:
        draw_seller_report(path)
    customer_id = customer.customer_unique_id if is_customer else None
    # A new identity has no conversation yet.
    if restart or "turns" not in st.session_state:
        open_session(identity, customer_id)
    elif getattr(st.session_state.get("session"), "closed", False):
        # Closed by the pool after a long pause: start again and say why.
        open_session(identity, customer_id)
        st.session_state.turns.insert(0, ("notice", texts.UI_SESSION_EXPIRED))
    if st.session_state.pop("language_notice", False):
        st.session_state.turns.insert(0, ("notice", texts.UI_LANGUAGE_CHANGED))

    # Drawn after the conversation was settled above, so a new one never
    # shows the SQL or the steps of the old.
    latest = latest_answer()
    if latest is not None:
        with st.sidebar:
            # The SQL behind the newest numbers, or the SQL tried when no
            # answer was found: the evidence, kept out of the conversation.
            if latest.queries and st.button(
                texts.UI_SHOW_SQL, key="show_sql", use_container_width=True
            ):
                show_sql(latest.queries_heading.rstrip(":"), latest.queries)
            # Closed by default: what an evaluator wants to see, not a
            # customer.
            with st.expander(texts.UI_DEVELOPER_DETAILS):
                st.caption(texts.UI_STEPS_LATEST)
                draw_steps(latest)

    draw_turns()
    session = st.session_state.get("session")
    if session is None:
        return
    waiting = st.session_state.pending is not None
    if waiting:
        draw_approval(session)
    clicked = None
    # A note on why the conversation is new is not part of it.
    said = [turn for turn in st.session_state.turns if turn[0] != "notice"]
    if not said and not waiting:
        clicked = draw_examples()
    prompt = texts.UI_INPUT_CUSTOMER if is_customer else texts.UI_INPUT_OPS
    # The limit here only helps the visitor; the server checks it again.
    question = st.chat_input(
        texts.UI_INPUT_WAITING_APPROVAL if waiting else prompt,
        disabled=waiting,
        max_chars=config.MAX_MESSAGE_CHARS,
    )
    # An example is sent as if it was typed.
    if question or clicked:
        answer(session, question or clicked)


main()
