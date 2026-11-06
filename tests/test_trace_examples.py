"""Tests for the example traces: every error kind the project marks is sent."""

import asyncio

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from scripts.trace_examples import run_examples
from src import tracing


@pytest.fixture
def exporter(monkeypatch):
    monkeypatch.setattr(tracing, "_personal_values", {})
    exporter = InMemorySpanExporter()
    tracing.setup_tracing("langfuse", exporter=exporter, batch=False)
    yield exporter
    tracing.shutdown_tracing()


def test_the_examples_hold_every_error_kind(
    exporter, synthetic_db_path, fake_policy_index
):
    asyncio.run(run_examples(synthetic_db_path, fake_policy_index))

    spans = exporter.get_finished_spans()
    errors = {span.attributes.get("marketdesk.error") for span in spans} - {None}
    answers = {span.attributes.get("marketdesk.answer") for span in spans} - {None}
    assert errors == {
        "ROUTER_REFUSED",
        "STEP_LIMIT",
        "TOOL_LIMIT",
        "QUOTA_EXCEEDED",
        "PROVIDER_BUSY",
        "SQL_REJECTED",
        "SQL_ERROR",
        "REPEATED_CALL",
        "NOT_FOUND",
        "APPROVAL_REQUIRED",
        "DUPLICATE_REQUEST",
    }
    assert answers == {"approved", "declined"}
