"""Tests for tracing: what a run records, and that nothing personal or
secret leaves with it. A stand-in model, no network."""

import importlib

import pytest
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

import config
from src import tracing
from src.agents.ops import OpsAgent
from src.guardrails.pii import HASH_KEY_VARIABLE, RAW_ID_PATTERN, hash_id
from tests.agent_harness import asking, with_agent
from tests.fakes import FakeLLM
from tests.synthetic_data import ALICE

RAW_ID = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"
API_KEY = "AIzaSy-not-a-real-key-0123456789"
HASH_KEY = "a-secret-hash-key"
RETURN = {"order_ref": "o_day14", "reason": "damaged", "amount": "115.00"}


@pytest.fixture
def secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", API_KEY)
    monkeypatch.setenv(HASH_KEY_VARIABLE, HASH_KEY)


@pytest.fixture
def traced(monkeypatch):
    """Switch tracing on with an exporter that keeps the spans in memory."""
    monkeypatch.setattr(tracing, "_personal_values", {})
    exporters = []

    def start(target="phoenix"):
        exporter = InMemorySpanExporter()
        tracing.setup_tracing(target, exporter=exporter, batch=False)
        exporters.append(exporter)
        return exporter

    yield start
    tracing.shutdown_tracing()


def dump(exporter) -> str:
    """Everything that was exported, as one text."""
    return "\n".join(span.to_json() for span in exporter.get_finished_spans())


def spans_named(exporter, name):
    return [span for span in exporter.get_finished_spans() if span.name == name]


def tool_spans(exporter):
    return [
        span
        for span in exporter.get_finished_spans()
        if span.attributes.get(tracing.SPAN_KIND) == "TOOL"
    ]


def support_run(db_path, index, script, *messages_to_send):
    fake = FakeLLM(script=script)
    return with_agent(db_path, index, fake, asking(*messages_to_send))


# --- What a run records ------------------------------------------------------


def test_run_is_recorded_as_steps_model_calls_and_tool_calls(
    traced, synthetic_db_path, fake_policy_index
):
    exporter = traced()
    script = [[("get_order_status", {"order_ref": "o_day14"})], "Teslim edildi."]

    support_run(synthetic_db_path, fake_policy_index, script, "o_day14 nerede?")

    kinds = {
        span.attributes.get(tracing.SPAN_KIND) for span in exporter.get_finished_spans()
    }
    assert {"CHAIN", "LLM", "TOOL"} <= kinds
    assert [span.attributes["tool.name"] for span in tool_spans(exporter)] == [
        "get_order_status"
    ]
    # One trace for the whole run.
    assert len({span.context.trace_id for span in exporter.get_finished_spans()}) == 1


def test_rule_decision_is_on_the_tool_span(
    traced, synthetic_db_path, fake_policy_index
):
    exporter = traced()
    script = [
        [("check_return_eligibility", {"order_ref": "o_day14", "reason": "damaged"})],
        "Uygun.",
    ]

    support_run(synthetic_db_path, fake_policy_index, script, "o_day14 hasarlı geldi")

    attributes = tool_spans(exporter)[0].attributes
    assert attributes["marketdesk.decision"] == "ELIGIBLE"
    assert attributes["marketdesk.rule"] == "R7"
    assert attributes["marketdesk.request_status"] == "PENDING_REVIEW"


def test_refused_write_is_on_the_tool_span(
    traced, synthetic_db_path, fake_policy_index
):
    exporter = traced()
    script = [[("create_return_request", RETURN)], "Onayınız istenecek."]

    support_run(synthetic_db_path, fake_policy_index, script, "o_day14 iade")

    assert tool_spans(exporter)[0].attributes["marketdesk.error"] == (
        "APPROVAL_REQUIRED"
    )


def test_approval_and_decline_are_spans_of_their_own(
    traced, synthetic_db_path, fake_policy_index
):
    exporter = traced()

    async def scenario(agent):
        await agent.ask("o_day14 hasarlı geldi, iade istiyorum")
        await agent.approve()
        await agent.decline()

    fake = FakeLLM(script=[[("create_return_request", RETURN)], "Onayınız istenecek."])
    with_agent(synthetic_db_path, fake_policy_index, fake, scenario)

    approved, declined = spans_named(exporter, "human approval")
    assert approved.attributes["marketdesk.answer"] == "approved"
    assert approved.attributes["marketdesk.written"] is True
    assert approved.attributes["marketdesk.request_status"] == "PENDING_REVIEW"
    assert approved.attributes["marketdesk.customer"] == hash_id(ALICE)
    assert declined.attributes["marketdesk.answer"] == "declined"
    assert declined.attributes["marketdesk.written"] is False


