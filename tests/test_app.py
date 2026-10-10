"""Tests for the chat page, run without a browser: the real page script on
the synthetic database, with a stand-in model."""

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

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


def test_missing_database_is_said_plainly(open_page, monkeypatch):
    open_page()
    monkeypatch.setattr(resources, "db_path", lambda: Path("no/such.db"))

    page = AppTest.from_file(APP, default_timeout=60).run()

    assert not page.exception
    assert page.error[0].value == messages.UI_NO_DATABASE
    assert not page.chat_input


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
