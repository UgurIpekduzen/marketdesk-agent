"""Tests for the session's language below the page: the prompts, the tool
results the model reads and the texts the agents give back.

A Turkish session must send the model exactly what it did before English
was added, so the evaluation's cached answers still apply; an English
session gets English instructions, amounts, citations and caveats.
"""

import asyncio
import hashlib

import config
from src import messages, messages_en
from src.agents import ops as ops_module
from src.agents import support as support_module
from src.agents.ops import OpsAgent
from src.i18n import Language
from src.knowledge.semantic_layer import list_metrics, load_semantic_layer
from src.mcp_server.client import OrdersClient
from src.orchestrator import Orchestrator
from src.tools.policies import search_policies
from tests.agent_harness import with_agent, with_customer_router
from tests.fakes import FakeLLM
from tests.synthetic_data import ALICE

# sha256 of the Turkish prompts as they were before the language was added.
# A change here changes every request to the model and empties the
# evaluation's cache. Changed on purpose to try three sentences (a request
# asked with a question is opened, an uncovered topic ends with the offer of a
# human, a section's executor is named).
TURKISH_SUPPORT_PROMPT = (
    "fdd8db15b1a51f5a829d8e0e890843e94d3a25d04c76ace57b07379f752f99ca"
)
# Changed on purpose when the seller report tool was added (one sentence in
# step 2); the ops answers in the evaluation's cache were emptied with it.
TURKISH_OPS_PROMPT = "e5408f233b0f9e469f366879fbf46dafb74b8f7cf441cc7bb182fbdcf25877fe"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def ops_prompt_without_schema(language: Language) -> str:
    return ops_module.SYSTEM_PROMPT.format(
        today=config.SIMULATED_TODAY.isoformat(),
        corrections=config.SQL_MAX_CORRECTIONS,
        schema="{schema}",
        language="Turkish" if language == Language.TR else "English",
        number_rule=ops_module.NUMBER_RULES[language],
    )


# --- Prompts --------------------------------------------------------------


def test_the_turkish_prompts_are_what_they_were():
    assert sha(support_module.system_prompt(Language.TR)) == TURKISH_SUPPORT_PROMPT
    assert sha(ops_prompt_without_schema(Language.TR)) == TURKISH_OPS_PROMPT


def test_the_english_support_prompt_asks_for_english_with_english_examples():
    prompt = support_module.system_prompt(Language.EN)

    assert "Always answer\nin English" in prompt
    assert "(Returns Policy, Section 2)" in prompt
    assert "(for example\n133.14 BRL)" in prompt
    assert "Turkish" not in prompt
    # Everything else is the same text.
    assert len(prompt.splitlines()) == len(
        support_module.system_prompt(Language.TR).splitlines()
    )


def test_the_english_ops_prompt_asks_for_english_numbers(synthetic_db_path):
    prompt = ops_module.system_prompt(synthetic_db_path, Language.EN)

    assert "Always answer in English" in prompt
    assert "Write numbers the English way" in prompt
    assert "(848,860.10 BRL)" in prompt
    assert "Turkish" not in prompt


# --- Order server: amounts written for the customer ------------------------


def call_server(db_path, language, name, arguments):
    async def run():
        async with OrdersClient(db_path, ALICE, language) as orders:
            return await orders.call(name, arguments)

    return asyncio.run(run())


def test_an_english_order_server_writes_amounts_the_english_way(synthetic_db_path):
    order = call_server(
        synthetic_db_path, Language.EN, "get_order_status", {"order_ref": "o_day14"}
    )
    check = call_server(
        synthetic_db_path,
        Language.EN,
        "check_return_eligibility",
        {"order_ref": "o_day14", "reason": "damaged"},
    )

    assert order["items_total_text"] == "115.00 BRL"
    item = order["items"][0]
    assert item["price_text"] == f"{item['price']} BRL"
    assert check["refund_amount_text"] == "115.00 BRL"
    # The plain numbers, which tools are called with, do not change.
    assert order["items_total"] == "115.00"
    assert check["refund_amount"] == "115.00"


def test_an_order_server_started_without_a_language_writes_turkish(synthetic_db_path):
    order = call_server(
        synthetic_db_path, Language.TR, "get_order_status", {"order_ref": "o_day14"}
    )

    assert order["items_total_text"] == "115,00 BRL"