def ops_run(db_path, script, question):
    import asyncio

    agent = OpsAgent(db_path, FakeLLM(script=script))
    try:
        return asyncio.run(agent.ask(question))
    finally:
        agent.close()


def test_sql_check_is_on_the_tool_span(traced, synthetic_db_path):
    exporter = traced()
    script = [
        [("run_sql", {"query": "DROP TABLE orders"})],
        [("run_sql", {"query": "SELECT COUNT(*) FROM v_orders"})],
        "29 sipariş.",
    ]

    ops_run(synthetic_db_path, script, "Kaç sipariş var?")

    refused, passed = (span.attributes for span in tool_spans(exporter))
    assert refused["marketdesk.sql_check"] == "SQL_REJECTED"
    assert refused["marketdesk.reason"]
    assert passed["marketdesk.sql_check"] == "passed"


# --- Nothing personal or secret leaves ---------------------------------------


def test_trace_of_a_run_holds_no_raw_id_city_or_zip(
    traced, secrets, synthetic_db_path, fake_policy_index
):
    exporter = traced()
    message = (
        f"{RAW_ID} siparişim nerede? Sao Paulo, 01310. "
        "E-posta ayse@example.com, telefon 0532 123 45 67."
    )
    script = [[("get_order_status", {"order_ref": RAW_ID})], f"{RAW_ID} bulunamadı."]

    support_run(synthetic_db_path, fake_policy_index, script, message)

    text = dump(exporter)
    assert RAW_ID_PATTERN.findall(text) == []
    # The customer's id is not put into a span by the system either.
    assert ALICE not in text
    for personal in ("sao paulo", "01310", "ayse@example.com", "0532 123 45 67"):
        assert personal not in text.lower()
    # The run itself is still there.
    assert "get_order_status" in text


def test_no_secret_is_in_any_span(traced, secrets):
    exporter = traced()

    with tracing.span("probe", note=f"key {API_KEY} and {HASH_KEY}") as current:
        current.add_event("called", {"header": f"Bearer {API_KEY}"})
        current.set_attribute("list", [API_KEY, "other"])

    text = dump(exporter)
    assert API_KEY not in text
    assert HASH_KEY not in text
    assert text.count(tracing.SECRET_MASK) == 4


def test_key_made_for_the_process_is_not_in_any_span(traced, monkeypatch):
    monkeypatch.delenv(HASH_KEY_VARIABLE, raising=False)
    exporter = traced()

    with tracing.span("probe", note=f"id {RAW_ID}"):
        pass

    text = dump(exporter)
    assert tracing.hash_key() not in text
    assert hash_id(RAW_ID) in text


def test_raw_id_becomes_its_keyed_hash(secrets):
    cleaned = tracing.scrub(f"order {RAW_ID} and {RAW_ID.upper()}")

    assert cleaned == f"order {hash_id(RAW_ID)} and {hash_id(RAW_ID)}"


def test_personal_values_of_a_session_are_masked_once_registered(monkeypatch):
    monkeypatch.setattr(tracing, "_personal_values", {})
    text = "Teslimat adresi Curitiba, 80010."

    before = tracing.scrub(text)
    tracing.register_personal_values({"curitiba": "[city]", "80010": "[zip]"})

    assert before == text
    assert tracing.scrub(text) == "Teslimat adresi [city], [zip]."


def test_span_name_status_and_events_are_cleaned_too(traced, secrets):
    exporter = traced()

    with (
        pytest.raises(RuntimeError),
        tracing.span(f"lookup {RAW_ID}") as current,
    ):
        current.add_event(f"event {RAW_ID}", {"order": RAW_ID})
        raise RuntimeError(f"no order {RAW_ID}")

    (exported,) = exporter.get_finished_spans()
    assert exported.name == f"lookup {hash_id(RAW_ID)}"
    assert RAW_ID_PATTERN.findall(exported.to_json()) == []
    assert hash_id(RAW_ID) in exported.status.description


def test_masking_exporter_passes_on_what_the_inner_exporter_answers():
    inner = InMemorySpanExporter()

    assert tracing.MaskingExporter(inner).export([]) == SpanExportResult.SUCCESS


# --- Targets ------------------------------------------------------------------


