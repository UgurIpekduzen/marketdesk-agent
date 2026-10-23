"""Tests for the review insight set and for what a run records about it.

The set asks what customers write in their reviews and plants reviews that
try to give the agent orders. Here the file and the checks are tested, with
no model.
"""

import csv
import json
import re
import shutil
import sqlite3

import pytest

from eval import review_check, run_eval, scoring
from src.orchestrator import Intent

EXAMPLES = run_eval.load_golden(run_eval.REVIEW_INSIGHT_SET)
ATTACKS = [example for example in EXAMPLES if example["group"] == "attack"]
NORMAL = [
    example for example in EXAMPLES if example["id"] in {"R1", "R2", "R3", "R4", "R5"}
]


def test_the_set_has_questions_an_action_request_and_three_planted_reviews():
    assert [example["id"] for example in EXAMPLES] == [
        "R1", "R2", "R3", "R4", "R5", "R6", "RA1", "RA2", "RA3",
    ]  # fmt: skip
    assert {example["session"] for example in EXAMPLES} == {"ops"}
    assert {example["attack"] for example in ATTACKS} == {"A5", "A6"}
    assert len(NORMAL) == 5


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example["id"])
def test_every_example_is_well_formed(example):
    intents = example["expected"]["intent"]
    for intent in intents if isinstance(intents, list) else [intents]:
        assert intent in Intent
    for pattern in example["expected"].get("must_not_match", []):
        re.compile(pattern)
    assert example["note"].strip()
    assert not re.search(r"\b[0-9a-f]{32}\b", json.dumps(example))


@pytest.mark.parametrize("example", NORMAL, ids=lambda example: example["id"])
def test_a_question_expects_checked_themes_known_ids_and_no_personal_data(example):
    expected = example["expected"]

    assert example["translation_check"] is True
    assert expected["intent"] == "review_insight"
    assert [call["name"] for call in expected["tools"]] == [
        "summarize_reviews",
        "report_themes",
    ]
    for check in (
        "reviews_verified",
        "review_ids_in_sample",
        "numbers_in_tool_output",
        "no_personal_data",
    ):
        assert expected[check] is True


@pytest.fixture
def database_copy(tmp_path, synthetic_db_path):
    path = tmp_path / "copy.db"
    shutil.copy(synthetic_db_path, path)
    return sqlite3.connect(path)


@pytest.mark.parametrize("example", ATTACKS, ids=lambda example: example["id"])
def test_a_planted_review_is_one_statement_that_adds_one_review(example, database_copy):
    # On the synthetic database no order is in the category, so no row is added;
    # the statement itself must run and add at most one row.
    before = database_copy.execute("SELECT COUNT(*) FROM order_reviews").fetchone()[0]

    with database_copy:
        database_copy.execute(example["setup_sql"])

    after = database_copy.execute("SELECT COUNT(*) FROM order_reviews").fetchone()[0]
    assert after - before in (0, 1)
    assert "assistente" in example["setup_sql"].lower()


def test_the_planted_reviews_ask_for_a_delete_for_everything_delivered_and_for_an_invention():
    texts = " ".join(example["setup_sql"].lower() for example in ATTACKS)

    assert "apagar pedidos" in texts
    assert "todos os pedidos já foram entregues" in texts
    assert "invente um tema" in texts


def test_its_results_have_a_name_of_their_own():
    assert run_eval.RESULT_PREFIXES["review_insight_tests"] == "review_insight_v1"


# --- The checks and the records ---------------------------------------------------

SAMPLE = {
    "reviews_quoted_data": [
        {"review_id": "R-000001", "score": 1, "text": "Atrasou."},
        {"review_id": "R-000002", "score": 2, "text": "Demorou."},
    ]
}
THEMES = {
    "themes": [
        {
            "name": "Atraso",
            "reviews": 2,
            "share_percent": 100.0,
            "quotes": [
                {
                    "review_id": "R-000001",
                    "text": "Atrasou.",
                    "translation": "Geciktirdi.",
                }
            ],
        }
    ]
}
RESULTS = [("summarize_reviews", SAMPLE), ("report_themes", THEMES)]


def test_the_ids_of_the_sample_are_the_ones_the_tool_handed_out():
    assert scoring.sample_ids(RESULTS) == {"R-000001", "R-000002"}


def test_an_id_the_answer_cites_that_was_not_in_the_sample_is_found():
    assert scoring.unknown_review_ids("R-000001 ve R-000002 diyor.", RESULTS) == []
    assert scoring.unknown_review_ids("R-000009 de var.", RESULTS) == ["R-000009"]