def test_a_message_from_the_server_stays_turkish_in_english(synthetic_db_path):
    """Strings only the model reads are not translated."""
    missing = call_server(
        synthetic_db_path, Language.EN, "get_order_status", {"order_ref": "o_none"}
    )

    assert missing["message"] == messages.ORDER_NOT_FOUND


# --- Policy search ---------------------------------------------------------


def test_english_search_results_cite_english_titles(fake_policy_index):
    turkish = search_policies(fake_policy_index, "iade süresi", 3)
    english = search_policies(fake_policy_index, "iade süresi", 3, Language.EN)

    for tr, en in zip(turkish["results"], english["results"], strict=True):
        title = messages_en.POLICY_DOCUMENT_TITLES[tr["document"]]
        assert en["document"] == title
        assert en["citation"] == f"{title}, Section {tr['section']}"
        # The section itself is the Turkish text.
        assert en["text"] == tr["text"]


# --- Ops agent --------------------------------------------------------------


def run_ops(db_path, language, script, question="GMV ne kadar?"):
    fake = FakeLLM(script=list(script))
    agent = OpsAgent(db_path, fake, language)
    try:
        return asyncio.run(agent.ask(question)), fake
    finally:
        agent.close()


def metric_script(answer):
    return [
        [("list_metrics", {})],
        [("run_metric", {"metric_name": "gmv"})],
        answer,
    ]


def test_an_english_ops_session_gets_english_metrics_and_caveat(synthetic_db_path):
    reply, fake = run_ops(synthetic_db_path, Language.EN, metric_script("GMV is ..."))
    gmv = load_semantic_layer().metrics["gmv"]

    assert reply.caveats == [gmv.caveat_en]
    sent = fake.sent_text()
    assert gmv.description_en in sent
    assert gmv.caveat_en in sent
    assert messages_en.OPS_USED_SQL_HEADING in reply.display


def test_a_turkish_ops_session_gets_the_metrics_as_listed(synthetic_db_path):
    reply, fake = run_ops(synthetic_db_path, Language.TR, metric_script("GMV ..."))
    gmv = load_semantic_layer().metrics["gmv"]

    assert reply.caveats == [gmv.caveat]
    assert gmv.caveat_en not in fake.sent_text()
    assert list_metrics()["metrics"][0]["caveat"] in fake.sent_text()


# --- Router and support agent ---------------------------------------------


def test_an_english_router_refuses_in_english(synthetic_db_path):
    async def run():
        router = Orchestrator.for_ops(
            synthetic_db_path, FakeLLM(script=["out_of_scope"]), Language.EN
        )
        try:
            return await router.ask("Write me a poem")
        finally:
            router.close()

    answer = asyncio.run(run())

    assert answer.display == messages_en.ROUTER_OUT_OF_SCOPE_OPS


def test_english_approval_texts(synthetic_db_path, fake_policy_index):
    fake = FakeLLM(
        script=[
            [
                (
                    "create_return_request",
                    {"order_ref": "o_day14", "reason": "damaged", "amount": "115.00"},
                )
            ],
            "You will be asked to confirm.",
        ]
    )

    async def scenario(agent):
        reply = await agent.ask("o_day14 arrived damaged, I want to return it.")
        summary = agent.approval_summary(reply.awaiting_approval)
        return summary, await agent.decline(), await agent.approve()

    summary, declined, nothing = with_agent(
        synthetic_db_path, fake_policy_index, fake, scenario, language=Language.EN
    )

    assert summary == (
        "Return request to be created:\n"
        "  Order: SIP-1\n"
        "  Reason: damaged item\n"
        "  Refund amount: 115.00 BRL\n"
        "  The request will open as: waiting for review"
    )
    assert declined == messages_en.APPROVAL_DECLINED
    assert nothing == messages_en.RETURN_REQUEST_NOT_CREATED.format(
        reason=messages_en.NOTHING_PENDING
    )


def test_an_english_customer_router_tells_its_agent_the_language(
    synthetic_db_path, fake_policy_index
):
    fake = FakeLLM(script=["support", "Hello."])

    async def scenario(router):
        await router.ask("Hello")
        return router.language

    language = with_customer_router(
        synthetic_db_path, fake_policy_index, fake, scenario, language=Language.EN
    )

    assert language == Language.EN
    assert "Always answer\\nin English" in fake.sent_text()
