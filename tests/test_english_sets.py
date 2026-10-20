"""Tests for the English golden and attack sets and the script that builds
them from the Turkish ones."""

import json

import pytest

from eval import build_english_sets
from src import messages_en

TURKISH_LETTERS = set("çğıöşüÇĞİÖŞÜ")


def load(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def pairs():
    for turkish_path, english_path in build_english_sets.SETS.items():
        yield from zip(load(turkish_path), load(english_path), strict=True)


def test_the_english_sets_are_what_the_script_builds():
    turkish = {
        path: path.read_text(encoding="utf-8") for path in build_english_sets.SETS
    }
    translations = json.loads(
        build_english_sets.TRANSLATIONS.read_text(encoding="utf-8")
    )

    built = build_english_sets.build(turkish, translations)

    for path, text in built.items():
        assert text == path.read_text(encoding="utf-8"), (
            "run `task eval:build-en` after changing a set or a translation"
        )


def test_both_languages_hold_the_same_examples_to_the_same_expectations():
    for turkish, english in pairs():
        assert english["id"] == turkish["id"]
        assert english["language"] == "en"
        for field in set(turkish) - {"question", "reference_answer", "source"}:
            if field == "expected":
                continue
            assert english[field] == turkish[field], (turkish["id"], field)
        for field, value in turkish["expected"].items():
            if field in build_english_sets.TRANSLATED_FIELDS:
                continue
            assert english["expected"][field] == value, (turkish["id"], field)


def test_an_order_in_the_question_stays_in_the_question():
    for turkish, english in pairs():
        assert ("{order}" in english["question"]) == ("{order}" in turkish["question"])


def test_nothing_turkish_is_left_in_the_english_texts():
    for _, english in pairs():
        texts = [english["question"], english.get("reference_answer", "")]
        texts += json.dumps(english["expected"].get("must_contain", [])).split('"')
        assert not any(TURKISH_LETTERS & set(text) for text in texts), english["id"]


def test_sources_are_cited_with_the_english_titles():
    titles = set(messages_en.POLICY_DOCUMENT_TITLES.values())
    sources = [
        source
        for _, english in pairs()
        if "source" in english
        for source in (
            english["source"]
            if isinstance(english["source"], list)
            else [english["source"]]
        )
    ]

    assert sources
    for source in sources:
        title, _, number = source.rpartition(", Section ")
        assert title in titles and number.isdigit(), source


def test_a_language_bound_text_without_a_translation_is_refused():
    example = {
        "id": "X",
        "question": "Kargo nerede?",
        "expected": {"intent": "support", "must_contain": ["kargo"]},
    }

    with pytest.raises(ValueError, match="must_contain needs a translation"):
        build_english_sets.translate(example, {"question": "Where is it?"})


def test_language_free_texts_need_no_translation():
    example = {
        "id": "X",
        "question": "Son siparişim nerede?",
        "expected": {"intent": "support", "must_contain": ["SIP-", "?", ["14"]]},
    }

    english = build_english_sets.translate(example, {"question": "Where is it?"})

    assert english["expected"]["must_contain"] == ["SIP-", "?", ["14"]]


def test_an_example_without_a_translation_is_refused():
    turkish = {
        path: path.read_text(encoding="utf-8") for path in build_english_sets.SETS
    }
    translations = json.loads(
        build_english_sets.TRANSLATIONS.read_text(encoding="utf-8")
    )
    del translations["S1"]

    with pytest.raises(ValueError, match="S1: no translation"):
        build_english_sets.build(turkish, translations)
