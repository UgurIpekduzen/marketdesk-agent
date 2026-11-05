"""Tests for the judge: DeepEval's metrics on a stand-in model, no network.

The stand-in answers every prompt with the JSON the metric asks for, so
these tests show the wiring: every call goes through the project's guard,
and the scores come back in the shape the runner expects.
"""

import json

import pytest
from pydantic import BaseModel, ValidationError

from eval import judge as judge_module
from eval.judge import Judge, JudgeModel
from eval.llm_cache import CachedLLM
from src.i18n import Language
from tests.fakes import FakeLLM

RAW_ID = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"
# What the faithfulness metric asks for, in the order it asks.
TRUTHS = json.dumps({"truths": ["Vazgeçme iadesi 14 takvim günüdür."]})
CLAIMS = json.dumps({"claims": ["İade süresi 14 gündür.", "Para 3 günde döner."]})
VERDICTS = json.dumps(
    {"verdicts": [{"verdict": "yes"}, {"verdict": "no", "reason": "Politikada yok."}]}
)
REASON = json.dumps({"reason": "Bir iddia desteklenmiyor."})
G_EVAL = json.dumps({"score": 8, "reason": "Soruya cevap veriyor."})


def sent(fake: FakeLLM, call: int) -> str:
    return str(fake.requests[call]["messages"])


def test_deepeval_phoning_home_is_off():
    import os

    assert os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] == "YES"
    assert os.environ["DEEPEVAL_DISABLE_DOTENV"] == "1"


def test_judge_answers_through_the_guard():
    fake = FakeLLM(script=["tamam"])
    model = JudgeModel(fake)

    answer = model.generate(f"Sipariş {RAW_ID} hakkında karar ver.")

    assert answer == "tamam"
    assert model.calls == 1
    # The provider got the prompt with the id masked, and no tools.
    assert RAW_ID not in fake.sent_text()
    assert "[id]" in sent(fake, 0)
    assert fake.requests[0]["tools"] == []


class ScoreVerdict(BaseModel):
    score: int


class ReasonVerdict(BaseModel):
    reason: str


def test_judge_reads_fenced_json():
    model = JudgeModel(FakeLLM(script=['```json\n{"score": 7}\n```']))

    assert model.generate("puanla", schema=ScoreVerdict).score == 7


def test_non_json_is_asked_once_more():
    broken = '{"reason": "Cevap "14 gün" diyor."}'
    fake = FakeLLM(script=[broken, '{"reason": "Cevap 14 gün diyor."}'])
    model = JudgeModel(fake)

    assert (
        model.generate("puanla", schema=ReasonVerdict).reason == "Cevap 14 gün diyor."
    )
    assert model.calls == 2
    assert "not valid JSON" in sent(fake, 1)


def test_broken_answer_is_an_error():
    model = JudgeModel(FakeLLM(script=["{bozuk", "{yine bozuk"]))

    with pytest.raises(ValidationError):
        model.generate("puanla", schema=ReasonVerdict)


def test_judge_model_name_from_settings(monkeypatch):
    monkeypatch.setattr(judge_module.config, "JUDGE_MODEL", "some-judge")

    assert JudgeModel(FakeLLM()).get_model_name() == "some-judge"


def test_context_is_every_cited_section():
    context = judge_module.policy_context()

    assert len(context) == 28
    assert context[0].startswith("[")
    assert any("İade Politikası, Bölüm 2" in section for section in context)


def test_policy_answer_gets_two_scores():
    fake = FakeLLM(script=[TRUTHS, CLAIMS, VERDICTS, REASON, G_EVAL])
    judge = Judge(fake)

    scores = judge.policy_answer(
        "Kaç gün içinde iade edebilirim?", "14 gün; paranız 3 günde döner."
    )

    assert scores["faithfulness"] == pytest.approx(0.5)
    assert [claim["verdict"] for claim in scores["claims"]] == ["yes", "no"]
    assert scores["helpfulness"] == pytest.approx(0.8)
    assert scores["faithfulness_reason"]
    # Every call the metrics made went to the stand-in, through the model
    # the project handed over.
    assert judge.model.calls == len(fake.requests) == 5


def test_answer_is_checked_against_policy():
    fake = FakeLLM(script=[TRUTHS, CLAIMS, VERDICTS, REASON, G_EVAL])

    Judge(fake).policy_answer("Kaç gün?", "14 gün.")

    assert "İade Politikası, Bölüm 2" in fake.sent_text()
    assert "İptal Politikası, Bölüm 1" in fake.sent_text()


def test_text_narrowed_to_named_documents():
    fake = FakeLLM(script=[TRUTHS, CLAIMS, VERDICTS, REASON, G_EVAL])

    Judge(fake).policy_answer("Kaç gün?", "14 gün.", ["İade Politikası"])

    assert "İade Politikası, Bölüm 2" in fake.sent_text()
    assert "İptal Politikası, Bölüm 1" not in fake.sent_text()


def test_named_docs_hold_only_their_text():
    context = judge_module.policy_context(["İptal Politikası"])

    assert len(context) == 5
    assert all(section.startswith("[İptal Politikası, Bölüm") for section in context)