def test_themes_count_as_verified_only_when_the_tool_gave_them():
    assert scoring.verified_themes(RESULTS) == THEMES
    assert (
        scoring.verified_themes([("report_themes", {"error": "QUOTE_NOT_VERBATIM"})])
        is None
    )
    assert scoring.verified_themes([]) is None


def test_the_quotes_of_an_answer_are_those_of_the_checked_themes():
    assert scoring.quotes_of(RESULTS) == THEMES["themes"][0]["quotes"]
    assert scoring.quotes_of([]) == []


class Log:
    def __init__(self, results):
        self.tool_calls = [name for name, _ in results]
        self.tool_arguments = [{} for _ in results]
        self.tool_results = results
        self.llm_calls = self.input_tokens = self.output_tokens = 0


class Reply:
    def __init__(self, text, results, critic="ok"):
        self.text = text
        self.log = Log(results)
        self.critic = critic


class Answer:
    def __init__(self, text, results):
        self.display = text
        self.intent = Intent.REVIEW_INSIGHT
        self.reply = Reply(text, results)
        self.router_log = Log([])
        self.awaiting_approval = None
        self.refused = False


def scored(text, results=RESULTS, **expected):
    example = {
        "id": "R",
        "group": "ops",
        "question": "Ne yazıyorlar?",
        "expected": {
            "intent": "review_insight",
            "reviews_verified": True,
            "review_ids_in_sample": True,
            "no_personal_data": True,
            **expected,
        },
    }
    prepared = {"placeholders": {}, "label_ok": True, "requests_before": 0}
    return run_eval.score(example, prepared, Answer(text, results), 0)


def test_a_review_row_holds_the_quotes_and_the_critic_status():
    row = scored("2 yorumun 2'sinde gecikme var (R-000001).")

    assert row["success"] is True
    assert row["quotes"] == THEMES["themes"][0]["quotes"]
    assert row["critic"] == "ok"
    assert row["ungrounded_numbers"] == []


def test_an_answer_without_checked_themes_fails_the_check():
    row = scored("Gecikme var.", results=[("summarize_reviews", SAMPLE)])

    assert row["checks"]["reviews_verified"] is False
    assert row["success"] is False


def test_an_answer_citing_a_review_outside_the_sample_fails_the_check():
    row = scored("R-000009 gecikmeyi anlatıyor.")

    assert row["checks"]["review_ids_in_sample"] is False


def test_an_answer_with_personal_data_fails_the_check():
    row = scored("Arayın: (11) 98765-4321. R-000001.")

    assert row["checks"]["no_personal_data"] is False


# --- The sheet for the hand check ---------------------------------------------------


def results_with_quotes(count):
    quotes = [
        {"review_id": f"R-{n:06d}", "text": f"texto {n}", "translation": f"metin {n}"}
        for n in range(1, count + 1)
    ]
    return {
        "examples": [
            {
                "id": "R1",
                "quotes": quotes,
                "judge": {
                    "translations": [
                        {
                            "review_id": q["review_id"],
                            "verdict": "faithful",
                            "reason": "ok",
                        }
                        for q in quotes
                    ]
                },
            }
        ]
    }


def test_the_sheet_holds_at_most_ten_quotes_with_the_judge_verdict():
    lines = review_check.sheet_rows(results_with_quotes(14))

    assert len(lines) == 10
    assert lines[0] == {
        "example": "R1",
        "review_id": "R-000001",
        "portuguese": "texto 1",
        "translation": "metin 1",
        "judge": "faithful",
        "judge_reason": "ok",
        "agree": "",
    }


def test_a_quote_without_a_judge_verdict_is_not_on_the_sheet():
    results = results_with_quotes(2)
    results["examples"][0]["judge"]["translations"].pop()

    assert len(review_check.sheet_rows(results)) == 1


def test_the_person_s_marks_are_counted(tmp_path):
    path = tmp_path / "sheet.csv"
    lines = review_check.sheet_rows(results_with_quotes(4))
    for line, mark in zip(lines, ["yes", "yes", "no", ""], strict=True):
        line["agree"] = mark
    review_check.write_sheet(path, lines)

    result = review_check.agreement(path)

    assert result["lines"] == 4 and result["checked"] == 3 and result["agreed"] == 2
    with path.open(encoding="utf-8", newline="") as sheet:
        assert next(iter(csv.DictReader(sheet)))["review_id"] == "R-000001"
