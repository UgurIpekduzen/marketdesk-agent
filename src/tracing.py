"""Tracing: every agent run as a tree of spans, with personal data masked.

setup_tracing() switches it on for the target chosen in config.py:

- "off": nothing is recorded or sent;
- "phoenix": to the local Phoenix container;
- "langfuse": to Langfuse Cloud, with only the attributes on an allowlist.

The spans of the agent steps, model calls and tool calls come from the
OpenInference instrumentation of LlamaIndex. The project adds what
matters here: on a tool span the rule engine's decision or the outcome of
the SQL check, read from the tool's answer, and a span of its own for the
person's answer to an approval request. The instrumentation does not make
its spans the current context, so that span starts a trace of its own.

Embedding vectors are not recorded at all. Whatever the target, every
span passes MaskingExporter on its way out. Raw ids become short keyed
hashes, e-mail addresses, phone numbers and the known personal values of
the sessions are masked, and the values of the secret environment
variables are removed. A hosted target then gets only
the attributes on HOSTED_ATTRIBUTES and the project's own: no message,
tool argument or tool result, no event detail and no error text. An
attribute nobody has thought about stays in this process.
"""

import base64
import json
import logging
import os
from collections.abc import Mapping, Sequence
from contextlib import contextmanager

from openinference.instrumentation import TraceConfig
from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import Status

import config
from src.guardrails.outbound import Redactor
from src.guardrails.pii import HASH_KEY_VARIABLE, RAW_ID_PATTERN, hash_id, hash_key

logger = logging.getLogger(__name__)

SERVICE_NAME = "marketdesk"
TRACER_NAME = "marketdesk"
SECRET_MASK = "[secret]"
# Environment variables whose values must never appear in a span.
SECRET_VARIABLES = (
    "GEMINI_API_KEY_FREE",
    "GEMINI_API_KEY_PAID",
    "GROQ_API_KEY",
    "HF_TOKEN",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    HASH_KEY_VARIABLE,
)
# OpenInference attribute names for the tokens of one model call.
INPUT_TOKENS = "llm.token_count.prompt"
OUTPUT_TOKENS = "llm.token_count.completion"
SPAN_KIND = "openinference.span.kind"
# Prefix of the attributes the project adds itself.
OWN_PREFIX = "marketdesk."
COST_ATTRIBUTE = f"{OWN_PREFIX}cost_usd_estimate"
# All a hosted target receives of a span, besides the project's own
# attributes: what kind of step it was, which tool or model, and the tokens.
HOSTED_ATTRIBUTES = frozenset(
    {
        SPAN_KIND,
        "tool.name",
        "llm.model_name",
        "llm.provider",
        "llm.system",
        INPUT_TOKENS,
        OUTPUT_TOKENS,
        "llm.token_count.total",
    }
)

# Personal values of the sessions seen by this process (city, zip code
# prefix), with the mask for each. Sessions add to it when they start.
_personal_values: dict[str, str] = {}
# Set while tracing is on.
_provider: TracerProvider | None = None


def register_personal_values(values: Mapping[str, str]) -> None:
    """Have the values of a session masked in every span from now on."""
    _personal_values.update(values)


def secret_values() -> list[str]:
    values = [os.environ.get(name, "") for name in SECRET_VARIABLES]
    # The key in use, also when it was made for this process.
    values.append(hash_key())
    return [value for value in values if value]


def scrub(text: str) -> str:
    """A text as it may leave the process."""
    for secret in secret_values():
        text = text.replace(secret, SECRET_MASK)
    text = RAW_ID_PATTERN.sub(lambda match: hash_id(match.group().lower()), text)
    # Ids are hashes by now; the redactor masks what is left.
    return Redactor(known_values=_personal_values).redact(text)[0]


def scrub_value(value: object) -> object:
    """Clean a span attribute value: a text or a sequence of values."""
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, bytes):
        return scrub(value.decode(errors="replace"))
    if isinstance(value, Sequence):
        return [scrub_value(item) for item in value]
    return value


def estimated_cost(attributes: Mapping) -> float | None:
    """What a model call would cost at the list price, in USD."""
    prices = (config.LLM_PRICE_INPUT_PER_MTOK, config.LLM_PRICE_OUTPUT_PER_MTOK)
    if INPUT_TOKENS not in attributes or None in prices:
        return None
    tokens = (attributes[INPUT_TOKENS], attributes.get(OUTPUT_TOKENS, 0))
    return sum(count * price for count, price in zip(tokens, prices)) / 1_000_000


def scrub_attributes(attributes: Mapping | None) -> dict:
    return {
        scrub(str(key)): scrub_value(value) for key, value in (attributes or {}).items()
    }


def tool_result(attributes: Mapping) -> dict | None:
    """The dict a tool answered with, read from the attributes of its span."""
    try:
        output = json.loads(attributes.get("output.value", ""))
        result = json.loads(output["blocks"][0]["text"])
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return result if isinstance(result, dict) else None


