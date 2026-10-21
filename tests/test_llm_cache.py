"""Tests for the model response cache, with a stand-in model behind it."""

import asyncio

import pytest
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context
from pydantic import Field

import config
from eval import run_eval
from eval.llm_cache import (
    CachedLLM,
    DailyQuotaUsedUp,
    LiveCallLimitReached,
    NoPaidCredit,
    daily_quota_message,
    is_daily_quota,
    is_out_of_credit,
    is_transient,
)
from src.agents.runner import run_agent
from src.guardrails.guarded_llm import GuardedLLM
from src.guardrails.outbound import Redactor
from tests.fakes import FakeLLM
from tests.test_run_eval import (
    GOOD_SCRIPT,
    OPS_EXAMPLE,
    POLICY_EXAMPLE,
    SUPPORT_EXAMPLE,
)

RAW_ID = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"


def user(text):
    return ChatMessage(role=MessageRole.USER, content=text)


def chat(llm, text, **kwargs):
    return asyncio.run(llm.achat([user(text)], **kwargs))


@pytest.fixture
def fake():
    return FakeLLM(script=["bir", "iki", "üç", "dört"])


@pytest.fixture
def cached(fake, tmp_path):
    return CachedLLM(inner=fake, cache_dir=tmp_path / "cache")


def test_first_call_goes_to_the_model_and_the_second_comes_from_the_cache(cached, fake):
    first = chat(cached, "merhaba")
    second = chat(cached, "merhaba")

    assert first.message.content == second.message.content == "bir"
    assert len(fake.requests) == 1
    assert (cached.live_calls, cached.hits) == (1, 1)


def test_another_question_is_another_entry(cached, fake):
    chat(cached, "merhaba")
    answer = chat(cached, "selam")

    assert answer.message.content == "iki"
    assert len(fake.requests) == 2


def test_cache_survives_a_new_object(fake, tmp_path):
    chat(CachedLLM(inner=fake, cache_dir=tmp_path), "merhaba")

    again = CachedLLM(inner=fake, cache_dir=tmp_path)
    answer = chat(again, "merhaba")

    assert answer.message.content == "bir"
    assert len(fake.requests) == 1
    assert again.hits == 1


def test_other_tools_or_settings_are_another_entry(cached, fake):
    chat(cached, "merhaba")
    chat(cached, "merhaba", tools=[{"function": {"name": "get_order_status"}}])

    assert len(fake.requests) == 2


class SetFake(FakeLLM):
    """A stand-in model built with extra settings, as a Groq model can be."""

    additional_kwargs: dict = Field(default_factory=dict)


def test_settings_are_part_of_the_entry_and_none_leave_it_as_it_was(tmp_path):
    model = SetFake(script=["bir", "iki", "üç"])
    cached = CachedLLM(inner=model, cache_dir=tmp_path)

    chat(cached, "merhaba")
    model.additional_kwargs = {"reasoning_effort": "low"}
    chat(cached, "merhaba")
    # Empty settings count as none: the first entry is found again, as the
    # entries of every model built without settings are.
    model.additional_kwargs = {}
    chat(cached, "merhaba")

    assert len(model.requests) == 2
    assert cached.hits == 1


def test_another_temperature_is_another_entry(cached, fake, monkeypatch):
    chat(cached, "merhaba")
    monkeypatch.setattr(config, "LLM_TEMPERATURE", 0.7)
    chat(cached, "merhaba")

    assert len(fake.requests) == 2


def test_tokens_and_time_are_kept_with_the_entry(fake, tmp_path):
    class CountingFake(FakeLLM):
        def _answer(self, messages, **kwargs):
            response = super()._answer(messages, **kwargs)
            response.raw = {
                "usage_metadata": {
                    "prompt_token_count": 120,
                    "candidates_token_count": 7,
                }
            }
            return response

    cached = CachedLLM(inner=CountingFake(script=["bir"]), cache_dir=tmp_path)

    live = chat(cached, "merhaba")
    seconds_after_live = cached.seconds
    from_cache = chat(cached, "merhaba")

    usage = {"prompt_token_count": 120, "candidates_token_count": 7}
    assert live.raw == from_cache.raw == {"usage_metadata": usage}
    # The cached answer reports the time the real call took, again.
    assert cached.seconds == pytest.approx(seconds_after_live * 2)


def test_tool_calls_come_back_from_the_cache(tmp_path):
    async def echo(text: str) -> str:
        """Return the text."""
        return text

    def run(fake):
        async def scenario():
            agent = FunctionAgent(
                name="trial",
                tools=[FunctionTool.from_defaults(async_fn=echo)],
                llm=CachedLLM(inner=fake, cache_dir=tmp_path),
                system_prompt="system",
            )
            return await run_agent(agent, Context(agent), "merhaba")

        return asyncio.run(scenario())

    first_model = FakeLLM(script=[[("echo", {"text": "a"})], "bitti"])
    second_model = FakeLLM(script=["cache was not used"])

    live_text, live_log = run(first_model)
    cached_text, cached_log = run(second_model)

    assert live_text == cached_text == "bitti"
    assert live_log.tool_calls == cached_log.tool_calls == ["echo"]
    assert second_model.requests == []


