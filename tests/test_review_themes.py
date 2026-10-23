"""Tests for the check of the themes the model draws from a sample of reviews."""

import json

import pytest

from src.knowledge.review_themes import (
    MAX_QUOTES,
    MAX_THEMES,
    folded,
    mentions,
    verify_themes,
)

SAMPLE = {
    "R-000001": "Demorou muito para chegar, atraso de dez dias.",
    "R-000002": "Atrasou e o vendedor não respondeu.",
    "R-000003": "Produto ok, embalagem fraca.",
    "R-000004": "Chegou rápido e bem embalado.",
}


def themes(*items):
    return json.dumps(list(items))


DELAY = {
    "name": "Atraso na entrega",
    "keywords": ["atras", "demor"],
    "quotes": [
        {
            "review_id": "R-000001",
            "text": "atraso de dez dias",
            "translation": "on gün gecikme",
        }
    ],
}


def test_a_theme_is_counted_by_the_reviews_that_hold_one_of_its_words():
    answer = verify_themes(SAMPLE, themes(DELAY))

    (theme,) = answer["themes"]
    # R-000001 holds "demor" and "atras", R-000002 holds "atras": two reviews.
    assert theme["reviews"] == 2
    assert theme["share_percent"] == 50.0
    assert answer["sampled"] == 4


def test_a_word_is_the_start_of_a_word_of_the_text_accents_and_case_aside():
    assert mentions("ATRASOU muito", "atras")
    assert mentions("Embalagem fraca", "embalagem")
    assert mentions("Não chegou", "nao")
    assert not mentions("nenhum atraso", "traso")
    assert folded("Péssimo  Produto") == "pessimo produto"


def test_the_themes_are_ordered_by_how_often_they_come_up():
    packaging = {"name": "Embalagem", "keywords": ["embalagem"], "quotes": []}

    answer = verify_themes(SAMPLE, themes(packaging, DELAY))

    assert [theme["name"] for theme in answer["themes"]] == [
        "Atraso na entrega",
        "Embalagem",
    ]


def test_a_quote_of_a_review_that_is_not_in_the_sample_is_refused():
    bad = {
        **DELAY,
        "quotes": [
            {"review_id": "R-999999", "text": "atraso de dez dias", "translation": "x"}
        ],
    }

    assert verify_themes(SAMPLE, themes(bad))["error"] == "UNKNOWN_REVIEW"


def test_a_quote_that_is_not_word_for_word_is_refused():
    paraphrase = {
        **DELAY,
        "quotes": [
            {
                "review_id": "R-000001",
                "text": "chegou com muito atraso",
                "translation": "x",
            }
        ],
    }

    assert verify_themes(SAMPLE, themes(paraphrase))["error"] == "QUOTE_NOT_VERBATIM"


def test_a_quote_of_another_review_than_the_one_named_is_refused():
    wrong = {
        **DELAY,
        "quotes": [
            {"review_id": "R-000004", "text": "atraso de dez dias", "translation": "x"}
        ],
    }

    assert verify_themes(SAMPLE, themes(wrong))["error"] == "QUOTE_NOT_VERBATIM"


def test_case_and_spacing_do_not_make_a_quote_wrong():
    quote = {
        "review_id": "R-000002",
        "text": "ATRASOU  e o vendedor",
        "translation": "x",
    }

    answer = verify_themes(SAMPLE, themes({**DELAY, "quotes": [quote]}))

    assert "error" not in answer
    # The quote comes back as the model wrote it, with its translation.
    assert answer["themes"][0]["quotes"][0]["text"] == "ATRASOU  e o vendedor"


def test_a_quote_that_is_too_short_is_refused():
    short = {
        **DELAY,
        "quotes": [{"review_id": "R-000001", "text": "muito", "translation": "x"}],
    }

    assert verify_themes(SAMPLE, themes(short))["error"] == "QUOTE_NOT_VERBATIM"


def test_a_theme_none_of_whose_words_is_in_the_sample_is_refused():
    invented = {"name": "Preço alto", "keywords": ["caro", "preco"], "quotes": []}

    assert (
        verify_themes(SAMPLE, themes(invented))["error"] == "NO_REVIEW_MENTIONS_THEME"
    )


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ("not json", "INVALID_THEMES"),
        ("[]", "INVALID_THEMES"),
        ('{"name": "x"}', "INVALID_THEMES"),
        ('[{"name": "x"}]', "INVALID_THEMES"),
        (themes({"name": "", "keywords": ["atras"]}), "INVALID_THEMES"),
        (themes({"name": "x" * 61, "keywords": ["atras"]}), "INVALID_THEMES"),
        (themes({"name": "x", "keywords": []}), "INVALID_KEYWORDS"),
        (themes({"name": "x", "keywords": ["ab"]}), "INVALID_KEYWORDS"),
        (themes({"name": "x", "keywords": ["abc"] * 7}), "INVALID_KEYWORDS"),
    ],
)
def test_a_malformed_answer_is_an_error_for_the_model_to_correct(payload, code):
    assert verify_themes(SAMPLE, payload)["error"] == code


def test_too_many_themes_or_quotes_are_refused():
    many = [DELAY] * (MAX_THEMES + 1)
    quote = {"review_id": "R-000001", "text": "atraso de dez dias", "translation": "x"}
    crowded = {**DELAY, "quotes": [quote] * (MAX_QUOTES + 1)}

    assert verify_themes(SAMPLE, json.dumps(many))["error"] == "TOO_MANY_THEMES"
    assert verify_themes(SAMPLE, themes(crowded))["error"] == "TOO_MANY_QUOTES"


def test_a_count_the_model_writes_is_not_used():
    # The model may send a count of its own; the one in the answer is counted here.
    claimed = {**DELAY, "reviews": 4, "share_percent": 100}

    answer = verify_themes(SAMPLE, themes(claimed))

    assert answer["themes"][0]["reviews"] == 2
