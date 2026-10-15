"""The MarketDesk chat page.

Run with:  streamlit run app.py

The page only draws and passes clicks on. Who the session belongs to, what
it may ask, the rules, the approval of a return request and every Turkish
text live in src/; nothing is decided here.
"""

import logging
from pathlib import Path

import streamlit as st

import config
from src import messages, tracing
from src.ui import resources
from src.ui.chat_session import ChatSession
from src.ui.session_pool import SessionPool
from src.ui.view import AnswerView, approval_card, friendly_error, view_of

logging.basicConfig(level=logging.INFO, format="%(message)s")


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
            lambda: ChatSession(resources.db_path(), index, customer_unique_id)
        )
    except Exception as failure:  # noqa: BLE001
        st.session_state.turns.append(("error", friendly_error(failure)))


def draw_answer(view: AnswerView) -> None:
    st.markdown(view.text)
    if view.sources:
        st.caption(f"{messages.UI_SOURCES}: {'; '.join(view.sources)}")
    if view.table and view.table["rows"]:
        st.caption(messages.UI_RESULT_TABLE)
        st.dataframe(
            [
                dict(zip(view.table["columns"], row, strict=True))
                for row in view.table["rows"]
            ],
            hide_index=True,
        )
    for caveat in view.caveats:
        st.info(caveat)
    if view.queries:
        with st.expander(view.queries_heading.rstrip(":")):
            for query in view.queries:
                st.code(query, language="sql")
    with st.expander(messages.UI_STEPS):
        draw_steps(view)


def draw_steps(view: AnswerView) -> None:
    """Who answered, which tools were called, steps and tokens."""
    st.write(f"**{messages.UI_STEPS_AGENT}:** {view.agent}")
    tools = " → ".join(view.tools) or messages.UI_STEPS_NO_TOOLS
    st.write(f"**{messages.UI_STEPS_TOOLS}:** {tools}")
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
            with st.chat_message("assistant"):
                draw_answer(content)
            continue
        with st.chat_message(role):
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
    with st.chat_message("user"):
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
    st.set_page_config(page_title=messages.UI_TITLE, page_icon="🛍️")
    start_tracing()
    st.title(messages.UI_TITLE)

    try:
        path = database(resources.db_path())
    except Exception:
        # Not cached: the next page run tries again.
        logging.getLogger(__name__).exception("the demo database could not be built")
        st.error(messages.UI_NO_DATABASE)
        st.stop()

    # The session type is chosen here, at sign-in, and nowhere else: a
    # message cannot change it.
    with st.sidebar:
        st.header(messages.UI_SESSION_HEADING)
        kind = st.radio(
            messages.UI_SESSION_HEADING,
            [messages.UI_SESSION_CUSTOMER, messages.UI_SESSION_OPS],
            label_visibility="collapsed",
        )
        customer = None
        if kind == messages.UI_SESSION_CUSTOMER:
            customers = demo_customers(str(path))
            if not customers:
                st.error(messages.UI_NO_CUSTOMERS)
                st.stop()
            # Shown by situation; the id stays on the server side.
            customer = st.selectbox(
                messages.UI_CUSTOMER_PICKER,
                customers,
                format_func=lambda choice: choice.label,
            )
        restart = st.button(messages.UI_NEW_CONVERSATION)
        st.caption(messages.UI_TODAY.format(today=config.SIMULATED_TODAY.isoformat()))
        st.caption(messages.UI_DATA_NOTE)

    is_customer = customer is not None
    st.caption(messages.UI_CAPTION_CUSTOMER if is_customer else messages.UI_CAPTION_OPS)
    identity = ("customer", customer.situation) if is_customer else ("ops",)
    customer_id = customer.customer_unique_id if is_customer else None
    if restart or st.session_state.get("identity") != identity:
        open_session(identity, customer_id)
    elif getattr(st.session_state.get("session"), "closed", False):
        # Closed by the pool after a long pause: start again and say why.
        open_session(identity, customer_id)
        st.session_state.turns.insert(0, ("notice", messages.UI_SESSION_EXPIRED))

    # Drawn after the conversation was settled above, so a new one never
    # shows the steps of the old. Each answer keeps its own steps in the
    # conversation as well.
    latest = latest_answer()
    if latest is not None:
        with st.sidebar:
            st.divider()
            st.subheader(messages.UI_STEPS_LATEST)
            draw_steps(latest)

    draw_turns()
    session = st.session_state.get("session")
    if session is None:
        return
    waiting = st.session_state.pending is not None
    if waiting:
        draw_approval(session)
    prompt = messages.UI_INPUT_CUSTOMER if is_customer else messages.UI_INPUT_OPS
    question = st.chat_input(
        messages.UI_INPUT_WAITING_APPROVAL if waiting else prompt, disabled=waiting
    )
    if question:
        answer(session, question)


main()
