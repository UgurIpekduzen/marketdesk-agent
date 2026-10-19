"""The MarketDesk chat page.

Run with:  streamlit run app.py

The page only draws and passes clicks on. Who the session belongs to, what
it may ask, the rules, the approval of a return request and every Turkish
text live in src/; nothing is decided here.
"""

import logging
from functools import partial
from pathlib import Path

import pandas as pd
import streamlit as st

import config
from src import messages, tracing
from src.formatting import (
    format_number,
    readable_sql,
    readable_table,
    worth_a_table,
)
from src.ui import resources
from src.ui.chat_session import ChatSession
from src.ui.question_limit import QuestionLimit
from src.ui.session_pool import SessionPool
from src.ui.view import (
    OPS_AVATAR,
    SUPPORT_AVATAR,
    USER_AVATAR,
    AnswerView,
    approval_card,
    friendly_error,
    tools_text,
    view_of,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO = ASSETS / "logo.svg"  # the mark and the name, at the top of the sidebar
ICON = ASSETS / "icon.svg"  # the mark alone: the browser tab, a closed sidebar


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
def policy_index():
    return resources.load_policy_index()


@st.cache_resource(show_spinner=False)
def database(path: Path) -> Path:
    """The database, built once per server process if it is missing."""
    if not path.exists():
        with st.spinner(messages.UI_PREPARING_DATABASE):
            resources.build_database(path)
    return path


@st.cache_data
def demo_customers(path: str):
    return resources.load_demo_customers(path)


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
    index = policy_index() if customer_unique_id else None
    try:
        st.session_state.session = session_pool().open(
            lambda: ChatSession(
                resources.db_path(),
                index,
                customer_unique_id,
                question_limit=question_limit(),
            )
        )
    except Exception as failure:  # noqa: BLE001
        st.session_state.turns.append(("error", friendly_error(failure)))


def sign_out() -> None:
    """Back to the choice screen: the conversation and its identity go."""
    close_session()
    for name in ("identity", "turns", "pending"):
        st.session_state.pop(name, None)


def draw_choice(customers: list) -> tuple | None:
    """The choice screen: as a customer in a situation, or as the ops team.

    Returns the chosen identity, or None until a start button is clicked.
    The customer comes from the server-side list; only its situation is
    kept, and the id is looked up again on every page run.
    """
    st.subheader(messages.UI_CHOICE_HEADING)
    st.caption(messages.UI_CHOICE_NOTE)
    customer_card, ops_card = st.columns(2)
    chosen = None
    with customer_card.container(border=True):
        st.markdown(f"{USER_AVATAR} **{messages.UI_CHOICE_CUSTOMER}**")
        st.write(messages.UI_CHOICE_CUSTOMER_TEXT)
        if customers:
            # A radio, not a drop-down: the labels are read whole.
            customer = st.radio(
                messages.UI_CUSTOMER_PICKER,
                customers,
                format_func=lambda choice: choice.label,
            )
            clicked = st.button(
                messages.UI_START_CUSTOMER, type="primary", use_container_width=True
            )
            # A value written by hand comes back as the text sent, not as one
            # of the customers: it is no choice.
            if clicked and customer in customers:
                chosen = ("customer", customer.situation)
        else:
            st.error(messages.UI_NO_CUSTOMERS)
    with ops_card.container(border=True):
        st.markdown(f"{OPS_AVATAR} **{messages.UI_CHOICE_OPS}**")
        st.write(messages.UI_CHOICE_OPS_TEXT)
        if st.button(messages.UI_START_OPS, use_container_width=True):
            chosen = ("ops",)
    return chosen


def draw_answer(view: AnswerView) -> None:
    st.markdown(view.text)
    if view.sources:
        st.caption(f"{messages.UI_SOURCES}: {'; '.join(view.sources)}")
    table = readable_table(view.table) if view.table else None
    if table and table["rows"] and worth_a_table(table):
        frame = pd.DataFrame(table["rows"], columns=table["columns"])
        st.caption(messages.UI_RESULT_TABLE)
        # Written the Turkish way whatever the visitor's browser language;
        # only the display changes, so a column still sorts as numbers.
        st.dataframe(
            frame.style.format(
                {
                    header: partial(format_number, whole=whole)
                    for header, whole in table["numbers"].items()
                },
                na_rep="",
            ),
            hide_index=True,
        )
    for caveat in view.caveats:
        st.info(caveat)


def draw_steps(view: AnswerView) -> None:
    """Who answered, which tools were called, steps and tokens."""
    st.write(f"**{messages.UI_STEPS_AGENT}:** {view.agent}")
    st.write(f"**{messages.UI_STEPS_TOOLS}:** {tools_text(view.tools)}")
    st.caption(messages.UI_STEPS_COUNTS.format(steps=view.steps, tokens=view.tokens))


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
        # The person's messages, and the support agent's word on an approval.
        avatar = USER_AVATAR if role == "user" else SUPPORT_AVATAR
        with st.chat_message(role, avatar=avatar):
            st.markdown(content)


def draw_approval(session: ChatSession) -> None:
    """The request that waits for the person: approve or give up."""
    pending = st.session_state.pending
    with st.container(border=True):
        st.subheader(messages.UI_APPROVAL_HEADING)
        for label, value in approval_card(pending).items():
            st.write(f"**{label}:** {value}")
        approve, decline = st.columns(2)
        # The click is all the page sends: the approval itself is made and
        # checked in code, on the order server.
        choice = None
        if approve.button(
            messages.UI_APPROVE, type="primary", use_container_width=True
        ):
            choice = session.approve
        if decline.button(messages.UI_DECLINE, use_container_width=True):
            choice = session.decline
    if choice is not None:
        # The card goes first: a run cut short by a second click must not
        # find the request still waiting and send the choice again.
        st.session_state.pending = None
        try:
            st.session_state.turns.append(("assistant", choice()))
        except Exception as failure:  # noqa: BLE001
            st.session_state.turns.append(("error", friendly_error(failure)))
        st.rerun()


def answer(session: ChatSession, question: str) -> None:
    st.session_state.turns.append(("user", question))
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(question)
    try:
        with st.spinner(messages.UI_THINKING):
            view = view_of(session.ask(question))
    except Exception as failure:  # noqa: BLE001
        st.session_state.turns.append(("error", friendly_error(failure)))
    else:
        st.session_state.turns.append(("answer", view))
        st.session_state.pending = view.pending
    st.rerun()


def main() -> None:
    st.set_page_config(page_title=messages.UI_TITLE, page_icon=str(ICON))
    st.logo(str(LOGO), size="large", icon_image=str(ICON))
    start_tracing()
    st.title(messages.UI_TITLE)

    try:
        path = database(resources.db_path())
    except Exception:
        # Not cached: the next page run tries again.
        logging.getLogger(__name__).exception("the demo database could not be built")
        st.error(messages.UI_NO_DATABASE)
        st.stop()

    customers = demo_customers(str(path))
    identity = st.session_state.get("identity")
    if identity is None:
        with st.sidebar:
            st.caption(messages.UI_DATA_NOTE)
        # The session type is chosen here, on the choice screen, and nowhere
        # else: a message cannot change it.
        chosen = draw_choice(customers)
        if chosen is not None:
            st.session_state.identity = chosen
            st.rerun()
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
        st.header(messages.UI_SESSION_HEADING)
        if is_customer:
            st.markdown(f"{USER_AVATAR} **{messages.UI_SESSION_CUSTOMER}**")
            st.caption(customer.label)
        else:
            st.markdown(f"{OPS_AVATAR} **{messages.UI_SESSION_OPS}**")
        change, new = st.columns(2)
        if change.button(messages.UI_CHANGE, use_container_width=True):
            sign_out()
            st.rerun()
        restart = new.button(messages.UI_NEW_CONVERSATION, use_container_width=True)
        st.caption(messages.UI_DATA_NOTE)

    st.caption(messages.UI_CAPTION_CUSTOMER if is_customer else messages.UI_CAPTION_OPS)
    customer_id = customer.customer_unique_id if is_customer else None
    # A new identity has no conversation yet.
    if restart or "turns" not in st.session_state:
        open_session(identity, customer_id)
    elif getattr(st.session_state.get("session"), "closed", False):
        # Closed by the pool after a long pause: start again and say why.
        open_session(identity, customer_id)
        st.session_state.turns.insert(0, ("notice", messages.UI_SESSION_EXPIRED))

    # Drawn after the conversation was settled above, so a new one never
    # shows the SQL or the steps of the old.
    latest = latest_answer()
    if latest is not None:
        with st.sidebar:
            # The SQL behind the newest numbers, or the SQL tried when no
            # answer was found: the evidence, kept out of the conversation.
            if latest.queries:
                with st.expander(latest.queries_heading.rstrip(":")):
                    for query in latest.queries:
                        st.code(readable_sql(query), language="sql", wrap_lines=True)
            # Closed by default: what an evaluator wants to see, not a
            # customer.
            with st.expander(messages.UI_DEVELOPER_DETAILS):
                st.caption(messages.UI_STEPS_LATEST)
                draw_steps(latest)

    draw_turns()
    session = st.session_state.get("session")
    if session is None:
        return
    waiting = st.session_state.pending is not None
    if waiting:
        draw_approval(session)
    prompt = messages.UI_INPUT_CUSTOMER if is_customer else messages.UI_INPUT_OPS
    # The limit here only helps the visitor; the server checks it again.
    question = st.chat_input(
        messages.UI_INPUT_WAITING_APPROVAL if waiting else prompt,
        disabled=waiting,
        max_chars=config.MAX_MESSAGE_CHARS,
    )
    if question:
        answer(session, question)


main()
