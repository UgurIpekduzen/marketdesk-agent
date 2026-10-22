"""Tests for the wrapper that stands between the agents and the provider."""

import ast
import asyncio
import importlib
from pathlib import Path

import pytest
from llama_index.core.base.llms.types import (
    ChatMessage,
    MessageRole,
    TextBlock,
    ToolCallBlock,
)

import config
from src.guardrails import guarded_llm
from src.guardrails.guarded_llm import GuardedLLM, build_llm
from src.guardrails.outbound import Redactor
from src.tools.session import Session
from tests.fakes import FakeLLM

RAW_ID = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GUARD_MODULE = PROJECT_ROOT / "src" / "guardrails" / "guarded_llm.py"


@pytest.fixture
def fake():
    return FakeLLM(script=["tamam"] * 5)


@pytest.fixture
def guarded(fake):
    return GuardedLLM(inner=fake, redactor=Redactor())


def user(text):
    return ChatMessage(role=MessageRole.USER, content=text)


def texts_sent(fake):
    return [
        block["text"]
        for request in fake.requests
        for message in request.get("messages", [])
        for block in message["blocks"]
        if block["block_type"] == "text"
    ]


# --- Every way of calling the model is cleaned --------------------------


def test_chat_is_cleaned(guarded, fake):
    response = guarded.chat([user(f"{RAW_ID} nerede?")])

    assert texts_sent(fake) == ["[id] nerede?"]
    assert response.message.content == "tamam"


def test_async_chat_is_cleaned(guarded, fake):
    asyncio.run(guarded.achat([user(f"{RAW_ID} nerede?")]))

    assert texts_sent(fake) == ["[id] nerede?"]


def test_streaming_chat_is_cleaned(guarded, fake):
    list(guarded.stream_chat([user(f"{RAW_ID} nerede?")]))

    assert texts_sent(fake) == ["[id] nerede?"]


def test_async_streaming_chat_is_cleaned(guarded, fake):
    async def run():
        stream = await guarded.astream_chat([user(f"{RAW_ID} nerede?")])
        return [chunk async for chunk in stream]

    asyncio.run(run())

    assert texts_sent(fake) == ["[id] nerede?"]


def test_completion_calls_are_cleaned(guarded, fake):
    async def run_async():
        await guarded.acomplete(f"c {RAW_ID}")
        stream = await guarded.astream_complete(f"d {RAW_ID}")
        return [chunk async for chunk in stream]

    guarded.complete(f"a {RAW_ID}")
    list(guarded.stream_complete(f"b {RAW_ID}"))
    asyncio.run(run_async())

    assert [request["prompt"] for request in fake.requests] == [
        "a [id]",
        "b [id]",
        "c [id]",
        "d [id]",
    ]


# --- Every part of a request is cleaned ---------------------------------


def test_every_role_is_cleaned(guarded, fake):
    guarded.chat(
        [
            ChatMessage(role=MessageRole.SYSTEM, content=f"System note {RAW_ID}"),
            user("ayse@example.com"),
            ChatMessage(role=MessageRole.ASSISTANT, content=f"Asked about {RAW_ID}"),
            ChatMessage(
                role=MessageRole.TOOL,
                content=f'{{"order_id": "{RAW_ID}"}}',
                additional_kwargs={"tool_call_id": "call-1", "note": RAW_ID},
            ),
        ]
    )

    assert RAW_ID not in fake.sent_text()
    assert "ayse@example.com" not in fake.sent_text()
    assert texts_sent(fake) == [
        "System note [id]",
        "[email]",
        "Asked about [id]",
        '{"order_id": "[id]"}',
    ]
    # The tool call id survives; the stray id next to it does not.
    assert fake.requests[0]["messages"][3]["additional_kwargs"] == {
        "tool_call_id": "call-1",
        "note": "[id]",
    }


