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
    "R-000001": "Demorou muito para chegar. Atraso de dez dias.",
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
        "text": "ATRASOU  e o vendedor NÃO respondeu",
        "translation": "x",
    }

    answer = verify_themes(SAMPLE, themes({**DELAY, "quotes": [quote]}))

    assert "error" not in answer
    # The quote comes back as the model wrote it, with its translation.
    assert (
        answer["themes"][0]["quotes"][0]["text"]
        == "ATRASOU  e o vendedor NÃO respondeu"
    )


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


# --- Words that tell nothing, and quotes cut out of a sentence -------------------

BIG_SAMPLE = {
    f"R-{n:06d}": text
    for n, text in enumerate(
        [
            "Não recebi o produto, péssimo atendimento.",
            "Produto chegou com defeito e a loja não responde.",
            "Não gostei, a cor é diferente da foto.",
            "Entrega rápida, produto ótimo.",
            "Comprei com desconto, chegou no prazo.",
            "Atraso de dez dias para chegar.",
            "Chegou quebrado. Quero o dinheiro de volta.",
            "Muito bom, recomendo a loja.",
            "Gostei do produto e da entrega.",
            "Nota 2.5 estrelas, esperava mais.",
        ],
        start=1,
    )
}


@pytest.mark.parametrize("word", ["com", "que", "não", "NAO", "para", "pro", "uma"])
def test_a_word_that_is_in_every_review_whatever_it_says_is_refused(word):
    theme = {"name": "Atraso na entrega", "keywords": [word, "atras"], "quotes": []}

    answer = verify_themes(SAMPLE, themes(theme))

    assert answer["error"] == "GENERIC_KEYWORD"
    assert word in answer["message"]


def test_a_word_that_is_in_most_reviews_of_a_large_sample_is_refused():
    sample = {f"R-{n:06d}": "Produto bom, entrega boa." for n in range(10)}
    sample["R-000010"] = "Chegou quebrado e atrasado."
    theme = {"name": "Qualidade", "keywords": ["produto"], "quotes": []}

    answer = verify_themes(sample, themes(theme))

    assert answer["error"] == "GENERIC_KEYWORD"
    assert "10 of 11" in answer["message"]


def test_the_same_word_is_fine_in_a_small_sample_and_when_it_is_not_in_most_reviews():
    theme = {"name": "Produto", "keywords": ["produto"], "quotes": []}

    assert "error" not in verify_themes(BIG_SAMPLE, themes(theme))
    # Four reviews only: too few to say a word is too common.
    small = {k: v for k, v in list(BIG_SAMPLE.items())[:4]}
    assert "error" not in verify_themes(small, themes(theme))


def test_the_counts_of_the_honest_words_are_unchanged():
    theme = {"name": "Atraso", "keywords": ["atras", "demor"], "quotes": []}

    answer = verify_themes(BIG_SAMPLE, themes(theme))

    assert answer["themes"][0]["reviews"] == 1


def quote_of(review_id, text):
    theme = {
        "name": "Entrega",
        "keywords": ["receb", "entrega", "chegou"],
        "quotes": [{"review_id": review_id, "text": text, "translation": "x"}],
    }
    return verify_themes(BIG_SAMPLE, themes(theme))


@pytest.mark.parametrize(
    ("review_id", "text"),
    [
        # Cut after the "Não": the sentence says the opposite.
        ("R-000001", "recebi o produto"),
        # Cut at a comma, in the middle of a sentence.
        ("R-000001", "Não recebi o produto"),
        ("R-000001", "péssimo atendimento"),
        ("R-000004", "Entrega rápida"),
        ("R-000003", "a cor é diferente da foto"),
        # Starts or ends in the middle of a word.
        ("R-000007", "hegou quebrado"),
        ("R-000007", "Chegou quebrad"),
        # The point of "2.5" is not the end of a sentence.
        ("R-000010", "5 estrelas, esperava mais"),
    ],
)
def test_a_quote_cut_out_of_a_sentence_is_refused(review_id, text):
    assert quote_of(review_id, text)["error"] == "QUOTE_NOT_VERBATIM"


@pytest.mark.parametrize(
    ("review_id", "text"),
    [
        # The whole review, which is one sentence.
        ("R-000001", "Não recebi o produto, péssimo atendimento."),
        ("R-000001", "não recebi o produto, péssimo atendimento"),
        # One of two sentences, either.
        ("R-000007", "Chegou quebrado."),
        ("R-000007", "Quero o dinheiro de volta."),
        # Both sentences.
        ("R-000007", "Chegou quebrado. Quero o dinheiro de volta."),
        # With or without the full stop or the "!!!".
        ("R-000007", "Chegou quebrado"),
        ("R-000010", "Nota 2.5 estrelas, esperava mais."),
    ],
)
def test_a_quote_of_whole_sentences_is_kept(review_id, text):
    assert "error" not in quote_of(review_id, text)


def test_the_title_and_the_message_of_a_review_are_two_sentences():
    sample = {"R-000001": "Ótimo — Chegou super rápido e veio tudo certo!"}
    theme = {
        "name": "Entrega",
        "keywords": ["chegou"],
        "quotes": [
            {
                "review_id": "R-000001",
                "text": "Chegou super rápido e veio tudo certo!",
                "translation": "x",
            }
        ],
    }

    assert "error" not in verify_themes(sample, themes(theme))


def test_a_new_line_ends_a_sentence_too():
    sample = {"R-000001": "Péssimo\nNão recebi nada do que comprei"}
    theme = {
        "name": "Entrega",
        "keywords": ["receb"],
        "quotes": [
            {
                "review_id": "R-000001",
                "text": "Não recebi nada do que comprei",
                "translation": "x",
            }
        ],
    }

    assert "error" not in verify_themes(sample, themes(theme))