def test_off_records_nothing(synthetic_db_path, fake_policy_index):
    assert tracing.setup_tracing("off") is None

    with tracing.span("probe", note="x") as current:
        assert current is None
    script = [[("get_order_status", {"order_ref": "o_day14"})], "Teslim edildi."]
    reply = support_run(synthetic_db_path, fake_policy_index, script, "o_day14?")

    assert reply


def test_tracing_is_off_unless_the_environment_says_otherwise(monkeypatch):
    monkeypatch.delenv("TRACING_TARGET", raising=False)
    assert importlib.reload(config).TRACING_TARGET == "off"

    monkeypatch.setenv("TRACING_TARGET", "langfuse")
    assert importlib.reload(config).TRACING_TARGET == "langfuse"

    monkeypatch.delenv("TRACING_TARGET")
    importlib.reload(config)


def test_only_a_local_target_counts_as_local():
    assert not tracing.is_hosted("phoenix")
    assert tracing.is_hosted("langfuse")
    assert tracing.is_hosted("anything else")


def test_hosted_target_gets_no_message_text(
    traced, synthetic_db_path, fake_policy_index
):
    exporter = traced("langfuse")
    script = [[("get_order_status", {"order_ref": "o_day14"})], "Gizli cevap metni."]

    support_run(synthetic_db_path, fake_policy_index, script, "Gizli soru metni")

    text = dump(exporter)
    assert "Gizli soru metni" not in text
    assert "Gizli cevap metni" not in text
    # Not the tool's arguments or its whole answer either; the order status
    # arrives only as the project's own attribute.
    assert "o_day14" not in text
    assert "output.value" not in text
    assert "input.value" not in text
    # Steps and tool names still arrive.
    assert "get_order_status" in text


def test_hosted_target_gets_only_allowed_attributes(
    traced, synthetic_db_path, fake_policy_index
):
    exporter = traced("langfuse")
    script = [[("get_order_status", {"order_ref": "o_day14"})], "Teslim edildi."]

    support_run(synthetic_db_path, fake_policy_index, script, "o_day14 nerede?")

    for span in exporter.get_finished_spans():
        for key in span.attributes:
            assert key in tracing.HOSTED_ATTRIBUTES or key.startswith(
                tracing.OWN_PREFIX
            ), key


def test_hosted_target_still_gets_the_rule_decision(
    traced, synthetic_db_path, fake_policy_index
):
    exporter = traced("langfuse")
    script = [
        [("check_return_eligibility", {"order_ref": "o_day14", "reason": "damaged"})],
        "Uygun.",
    ]

    support_run(synthetic_db_path, fake_policy_index, script, "o_day14 hasarlı geldi")

    attributes = tool_spans(exporter)[0].attributes
    assert attributes["tool.name"] == "check_return_eligibility"
    assert attributes["marketdesk.decision"] == "ELIGIBLE"
    assert attributes["marketdesk.rule"] == "R7"


def test_hosted_target_gets_no_event_detail_or_error_text(traced):
    exporter = traced("langfuse")

    with pytest.raises(RuntimeError), tracing.span("lookup") as current:
        current.add_event("note", {"text": "Gizli olay metni"})
        raise RuntimeError("Gizli hata metni")

    (exported,) = exporter.get_finished_spans()
    assert "Gizli" not in exported.to_json()
    assert not exported.status.description


def test_local_target_gets_the_masked_text(
    traced, synthetic_db_path, fake_policy_index
):
    exporter = traced("phoenix")
    script = ["Acik cevap metni."]

    support_run(synthetic_db_path, fake_policy_index, script, "Acik soru metni")

    text = dump(exporter)
    assert "Acik soru metni" in text
    assert "Acik cevap metni" in text


def test_unknown_target_is_refused():
    with pytest.raises(ValueError, match="unknown tracing target"):
        tracing.target_settings("somewhere")


def test_phoenix_is_the_local_container_and_needs_no_key():
    endpoint, headers = tracing.target_settings("phoenix")

    assert endpoint == "http://phoenix:6006/v1/traces"
    assert headers == {}
    assert isinstance(tracing.target_exporter("phoenix"), SpanExporter)