def test_arguments_of_earlier_tool_calls_are_cleaned(guarded, fake):
    earlier_call = ChatMessage(
        role=MessageRole.ASSISTANT,
        blocks=[
            TextBlock(text="Looking it up."),
            ToolCallBlock(
                tool_call_id="call-1",
                tool_name="get_order_status",
                tool_kwargs={"order_ref": RAW_ID},
            ),
        ],
    )

    guarded.chat([earlier_call])

    blocks = fake.requests[0]["messages"][0]["blocks"]
    assert blocks[1]["tool_name"] == "get_order_status"
    assert blocks[1]["tool_kwargs"] == {"order_ref": "[id]"}
    assert RAW_ID not in fake.sent_text()


def test_messages_given_by_the_caller_are_not_changed(guarded):
    message = user(f"{RAW_ID} nerede?")

    guarded.chat([message])

    assert message.content == f"{RAW_ID} nerede?"


def test_clean_request_is_passed_on_as_it_is(guarded, fake):
    guarded.chat([user("İade süresi kaç gün?")], temperature=0)

    assert texts_sent(fake) == ["İade süresi kaç gün?"]
    assert fake.requests[0]["kwargs"] == {"temperature": "0"}


def test_customer_session_gets_aliases_instead_of_masks(fake):
    session = Session("u_alice", personal_values={"campinas": "[city]"})
    guarded = GuardedLLM(inner=fake, redactor=session.redactor())

    guarded.chat([user(f"{RAW_ID} nerede? Campinas'tayım.")])

    assert texts_sent(fake) == ["SIP-1 nerede? [city]'tayım."]
    assert session.order_id_for("SIP-1") == RAW_ID


# --- The wrapper looks like the model it wraps --------------------------


def test_metadata_is_the_wrapped_models(guarded, fake):
    assert guarded.metadata == fake.metadata
    assert guarded.metadata.is_function_calling_model


def test_response_is_passed_back_unchanged(fake):
    fake.script = [f"Cevap: {RAW_ID}"]
    guarded = GuardedLLM(inner=fake, redactor=Redactor())

    response = guarded.chat([user("soru")])

    # Only outgoing text is cleaned; the model can only repeat what it was sent.
    assert response.message.content == f"Cevap: {RAW_ID}"


# --- The factory, and nobody else, knows the provider -------------------


def test_build_llm_wraps_the_provider_model(monkeypatch, fake):
    monkeypatch.setattr(guarded_llm, "build_provider_llm", lambda: fake)
    redactor = Redactor()

    llm = build_llm(redactor)

    assert isinstance(llm, GuardedLLM)
    assert llm.inner is fake
    assert llm.redactor is redactor


def test_build_llm_without_a_session_still_masks(monkeypatch, fake):
    monkeypatch.setattr(guarded_llm, "build_provider_llm", lambda: fake)

    build_llm().chat([user(RAW_ID)])

    assert texts_sent(fake) == ["[id]"]


def test_unknown_provider_is_an_error(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "somebody-else")

    with pytest.raises(ValueError, match="somebody-else"):
        guarded_llm.build_provider_llm()


def test_main_and_fallback_providers_have_an_api_key_variable():
    assert config.LLM_PROVIDER in guarded_llm.API_KEY_VARIABLES
    assert config.LLM_FALLBACK_PROVIDER in guarded_llm.API_KEY_VARIABLES


def test_main_model_is_used_unless_the_fallback_is_switched_on(monkeypatch):
    assert config.LLM_USE_FALLBACK is False
    assert guarded_llm.configured_model() == (config.LLM_PROVIDER, config.LLM_MODEL)

    monkeypatch.setattr(config, "LLM_USE_FALLBACK", True)

    assert guarded_llm.configured_model() == (
        config.LLM_FALLBACK_PROVIDER,
        config.LLM_FALLBACK_MODEL,
    )


def recording_provider(created):
    """A stand-in for a provider's model class that records how it is created."""

    def create(**kwargs):
        created.append(kwargs)

    return create


