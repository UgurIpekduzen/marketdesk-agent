"""Tests for the critic of the operations agent, with a stand-in model.

The critic checks in code that every number in an answer is one a tool
returned for the question. When one is not, the model is asked once more;
an answer that still holds one is shown with a note.
"""

import asyncio

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

import config
from src import messages, messages_en, tracing
from src.agents import critic
from src.agents.ops import OpsAgent
from src.i18n import Language
from tests.fakes import FakeLLM

JUNE = [("run_metric", {"metric_name": "order_count", "purchase_month": ["2018-06"]})]


@pytest.fixture
def fake():
    return FakeLLM()


@pytest.fixture
def make_agent(synthetic_db_path, fake):
    agents = []

    def make(**options):
        agent = OpsAgent(synthetic_db_path, fake, **options)
        agents.append(agent)
        return agent

    yield make
    for agent in agents:
        agent.close()


def ask(agent, *questions):
    async def run():
        reply = None
        for question in questions:
            reply = await agent.ask(question)
        return reply

    return asyncio.run(run())


def asked_for_correction(fake) -> bool:
    return messages.CRITIC_CORRECTION.split("{")[0] in str(fake.requests[-1])


# --- The check ------------------------------------------------------------------


def test_a_number_a_tool_returned_is_supported():
    results = [("run_metric", {"rows": [[29, 29]], "caveat": "Not."})]

    assert critic.unsupported("Haziran'da 29 sipariş var.", results, "Kaç?") == []


def test_a_number_no_tool_returned_is_not():
    results = [("run_metric", {"rows": [[29, 29]]})]

    assert critic.unsupported("Haziran'da 777 sipariş var.", results, "Kaç?") == ["777"]


def test_a_number_the_question_holds_dates_and_years_are_left_out():
    results = [("run_metric", {"rows": [[29, 29]]})]
    text = (
        "2018-06-01 ile 30.06.2018 arası, 2018 Haziran: 29 sipariş. Soruda 500 vardı."
    )

    assert critic.unsupported(text, results, "500 siparişten fazla mı?") == []


@pytest.mark.parametrize(
    "text",
    ["848.860,10 BRL", "848,860.10 BRL", "Yaklaşık 848,86 bin BRL"],
)
def test_the_turkish_and_the_english_way_of_writing_a_number_are_both_read(text):
    results = [("run_metric", {"rows": [[848860.1]]})]

    assert critic.unsupported(text, results, "GMV?") == []


def test_a_sellers_pseudonym_is_a_name_not_a_number():
    results = [("seller_report", {"rows": [["S-1286", 34, 82.35]]})]
    text = "S-1286 en yüksek orana sahip (%82,35, 34 kalem); S-1397 en düşük."

    assert critic.unsupported(text, results, "Rapor?") == []


# --- In the agent ---------------------------------------------------------------


def test_an_answer_whose_numbers_come_from_the_tools_is_left_as_it_is(make_agent, fake):
    fake.script = [JUNE, "Haziran 2018'de 29 sipariş var."]

    reply = ask(make_agent(), "Haziran 2018'de kaç sipariş?")

    assert reply.critic == critic.OK
    assert reply.text == "Haziran 2018'de 29 sipariş var."
    assert len(fake.requests) == 2


def test_an_unsupported_number_gets_one_correction(make_agent, fake):
    fake.script = [
        JUNE,
        "Haziran 2018'de 777 sipariş var.",
        "Haziran 2018'de 29 sipariş var.",
    ]

    reply = ask(make_agent(), "Haziran 2018'de kaç sipariş?")

    assert reply.critic == critic.CORRECTED
    assert reply.text == "Haziran 2018'de 29 sipariş var."
    assert asked_for_correction(fake)
    assert "777" in str(fake.requests[-1])
    # The correction is one more model call, and it is counted in the run.
    assert reply.log.llm_calls == 3


def test_an_answer_that_is_still_wrong_is_shown_with_a_note(make_agent, fake):
    fake.script = [JUNE, "777 sipariş var.", "Hâlâ 888 sipariş var."]

    reply = ask(make_agent(), "Haziran 2018'de kaç sipariş?")

    assert reply.critic == critic.FLAGGED
    assert reply.text == f"Hâlâ 888 sipariş var.\n\n{messages.CRITIC_NOTE}"
    # Once, not until it is right.
    assert reply.log.llm_calls == 3


def test_the_note_is_in_the_language_of_the_session(make_agent, fake):
    fake.script = [JUNE, "777 orders.", "888 orders."]

    reply = ask(make_agent(language=Language.EN), "How many orders in June 2018?")

    assert reply.text.endswith(messages_en.CRITIC_NOTE)


def test_the_note_does_not_repeat_the_numbers(make_agent, fake):
    fake.script = [JUNE, "777 sipariş var.", "888 sipariş var."]

    reply = ask(make_agent(), "Haziran 2018'de kaç sipariş?")

    assert "888" not in messages.CRITIC_NOTE
    assert reply.text.count("888") == 1