def own_attributes(attributes: Mapping) -> dict:
    """What the project wants to see on a tool span at a glance.

    The rule engine's decision and rule, the status a return request would
    get, an error code with its reason, and for free SQL whether the query
    passed the check.
    """
    if attributes.get(SPAN_KIND) != "TOOL":
        return {}
    result = tool_result(attributes)
    if result is None:
        return {}
    found = {
        "decision": result.get("decision"),
        "rule": result.get("rule"),
        "request_status": result.get("request_status") or result.get("status"),
        "error": result.get("error"),
        "reason": result.get("reason"),
    }
    if attributes.get("tool.name") == "run_sql":
        found["sql_check"] = result.get("error", "passed")
    return {
        f"{OWN_PREFIX}{key}": value
        for key, value in found.items()
        if isinstance(value, str)
    }


def allowed_for_hosted(attributes: Mapping) -> dict:
    """The attributes a hosted target may receive."""
    return {
        key: value
        for key, value in attributes.items()
        if key in HOSTED_ATTRIBUTES or key.startswith(OWN_PREFIX)
    }


def masked(span: ReadableSpan, hosted: bool = False) -> ReadableSpan:
    """A copy of a finished span with every text cleaned.

    For a hosted target only the allowed attributes are kept, events lose
    their details and the status its description. The project's own
    attributes are read from the full span first, so the decision of a
    tool still arrives when its answer does not.
    """
    attributes = scrub_attributes(
        {**span.attributes, **own_attributes(span.attributes)}
    )
    cost = estimated_cost(attributes)
    if cost is not None:
        attributes[COST_ATTRIBUTE] = round(cost, 8)
    if hosted:
        attributes = allowed_for_hosted(attributes)
    status = span.status
    if hosted:
        status = Status(status.status_code)
    elif status.description:
        status = Status(status.status_code, scrub(status.description))
    return ReadableSpan(
        name=scrub(span.name),
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=attributes,
        events=[
            Event(
                scrub(event.name),
                {} if hosted else scrub_attributes(event.attributes),
                event.timestamp,
            )
            for event in span.events
        ],
        links=span.links,
        kind=span.kind,
        status=status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class MaskingExporter(SpanExporter):
    """Cleans every span, then hands it to the real exporter."""

    def __init__(self, inner: SpanExporter, hosted: bool = False) -> None:
        self._inner = inner
        self._hosted = hosted

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([masked(span, self._hosted) for span in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def target_settings(target: str) -> tuple[str, dict[str, str]]:
    """Where a target receives spans, and the headers it asks for."""
    if target == "phoenix":
        return config.TRACING_PHOENIX_ENDPOINT, {}
    if target == "langfuse":
        keys = (
            f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}"
        )
        signed = base64.b64encode(keys.encode()).decode()
        return config.langfuse_endpoint(config.LANGFUSE_BASE_URL), {
            "Authorization": f"Basic {signed}"
        }
    raise ValueError(f"unknown tracing target: {target!r}")


def target_exporter(target: str) -> SpanExporter:
    """The exporter that sends spans to a target."""
    # Imported here: only a run that sends spans needs the HTTP exporter.
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )

    endpoint, headers = target_settings(target)
    return OTLPSpanExporter(endpoint=endpoint, headers=headers)


def is_hosted(target: str) -> bool:
    """Whether a target runs outside this machine."""
    return target != "phoenix"


def setup_tracing(
    target: str | None = None,
    exporter: SpanExporter | None = None,
    batch: bool = True,
) -> TracerProvider | None:
    """Switch tracing on for the configured target; None when it is off.

    A test passes its own exporter and batch=False, to read the spans as
    soon as they end. The masking exporter is always in front.
    """
    target = config.TRACING_TARGET if target is None else target
    if target == "off":
        return None
    exporter = MaskingExporter(
        exporter or target_exporter(target), hosted=is_hosted(target)
    )
    provider = TracerProvider(resource=Resource({"service.name": SERVICE_NAME}))
    processor = BatchSpanProcessor if batch else SimpleSpanProcessor
    provider.add_span_processor(processor(exporter))
    # The instrumentation records everything but embedding vectors; what may
    # leave is decided in MaskingExporter, after the project's own attributes
    # are read. A vector is made from the unmasked text, which masking cannot
    # reach, and nobody reads one when debugging.
    LlamaIndexInstrumentor().instrument(
        tracer_provider=provider, config=TraceConfig(hide_embedding_vectors=True)
    )
    global _provider
    _provider = provider
    logger.info("tracing is on, target=%s", target)
    return provider


def shutdown_tracing() -> None:
    """Send what is left and switch tracing off again."""
    global _provider
    if _provider is None:
        return
    LlamaIndexInstrumentor().uninstrument()
    _provider.shutdown()
    _provider = None


@contextmanager
def span(name: str, **attributes: object):
    """A span of the project's own.

    Does nothing when tracing is off. Attribute names get the project's
    prefix; None values are left out.
    """
    if _provider is None:
        yield None
        return
    tracer = _provider.get_tracer(TRACER_NAME)
    with tracer.start_as_current_span(name) as current:
        annotate(current, **attributes)
        yield current


def annotate(current: trace.Span | None, **attributes: object) -> None:
    """Put the project's attributes on a span."""
    if current is None:
        return
    for key, value in attributes.items():
        if value is not None:
            current.set_attribute(f"{OWN_PREFIX}{key}", value)


def mark(**attributes: object) -> None:
    """Put the project's attributes on the span that is open now, if any."""
    if _provider is None:
        return
    current = trace.get_current_span()
    if current.is_recording():
        annotate(current, **attributes)