@pytest.mark.parametrize(
    ("use_fallback", "module", "class_name", "key_variable"),
    [
        (False, "llama_index.llms.google_genai", "GoogleGenAI", "GEMINI_API_KEY_FREE"),
        (True, "llama_index.llms.groq", "Groq", "GROQ_API_KEY"),
    ],
)
def test_provider_model_gets_name_key_and_temperature(
    monkeypatch, use_fallback, module, class_name, key_variable
):
    created = []
    monkeypatch.setattr(
        importlib.import_module(module), class_name, recording_provider(created)
    )
    monkeypatch.setattr(config, "LLM_USE_FALLBACK", use_fallback)
    monkeypatch.setenv(key_variable, "test-key")

    guarded_llm.build_provider_llm()

    expected_model = config.LLM_FALLBACK_MODEL if use_fallback else config.LLM_MODEL
    expected = {"model": expected_model, "api_key": "test-key", "temperature": 0}
    if use_fallback:
        # A Groq model is built with no extra settings unless asked.
        expected["additional_kwargs"] = {}
    assert created == [expected]


def test_a_groq_model_can_be_told_how_much_to_think(monkeypatch):
    created = []
    monkeypatch.setattr(
        importlib.import_module("llama_index.llms.groq"),
        "Groq",
        recording_provider(created),
    )
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    guarded_llm.build_provider_llm(
        "groq", "openai/gpt-oss-120b", reasoning_effort="low"
    )

    assert created[0]["additional_kwargs"] == {"reasoning_effort": "low"}


def test_a_model_can_be_given_its_own_temperature(monkeypatch):
    created = []
    monkeypatch.setattr(
        importlib.import_module("llama_index.llms.groq"),
        "Groq",
        recording_provider(created),
    )
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    guarded_llm.build_provider_llm("groq", "qwen/qwen3.8-27b")
    guarded_llm.build_provider_llm("groq", "qwen/qwen3.8-27b", temperature=0.7)

    assert [model["temperature"] for model in created] == [
        config.LLM_TEMPERATURE,
        0.7,
    ]


def test_only_groq_models_take_a_reasoning_effort(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY_FREE", "test-key")

    with pytest.raises(ValueError, match="reasoning_effort"):
        guarded_llm.build_provider_llm(
            "gemini", config.LLM_MODEL, reasoning_effort="low"
        )


def test_missing_api_key_is_an_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY_FREE", raising=False)

    with pytest.raises(KeyError, match="GEMINI_API_KEY_FREE"):
        guarded_llm.build_provider_llm()


def imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def is_provider_module(name):
    """True for a provider's own package or LlamaIndex's wrapper around one."""
    return name.startswith(
        ("llama_index.llms.", "google.genai", "google.generativeai", "groq")
    )


def test_only_the_guard_module_imports_a_provider():
    offenders = []
    sources = [
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "config.py",
        *(PROJECT_ROOT / "src").rglob("*.py"),
        *(PROJECT_ROOT / "scripts").rglob("*.py"),
        *(PROJECT_ROOT / "eval").rglob("*.py"),
    ]
    for path in sources:
        if path == GUARD_MODULE:
            continue
        offenders += [
            f"{path.relative_to(PROJECT_ROOT)}: {name}"
            for name in imported_modules(path)
            if is_provider_module(name)
        ]

    assert offenders == []
    assert any(is_provider_module(name) for name in imported_modules(GUARD_MODULE))


def test_the_import_check_recognises_a_provider_import(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import os\n"
        "from llama_index.core.llms import ChatMessage\n"
        "from llama_index.llms.groq import Groq\n"
        "import google.genai\n",
        encoding="utf-8",
    )

    found = [name for name in imported_modules(sample) if is_provider_module(name)]

    assert found == ["llama_index.llms.groq", "google.genai"]