def test_a_critic_switched_off_leaves_the_answer_alone(make_agent, fake):
    fake.script = [JUNE, "777 sipariş var."]

    reply = ask(make_agent(use_critic=False), "Haziran 2018'de kaç sipariş?")

    assert reply.critic is None
    assert reply.text == "777 sipariş var."
    assert len(fake.requests) == 2


def test_the_setting_in_config_switches_it_off(make_agent, fake, monkeypatch):
    monkeypatch.setattr(config, "CRITIC_ENABLED", False)
    fake.script = [JUNE, "777 sipariş var."]

    reply = ask(make_agent(), "Haziran 2018'de kaç sipariş?")

    assert reply.critic is None


def test_the_number_of_corrections_is_a_setting(make_agent, fake, monkeypatch):
    monkeypatch.setattr(config, "CRITIC_MAX_CORRECTIONS", 0)
    fake.script = [JUNE, "777 sipariş var."]

    reply = ask(make_agent(), "Haziran 2018'de kaç sipariş?")

    assert reply.critic == critic.FLAGGED
    assert len(fake.requests) == 2


def test_each_question_is_checked_against_its_own_tool_results(make_agent, fake):
    # 29 came from the first question's tool; the second has no tool call.
    fake.script = [JUNE, "29 sipariş var.", "Tekrar: 29 sipariş.", "Hâlâ 29."]

    reply = ask(make_agent(), "Haziran 2018'de kaç sipariş?", "Tekrar söyler misin?")

    assert reply.critic == critic.FLAGGED


def test_a_refusal_with_no_numbers_passes(make_agent, fake):
    fake.script = ["Bu bir operasyon verisi sorusu değil."]

    reply = ask(make_agent(), "Bana bir şiir yaz.")

    assert reply.critic == critic.OK
    assert len(fake.requests) == 1


def test_a_run_that_gave_up_is_not_looked_at(make_agent, fake):
    attempts = [
        "SELECT customer_city FROM v_orders",
        "SELECT city FROM v_orders",
        "SELECT o.customer_city FROM v_orders AS o",
    ]
    fake.script = [
        *([("run_sql", {"query": query})] for query in attempts),
        "Bir şey söyledim: 777.",
    ]

    reply = ask(make_agent(), "Şehirleri say.")

    assert reply.gave_up
    assert reply.critic is None
    assert len(fake.requests) == 4


def test_the_correction_is_marked_on_the_log_and_the_trace(make_agent, fake, caplog):
    import logging

    caplog.set_level(logging.INFO)
    fake.script = [JUNE, "777 sipariş var.", "29 sipariş var."]

    ask(make_agent(), "Haziran 2018'de kaç sipariş?")

    assert "critic status=corrected unsupported=0" in caplog.text
    assert "777" not in caplog.text.split("critic status")[1]


def test_the_critic_s_status_is_on_the_trace(make_agent, fake, monkeypatch):
    monkeypatch.setattr(tracing, "_personal_values", {})
    exporter = InMemorySpanExporter()
    tracing.setup_tracing("phoenix", exporter=exporter, batch=False)
    try:
        fake.script = [JUNE, "777 sipariş var.", "888 sipariş var."]
        with tracing.span("message"):
            ask(make_agent(), "Haziran 2018'de kaç sipariş?")
    finally:
        tracing.shutdown_tracing()

    marked = {
        f"{key.split('.', 1)[1]}={value}"
        for span in exporter.get_finished_spans()
        for key, value in span.attributes.items()
        if key.startswith("marketdesk.")
    }
    assert "critic=flagged" in marked


def test_a_pseudonym_in_an_answer_does_not_ask_for_a_correction(
    make_agent, fake, monkeypatch
):
    # The synthetic database has one seller of 24 items.
    monkeypatch.setattr(config, "SELLER_REPORT_MIN_ITEMS", 1)
    fake.script = [
        [("seller_report", {})],
        "En yüksek orana S-0001 sahip.",
        "Hiç gerekmeyen düzeltme.",
    ]

    reply = ask(make_agent(), "Satıcı raporu?")

    assert reply.critic == critic.OK
    assert reply.text == "En yüksek orana S-0001 sahip."
    assert len(fake.requests) == 2


def test_the_wording_in_use_tells_the_model_to_compute_with_a_query(make_agent, fake):
    fake.script = [JUNE, "777 sipariş var.", "29 sipariş var."]

    reply = ask(make_agent(), "Haziran 2018'de kaç sipariş?")

    assert (
        config.CRITIC_CORRECTION_VARIANT == config.CRITIC_DEFAULT_VARIANT == "compute"
    )
    assert reply.critic == critic.CORRECTED
    assert "run_sql ile hesapla" in str(fake.requests[-1])
    assert "777" in str(fake.requests[-1])


def test_the_first_wording_only_asks_for_the_tools_numbers(
    make_agent, fake, monkeypatch
):
    monkeypatch.setattr(config, "CRITIC_CORRECTION_VARIANT", "plain")
    fake.script = [JUNE, "777 sipariş var.", "29 sipariş var."]

    ask(make_agent(), "Haziran 2018'de kaç sipariş?")

    assert "run_sql ile hesapla" not in str(fake.requests[-1])
    assert "777" in str(fake.requests[-1])
    assert set(critic.CORRECTIONS) == {"plain", "compute"}