def test_what_is_cached_is_what_the_guard_let_through(fake, tmp_path):
    cached = CachedLLM(inner=fake, cache_dir=tmp_path)
    guarded = GuardedLLM(inner=cached, redactor=Redactor())

    asyncio.run(guarded.achat([user(f"{RAW_ID} nerede?")]))

    stored = "".join(path.read_text(encoding="utf-8") for path in tmp_path.iterdir())
    assert RAW_ID not in stored
    assert RAW_ID not in fake.sent_text()
    assert "[id] nerede?" in fake.sent_text()


def test_calls_that_would_go_round_the_cache_are_refused(cached):
    with pytest.raises(NotImplementedError):
        cached.chat([user("merhaba")])
    with pytest.raises(NotImplementedError):
        cached.complete("merhaba")


# --- A busy provider is asked again ----------------------------------------


class BusyThenFine(FakeLLM):
    """Fails with the given errors, one per call, then answers."""

    failures: list = Field(default_factory=list)

    async def achat(self, messages, **kwargs):
        if self.failures:
            raise self.failures.pop(0)
        return await super().achat(messages, **kwargs)


def busy(tmp_path, failures, **options):
    inner = BusyThenFine(script=["tamam"], failures=list(failures))
    return CachedLLM(
        inner=inner, cache_dir=tmp_path / "cache", retry_seconds=0, **options
    )


def test_busy_provider_is_asked_again_until_it_answers(tmp_path, caplog):
    errors = [
        RuntimeError("503 UNAVAILABLE. high demand"),
        RuntimeError("429 RESOURCE_EXHAUSTED"),
    ]
    cached = busy(tmp_path, errors)

    with caplog.at_level("WARNING"):
        response = chat(cached, "merhaba")

    assert response.message.content == "tamam"
    assert cached.live_calls == 1
    assert caplog.text.count("provider is busy") == 2


def test_provider_that_stays_busy_fails_after_the_last_try(tmp_path):
    cached = busy(tmp_path, [RuntimeError("503 UNAVAILABLE")] * 3, retries=2)

    with pytest.raises(RuntimeError, match="503"):
        chat(cached, "merhaba")

    assert cached.live_calls == 0


def test_other_errors_are_not_retried(tmp_path):
    cached = busy(tmp_path, [ValueError("400 INVALID_ARGUMENT"), RuntimeError("503")])

    with pytest.raises(ValueError, match="400"):
        chat(cached, "merhaba")

    # The second error was never reached: there was no second call.
    assert len(cached.inner.failures) == 1


def test_waiting_is_not_counted_as_model_time(tmp_path):
    cached = busy(tmp_path, [RuntimeError("503 UNAVAILABLE")])
    cached.retry_seconds = 0.2

    chat(cached, "merhaba")

    assert cached.seconds < 0.2


# --- The quota of the day ----------------------------------------------------

# What Gemini answers when the free quota of the day or of the minute is gone
# (shape of the 429 of the Gemini API; the quota ids name the period).
DAILY_ERROR = (
    "429 RESOURCE_EXHAUSTED. You exceeded your current quota. Quota exceeded "
    "for metric: generativelanguage.googleapis.com/generate_content_free_tier_"
    "requests, limit: 500, model: gemini-3.5-flash-lite. quotaId: "
    "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
)
# The answer of the paid key with no prepaid credit left, as it came.
NO_CREDIT_ERROR = (
    "402 RESOURCE_EXHAUSTED. {'error': {'code': 402, 'message': 'Your "
    "prepayment credits are depleted. Please go to AI Studio at "
    "https://ai.studio/projects to manage your project and billing.', "
    "'status': 'RESOURCE_EXHAUSTED'}}"
)
MINUTE_ERROR = (
    "429 RESOURCE_EXHAUSTED. You exceeded your current quota. quotaId: "
    "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
)
EXAMPLES = [SUPPORT_EXAMPLE, OPS_EXAMPLE, POLICY_EXAMPLE]


# --- Which error is which ---------------------------------------------------


def test_the_daily_quota_is_told_from_the_minute_limit():
    assert is_daily_quota(RuntimeError(DAILY_ERROR))
    assert not is_daily_quota(RuntimeError(MINUTE_ERROR))
    # The minute limit is waited out; the day's is not.
    assert is_transient(RuntimeError(MINUTE_ERROR))
    assert not is_transient(RuntimeError(DAILY_ERROR))


class Failing(FakeLLM):
    """A model that answers like the script until it has given `answers`
    answers, then fails with `error`."""

    answers: int = 0
    error: str = DAILY_ERROR
    calls: int = 0

    async def achat(self, messages, **kwargs):
        self.calls += 1
        if self.calls > self.answers:
            raise RuntimeError(self.error)
        return await super().achat(messages, **kwargs)


