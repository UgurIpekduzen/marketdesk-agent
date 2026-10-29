"""Tests for the sheet on which a person checks the judge's scores."""

import csv

import pytest

from eval.judge_check import COLUMNS, agreement, sheet_rows, write_sheet

FINAL = {
    "examples": [
        {
            "id": "P1",
            "answer": "14 gün (İade Politikası, Bölüm 2).",
            "judge": {
                "faithfulness": 0.5,
                "claims": [
                    {"claim": "Süre 14 gündür.", "verdict": "yes"},
                    {"claim": "Kargo ücretsizdir.", "verdict": "borderline"},
                ],
                "faithfulness_reason": "Bir iddia desteklenmiyor.",
                "helpfulness": 1.0,
                "helpfulness_reason": "Soruyu cevaplıyor.",
            },
        },
        {
            "id": "O1",
            "answer": "Oran %3,58.",
            "judge": {"no_causal_claim": 1.0, "no_causal_claim_reason": "İddia yok."},
        },
        {"id": "S1", "answer": "Kargoda.", "judge": {}},
        {"id": "S2", "answer": "Uygun."},
    ]
}
BASELINES = {
    "examples": [
        {
            "baseline": "B0",
            "id": "P1",
            "answer": "14 gün.",
            "judge": {"faithfulness": 1.0},
        }
    ]
}
QUESTIONS = {"P1": "Kaç gün içinde iade edebilirim?", "O1": "Geç teslim oranı?"}


def test_sheet_has_one_line_per_judge_score():
    lines = sheet_rows(FINAL, QUESTIONS)

    assert [(line["id"], line["score_name"], line["score"]) for line in lines] == [
        ("P1", "faithfulness", "0.50"),
        ("P1", "helpfulness", "1.00"),
        ("O1", "no_causal_claim", "1.00"),
    ]
    assert {line["system"] for line in lines} == {"Final"}
    assert {line["agree"] for line in lines} == {""}
    assert lines[0]["question"] == QUESTIONS["P1"]


def test_faithfulness_line_shows_verdicts():
    reason = sheet_rows(FINAL, QUESTIONS)[0]["reason"]

    assert "[yes] Süre 14 gündür." in reason
    assert "[borderline] Kargo ücretsizdir." in reason
    assert reason.endswith("Bir iddia desteklenmiyor.")


def test_baseline_answers_are_named():
    (line,) = sheet_rows(BASELINES, QUESTIONS)

    assert line["system"] == "B0"


def filled(tmp_path, marks):
    path = tmp_path / "sheet.csv"
    lines = sheet_rows(FINAL, QUESTIONS) + sheet_rows(BASELINES, QUESTIONS)
    for line, mark in zip(lines, marks, strict=True):
        line["agree"] = mark
    write_sheet(path, lines)
    return path


def test_sheet_is_csv_with_ordered_columns(tmp_path):
    path = filled(tmp_path, ["", "", "", ""])

    with path.open(encoding="utf-8", newline="") as sheet:
        header = next(csv.reader(sheet))

    assert tuple(header) == COLUMNS


def test_agreement_counts_marked_lines_only(tmp_path):
    result = agreement(filled(tmp_path, ["yes", "No", "", " YES "]))

    assert result == {
        "lines": 4,
        "checked": 3,
        "agreed": 2,
        "rate": pytest.approx(2 / 3),
    }


def test_no_rate_before_anything_is_marked(tmp_path):
    assert agreement(filled(tmp_path, ["", "", "", ""]))["rate"] is None


def test_mark_must_be_yes_or_no(tmp_path):
    with pytest.raises(ValueError, match="evet"):
        agreement(filled(tmp_path, ["yes", "evet", "", ""]))
