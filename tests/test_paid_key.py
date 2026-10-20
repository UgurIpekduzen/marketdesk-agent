"""Tests for the paid Gemini key of evaluation runs."""

from pathlib import Path

import pytest

import config
from src.guardrails import guarded_llm

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Recorder:
    """Stands in for the provider's model class and keeps the key it got."""

    def __init__(self, model, api_key, temperature):
        self.api_key = api_key


@pytest.fixture
def two_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY_FREE", "free-key")
    monkeypatch.setenv(config.PAID_KEY_VARIABLE, "paid-key")
    monkeypatch.setattr("llama_index.llms.google_genai.GoogleGenAI", Recorder)


# --- Which key ----------------------------------------------------------------


def test_the_free_key_is_used_unless_paid_is_asked_for(two_keys):
    assert guarded_llm.build_provider_llm().api_key == "free-key"
    assert guarded_llm.build_judge_provider_llm().api_key == "free-key"


def test_paid_uses_the_paid_key(two_keys):
    assert guarded_llm.build_provider_llm(paid=True).api_key == "paid-key"
    assert guarded_llm.build_judge_provider_llm(paid=True).api_key == "paid-key"


def test_the_paid_key_is_a_gemini_key(two_keys):
    with pytest.raises(ValueError, match="Gemini"):
        guarded_llm.build_provider_llm("groq", "some-model", paid=True)


def test_the_page_and_the_agents_never_ask_for_the_paid_key():
    """Only the evaluation may pass paid; the system itself never does."""
    files = [PROJECT_ROOT / "app.py", *sorted((PROJECT_ROOT / "src").rglob("*.py"))]
    for path in files:
        # The one place that reads the key, and the tracing, which names it
        # only to mask its value.
        if path.name in ("guarded_llm.py", "tracing.py"):
            continue
        text = path.read_text(encoding="utf-8")
        assert "paid=True" not in text, path
        assert "PAID_KEY_VARIABLE" not in text, path
        assert config.PAID_KEY_VARIABLE not in text, path