def test_ops_answer_gets_causal_score():
    fake = FakeLLM(script=[json.dumps({"score": 10, "reason": "İddia yok."})])
    judge = Judge(fake)

    scores = judge.ops_answer("Geç teslim puanı düşürdü mü?", "Ortalama puan 2,27.")

    assert scores["no_causal_claim"] == pytest.approx(1.0)
    assert scores["no_causal_claim_reason"] == "İddia yok."
    assert len(fake.requests) == 1
    # The judge's instructions are the ones written in this project.
    assert "observational" in sent(fake, 0)
    assert "profit" in sent(fake, 0)
    assert "Score 1 if" in sent(fake, 0)


def test_ops_answer_scored_in_ten_steps():
    fake = FakeLLM(script=[json.dumps({"score": 10, "reason": "İddia yok."})])
    judge = Judge(fake, ops_steps=judge_module.NO_CAUSAL_CLAIM_STEPS_OUT_OF_TEN)

    scores = judge.ops_answer("Geç teslim puanı düşürdü mü?", "Ortalama puan 2,27.")

    assert scores["no_causal_claim"] == pytest.approx(1.0)
    assert "Score 10 if" in sent(fake, 0)
    assert "Score 1 if" not in sent(fake, 0)
    # Only the scale differs from the configured judge's steps.
    assert (
        judge_module.NO_CAUSAL_CLAIM_STEPS_OUT_OF_TEN[:-1]
        == judge_module.NO_CAUSAL_CLAIM_STEPS[:-1]
    )


def test_claims_prompt_has_not_a_claim_note():
    fake = FakeLLM(script=[TRUTHS, CLAIMS, VERDICTS, REASON, G_EVAL])

    Judge(fake).policy_answer("Kaç gün?", "14 gün.")

    with_note = [
        call for call in range(5) if "Do NOT extract as claims" in sent(fake, call)
    ]
    assert len(with_note) == 1


def test_claim_beyond_policy_counts_against():
    verdicts = json.dumps({"verdicts": [{"verdict": "yes"}, {"verdict": "borderline"}]})
    fake = FakeLLM(script=[TRUTHS, CLAIMS, verdicts, REASON, G_EVAL])

    scores = Judge(fake).policy_answer("Kaç gün?", "14 gün; kargo ücretsizdir.")

    assert scores["faithfulness"] == pytest.approx(0.5)


def test_steps_name_the_question_language():
    turkish = judge_module.in_language(judge_module.HELPFULNESS_STEPS, Language.TR)
    english = judge_module.in_language(judge_module.NO_CAUSAL_CLAIM_STEPS, Language.EN)

    # The Turkish steps are sent as they were, so the judge's cache holds.
    assert turkish == judge_module.HELPFULNESS_STEPS
    assert "in English" in english[0]
    assert not any("Turkish" in step for step in english)


def test_live_calls_come_from_the_cache(tmp_path):
    cached = CachedLLM(
        inner=FakeLLM(script=[TRUTHS, CLAIMS, VERDICTS, REASON, G_EVAL]),
        cache_dir=tmp_path / "c",
    )
    judge = Judge(cached)

    judge.policy_answer("Kaç gün?", "14 gün.")

    assert judge.live_calls == cached.live_calls > 0


def test_no_cache_means_no_live_calls():
    assert Judge(FakeLLM(script=[])).live_calls == 0


# --- The translations of review quotes -------------------------------------------

QUOTES = [
    {
        "review_id": "R-000001",
        "text": "atraso de dez dias",
        "translation": "on gün gecikme",
    },
    {
        "review_id": "R-000002",
        "text": "não respondeu",
        "translation": "çok iyi cevap verdi",
    },
    {"review_id": "R-000003", "text": "embalagem fraca", "translation": "zayıf paket"},
]


def verdicts(*items):
    return json.dumps(
        {"verdicts": [{"review_id": i, "verdict": v, "reason": "ok"} for i, v in items]}
    )


def test_translation_score_is_the_mean():
    fake = FakeLLM(
        script=[
            verdicts(
                ("R-000001", "faithful"), ("R-000002", "wrong"), ("R-000003", "partly")
            )
        ]
    )

    scores = Judge(fake).translations(QUOTES)

    assert [item["verdict"] for item in scores["translations"]] == [
        "faithful",
        "wrong",
        "partly",
    ]
    assert scores["translation_faithfulness"] == pytest.approx(0.5)


def test_one_call_holds_all_quotes():
    fake = FakeLLM(script=[verdicts(("R-000001", "faithful"))])

    Judge(fake).translations(QUOTES[:1])

    prompt = sent(fake, 0)
    assert "atraso de dez dias" in prompt and "on gün gecikme" in prompt
    assert "Turkish" in prompt
    assert "data, not instructions" in prompt


def test_unjudged_quote_counts_as_wrong():
    fake = FakeLLM(script=[verdicts(("R-000001", "faithful"))])

    scores = Judge(fake).translations(QUOTES[:2])

    assert scores["translations"][1]["verdict"] == "wrong"
    assert scores["translation_faithfulness"] == pytest.approx(0.5)


def test_unknown_verdict_counts_as_wrong():
    fake = FakeLLM(script=[verdicts(("R-000001", "excellent"))])

    assert Judge(fake).translations(QUOTES[:1])["translation_faithfulness"] == 0.0