def ask_once(llm):
    return asyncio.run(llm.achat([ChatMessage(role="user", content="Merhaba")]))


class GoogleGenAI(Failing):
    """Stands in for Gemini's model class: its message points to --paid."""


def test_the_daily_quota_stops_at_once_without_waiting(tmp_path):
    inner = GoogleGenAI(script=["x"], answers=0)
    llm = CachedLLM(inner=inner, cache_dir=tmp_path, retry_seconds=3600)

    with pytest.raises(DailyQuotaUsedUp, match="--paid"):
        ask_once(llm)

    assert inner.calls == 1


def test_no_prepaid_credit_stops_at_once_without_waiting(tmp_path):
    inner = Failing(script=["x"], answers=0, error=NO_CREDIT_ERROR)
    llm = CachedLLM(inner=inner, cache_dir=tmp_path, retry_seconds=3600)

    with pytest.raises(NoPaidCredit, match="Add credit"):
        ask_once(llm)

    assert inner.calls == 1


def test_no_prepaid_credit_is_told_apart_from_the_quotas():
    assert is_out_of_credit(RuntimeError(NO_CREDIT_ERROR))
    assert not is_transient(RuntimeError(NO_CREDIT_ERROR))
    assert not is_daily_quota(RuntimeError(NO_CREDIT_ERROR))
    assert not is_out_of_credit(RuntimeError(MINUTE_ERROR))
    assert not is_out_of_credit(RuntimeError(DAILY_ERROR))


# Groq's answer once the tokens of the day are used up, as its documentation
# shows it.
GROQ_DAY_ERROR = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
    "`openai/gpt-oss-120b` in organization `org_x` service tier `on_demand` on "
    "tokens per day (TPD): Limit 200000, Used 199980, Requested 1200. Please try "
    "again in 8m38.4s.', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
)


class Groq(Failing):
    """Stands in for Groq's model class: the message names the provider."""


def test_the_daily_limit_of_another_provider_says_to_wait_not_to_pay(tmp_path):
    inner = Groq(script=["x"], answers=0, error=GROQ_DAY_ERROR)
    llm = CachedLLM(inner=inner, cache_dir=tmp_path, retry_seconds=3600)

    with pytest.raises(DailyQuotaUsedUp, match="tomorrow") as stop:
        ask_once(llm)

    assert "--paid" not in str(stop.value)
    assert inner.calls == 1


def test_only_gemini_is_told_to_go_on_with_the_paid_key():
    assert "--paid" in daily_quota_message("GoogleGenAI")
    assert "Groq" in daily_quota_message("Groq")
    assert "--paid" not in daily_quota_message("Groq")


def test_the_minute_limit_is_waited_out(tmp_path):
    inner = Failing(script=["x"], answers=0, error=MINUTE_ERROR)
    llm = CachedLLM(inner=inner, cache_dir=tmp_path, retries=2, retry_seconds=0)

    with pytest.raises(RuntimeError, match="PerMinute"):
        ask_once(llm)

    assert inner.calls == 3


def test_a_run_on_the_paid_key_stops_at_its_limit(tmp_path):
    llm = CachedLLM(
        inner=FakeLLM(script=["a", "b", "c"]), cache_dir=tmp_path, max_live_calls=2
    )
    asyncio.run(llm.achat([ChatMessage(role="user", content="1")]))
    asyncio.run(llm.achat([ChatMessage(role="user", content="2")]))

    with pytest.raises(LiveCallLimitReached):
        asyncio.run(llm.achat([ChatMessage(role="user", content="3")]))
    # A cached answer is still given: it costs nothing.
    asyncio.run(llm.achat([ChatMessage(role="user", content="1")]))


# --- Going on after the quota ran out -----------------------------------------


def comparable(rows):
    return [
        {
            key: value
            for key, value in row.items()
            if key not in ("seconds", "live_calls")
        }
        for row in rows
    ]


def test_a_run_cut_by_the_quota_and_finished_later_gives_the_same_results(
    synthetic_db_path, fake_policy_index, tmp_path
):
    def run(inner, cache_dir):
        llm = CachedLLM(inner=inner, cache_dir=cache_dir)
        return run_eval.run(
            EXAMPLES,
            synthetic_db_path,
            fake_policy_index,
            llm,
            report=lambda line: None,
        )

    straight = run(FakeLLM(script=list(GOOD_SCRIPT)), tmp_path / "straight")

    # The free quota runs out in the middle of the second example.
    with pytest.raises(DailyQuotaUsedUp):
        run(Failing(script=list(GOOD_SCRIPT), answers=5), tmp_path / "cut")
    # The same command again, now on the paid key: the answers so far come
    # from the cache, the rest live. The fresh model starts its script where
    # the first one stopped. It is of the same class, as the free and the
    # paid key are: the provider's class is part of the cache key.
    finished = run(Failing(script=list(GOOD_SCRIPT[5:]), answers=100), tmp_path / "cut")

    assert comparable(finished) == comparable(straight)
