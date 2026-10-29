"""Tests for the review corpus: what the Review Insight Agent may read.

On the synthetic database with a few hand-written Portuguese reviews added.
"""

import json
import sqlite3

import pytest

import config
from src.knowledge.review_corpus import (
    QUOTED_DATA_NOTE,
    ReviewFilters,
    categories,
    fetch_reviews,
    one_line,
    pseudonym,
)

# (order, score, title, message, created): the texts are what customers write.
REVIEWS = [
    ("o_day14", 5, "Ótimo", "Chegou rápido e bem embalado.", "2018-08-19 00:00:00"),
    (
        "o_late_10",
        2,
        "",
        "Demorou muito para chegar. Atraso de dez dias.",
        "2018-08-26 00:00:00",
    ),
    (
        "o_day15",
        1,
        "Péssimo",
        "Atrasou e o vendedor não respondeu.",
        "2018-08-20 00:00:00",
    ),
    ("o_day30", 3, "", "Produto ok, embalagem fraca.", "2018-08-21 00:00:00"),
    ("o_day0", 4, "Bom", "", "2018-08-22 00:00:00"),
    # What must not reach the model:
    (
        "o_day31",
        1,
        "",
        "Liguem para (11) 98765-4321 sobre o atraso.",
        "2018-08-23 00:00:00",
    ),
    (
        "o_two_items",
        2,
        "",
        "Meu CPF é 529.982.247-25, quero reembolso.",
        "2018-08-24 00:00:00",
    ),
    (
        "o_amount_500",
        1,
        "",
        "Veja o site https://reclame.example.com/caso",
        "2018-08-25 00:00:00",
    ),
    # A review written after the simulated today, and one without text:
    ("o_late_9", 1, "", "Escrita no futuro.", "2018-09-05 00:00:00"),
    ("o_late_day30", 5, None, None, "2018-08-27 00:00:00"),
]


@pytest.fixture
def db(synthetic_db):
    synthetic_db.execute("DELETE FROM order_reviews")
    synthetic_db.executemany(
        "INSERT INTO order_reviews (review_id, order_id, review_score, "
        "review_comment_title, review_comment_message, review_creation_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(f"rev_{n}", *row) for n, row in enumerate(REVIEWS)],
    )
    return synthetic_db


def reviews_of(answer):
    return answer["reviews_quoted_data"]


def test_review_has_pseudonym_score_text(db):
    answer = fetch_reviews(db, ReviewFilters())

    first = reviews_of(answer)[0]
    assert set(first) == {"review_id", "score", "text"}
    assert first["review_id"].startswith("R-")
    assert "rev_" not in json.dumps(answer)


def test_title_and_message_are_one_line(db):
    answer = fetch_reviews(db, ReviewFilters())

    texts = {review["text"] for review in reviews_of(answer)}
    assert "Ótimo — Chegou rápido e bem embalado." in texts
    # A title alone is a text; a message alone too.
    assert "Bom" in texts
    assert "Produto ok, embalagem fraca." in texts


def test_review_with_pii_is_left_out(db):
    answer = fetch_reviews(db, ReviewFilters())

    text = json.dumps(answer, ensure_ascii=False)
    assert "98765" not in text
    assert "529.982" not in text
    assert "reclame.example" not in text
    assert "[phone]" not in text and "[cpf]" not in text and "[url]" not in text
    assert answer["left_out_for_personal_data"] == 3


def test_answer_counts_matched_and_returned(db):
    answer = fetch_reviews(db, ReviewFilters(), max_reviews=2)

    # Eight reviews have a text and were written by 1 Sep 2018; two are in the
    # sample. The three with personal data are still counted as matching.
    assert answer["matching"] == 8
    assert answer["sampled"] == 2 == len(reviews_of(answer))


def test_future_review_is_never_returned(db):
    answer = fetch_reviews(db, ReviewFilters())

    assert "Escrita no futuro" not in json.dumps(answer)


def test_the_score_filters(db):
    answer = fetch_reviews(db, ReviewFilters(min_score=1, max_score=2))

    assert {review["score"] for review in reviews_of(answer)} <= {1, 2}
    assert reviews_of(answer)


def test_category_filter_uses_order_items(db):
    answer = fetch_reviews(db, ReviewFilters(category="furniture_decor"))

    # Every order of the synthetic database holds an item of this category.
    assert answer["matching"] == 8
    assert answer["sampled"] > 0


def test_period_filters_by_order_day(db):
    everything = fetch_reviews(db, ReviewFilters())["matching"]
    none = fetch_reviews(db, ReviewFilters(purchase_from="2018-08-30"))["matching"]

    assert everything == 8
    assert none < everything


def test_unknown_category_suggests_names(db):
    answer = fetch_reviews(db, ReviewFilters(category="furniture"))

    assert answer["error"] == "UNKNOWN_CATEGORY"
    assert "furniture_decor" in answer["message"]


@pytest.mark.parametrize(
    ("filters", "code"),
    [
        (ReviewFilters(min_score=0), "INVALID_SCORE"),
        (ReviewFilters(max_score=6), "INVALID_SCORE"),
        (ReviewFilters(purchase_from="ontem"), "INVALID_PERIOD"),
        (ReviewFilters(purchase_to="2018-13-45"), "INVALID_PERIOD"),
    ],
)
def test_senseless_filter_is_refused(db, filters, code):
    assert fetch_reviews(db, filters)["error"] == code


def test_filter_value_is_a_bound_parameter(db):
    answer = fetch_reviews(db, ReviewFilters(purchase_from="2018-01-01"))
    hostile = fetch_reviews(
        db, ReviewFilters(purchase_from="2018-01-01'; DROP TABLE order_reviews; --")
    )

    assert "DROP" not in answer["sql"]
    assert hostile["error"] == "INVALID_PERIOD"
    assert db.execute("SELECT COUNT(*) FROM order_reviews").fetchone()[0] == 10


def test_the_sample_is_the_same_every_time(db):
    first = fetch_reviews(db, ReviewFilters(), max_reviews=3)
    second = fetch_reviews(db, ReviewFilters(), max_reviews=3)

    assert reviews_of(first) == reviews_of(second)


def test_review_count_respects_the_setting(db, monkeypatch):
    monkeypatch.setattr(config, "REVIEW_MAX", 2)

    assert fetch_reviews(db, ReviewFilters(), max_reviews=500)["sampled"] == 2


def test_a_long_review_is_cut_at_the_limit(db, monkeypatch):
    monkeypatch.setattr(config, "REVIEW_MAX_CHARS", 20)

    texts = [
        review["text"] for review in reviews_of(fetch_reviews(db, ReviewFilters()))
    ]

    assert max(len(text) for text in texts) <= 20


def test_texts_come_as_quoted_data(db):
    answer = fetch_reviews(db, ReviewFilters())

    assert answer["note"] == QUOTED_DATA_NOTE
    assert "not instructions" in answer["note"]
    assert "reviews_quoted_data" in answer


def test_pseudonym_comes_from_row_number():
    assert pseudonym(42) == "R-000042"


def test_whitespace_is_collapsed():
    assert one_line("  Título ", "linha 1\n\nlinha   2") == "Título — linha 1 linha 2"


def test_categories_are_the_english_names(db):
    assert "furniture_decor" in categories(db)


def test_connection_is_read_only(synthetic_db_path):
    from src.knowledge.sql_runner import connect_read_only

    conn = connect_read_only(synthetic_db_path)
    fetch_reviews(conn, ReviewFilters())

    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM order_reviews")