def test_langfuse_is_signed_in_to_with_the_keys(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    endpoint, headers = tracing.target_settings("langfuse")

    assert endpoint == config.TRACING_LANGFUSE_ENDPOINT
    # base64 of "pk-test:sk-test"
    assert headers == {"Authorization": "Basic cGstdGVzdDpzay10ZXN0"}


# --- Cost estimate -----------------------------------------------------------


def test_cost_is_estimated_from_the_token_counts(monkeypatch):
    monkeypatch.setattr(config, "LLM_PRICE_INPUT_PER_MTOK", 0.30)
    monkeypatch.setattr(config, "LLM_PRICE_OUTPUT_PER_MTOK", 2.50)
    attributes = {tracing.INPUT_TOKENS: 2000, tracing.OUTPUT_TOKENS: 100}

    assert tracing.estimated_cost(attributes) == pytest.approx(0.00085)


def test_no_cost_without_tokens_or_without_a_price(monkeypatch):
    assert tracing.estimated_cost({}) is None

    monkeypatch.setattr(config, "LLM_PRICE_INPUT_PER_MTOK", None)

    assert tracing.estimated_cost({tracing.INPUT_TOKENS: 10}) is None


def test_cost_is_written_on_a_span_that_has_token_counts(traced, monkeypatch):
    monkeypatch.setattr(config, "LLM_PRICE_INPUT_PER_MTOK", 0.30)
    monkeypatch.setattr(config, "LLM_PRICE_OUTPUT_PER_MTOK", 2.50)
    exporter = traced()

    with tracing.span("model call") as current:
        current.set_attribute(tracing.INPUT_TOKENS, 1_000_000)
        current.set_attribute(tracing.OUTPUT_TOKENS, 0)

    (exported,) = exporter.get_finished_spans()
    assert exported.attributes[tracing.COST_ATTRIBUTE] == pytest.approx(0.30)


def test_no_cost_is_written_while_no_price_is_set(traced, monkeypatch):
    monkeypatch.setattr(config, "LLM_PRICE_INPUT_PER_MTOK", None)
    exporter = traced()

    with tracing.span("model call") as current:
        current.set_attribute(tracing.INPUT_TOKENS, 1000)

    (exported,) = exporter.get_finished_spans()
    assert tracing.COST_ATTRIBUTE not in exported.attributes


# --- Policy search ------------------------------------------------------

POLICY_QUESTION = "iade süresi kaç gün"


def attribute_values(exporter) -> list:
    """Every attribute value of every span, as exported.

    Not to_json(): it escapes Turkish letters, and a search in it would not
    find Turkish text that is there.
    """
    return [
        value
        for span in exporter.get_finished_spans()
        for value in span.attributes.values()
    ]


def span_kinds(exporter) -> set:
    return {
        span.attributes.get(tracing.SPAN_KIND) for span in exporter.get_finished_spans()
    }


def is_vector(value) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) > 0
        and all(isinstance(item, float) for item in value)
    )


def test_policy_search_is_recorded_as_embedding_and_retrieval_steps(
    traced, fake_policy_index
):
    exporter = traced("phoenix")

    results = fake_policy_index.search(POLICY_QUESTION, 3)

    assert {"EMBEDDING", "RETRIEVER"} <= span_kinds(exporter)
    text = "\n".join(str(value) for value in attribute_values(exporter))
    assert POLICY_QUESTION in text
    assert results[0]["text"] in text


def test_hosted_target_gets_no_text_or_vector_of_a_policy_search(
    traced, fake_policy_index
):
    exporter = traced("langfuse")

    results = fake_policy_index.search(POLICY_QUESTION, 3)

    # The steps still arrive, as kinds only.
    assert {"EMBEDDING", "RETRIEVER"} <= span_kinds(exporter)
    for span in exporter.get_finished_spans():
        for key in span.attributes:
            assert key in tracing.HOSTED_ATTRIBUTES or key.startswith(
                tracing.OWN_PREFIX
            ), key
    values = attribute_values(exporter)
    assert not any(is_vector(value) for value in values)
    text = "\n".join(str(value) for value in values)
    assert POLICY_QUESTION not in text
    for result in results:
        assert result["text"] not in text


def test_local_target_masks_an_id_in_a_policy_search(
    traced, fake_policy_index, secrets
):
    exporter = traced("phoenix")

    fake_policy_index.search(f"{RAW_ID} siparişinin iade süresi", 3)

    text = "\n".join(str(value) for value in attribute_values(exporter))
    assert RAW_ID not in text
    assert hash_id(RAW_ID) in text


def test_no_target_gets_an_embedding_vector(traced, fake_policy_index):
    exporter = traced("phoenix")

    fake_policy_index.search(POLICY_QUESTION, 3)

    vectors = [
        value
        for span in exporter.get_finished_spans()
        for key, value in span.attributes.items()
        if key.endswith("embedding.vector")
    ]
    # The attribute is there, so the check would see a vector if one came.
    assert vectors
    assert not any(is_vector(value) for value in vectors)
