"""Tests for the session language and the two string catalogs."""

import string

import pytest

from src import messages, messages_en
from src.i18n import DEFAULT_LANGUAGE, Language, catalog, from_locale


def strings_of(module) -> dict:
    """The catalog's strings and maps, by name."""
    return {
        name: value
        for name, value in vars(module).items()
        if name.isupper() and isinstance(value, str | dict)
    }


def placeholders(text: str) -> set[str]:
    return {field for _, field, _, _ in string.Formatter().parse(text) if field}


@pytest.mark.parametrize(
    ("locale", "language"),
    [
        ("en-US", Language.EN),
        ("en-GB", Language.EN),
        ("en", Language.EN),
        ("EN_us", Language.EN),
        ("tr-TR", Language.TR),
        ("tr", Language.TR),
        # A third language and a missing locale get the first language.
        ("de-DE", Language.TR),
        ("", Language.TR),
        (None, Language.TR),
        # Only the language part counts, not a look-alike.
        ("eng", Language.TR),
    ],
)
def test_language_from_the_browser_locale(locale, language):
    assert from_locale(locale) == language


def test_turkish_is_the_default():
    assert DEFAULT_LANGUAGE == Language.TR


def test_each_language_has_its_catalog():
    assert catalog(Language.TR) is messages
    assert catalog(Language.EN) is messages_en
    assert catalog("en") is messages_en


def test_english_has_every_user_string():
    turkish = set(strings_of(messages)) - messages.MODEL_ONLY
    english = set(strings_of(messages_en))

    assert english == turkish


def test_model_only_strings_are_turkish():
    assert messages.MODEL_ONLY <= set(strings_of(messages))
    assert not messages.MODEL_ONLY & set(strings_of(messages_en))


def test_languages_share_placeholders():
    english = strings_of(messages_en)
    for name, turkish in strings_of(messages).items():
        # Turkish titles are cited as written: only English has the map.
        if name not in english or name == "POLICY_DOCUMENT_TITLES":
            continue
        if isinstance(turkish, str):
            assert placeholders(english[name]) == placeholders(turkish), name
        else:
            # A map has the same keys, and each value the same placeholders.
            assert english[name].keys() == turkish.keys(), name
            for key in turkish:
                assert placeholders(str(english[name][key])) == placeholders(
                    str(turkish[key])
                ), f"{name}[{key}]"


def test_english_strings_are_translated():
    turkish_letters = set("çğıöşüÇĞİÖŞÜ")
    for name, value in strings_of(messages_en).items():
        # The titles map has the Turkish document titles as its keys.
        texts = value.values() if isinstance(value, dict) else [value]
        for text in texts:
            assert not turkish_letters & set(str(text)), name


def test_policies_have_english_titles():
    from src.knowledge.policy_index import read_sections

    titles = {section.document for section in read_sections()}

    assert titles == set(messages_en.POLICY_DOCUMENT_TITLES)


def test_example_lists_match_in_length():
    for name in (
        "EXAMPLE_QUESTIONS_GENERAL",
        "EXAMPLE_QUESTIONS_POLICY",
        "EXAMPLE_QUESTIONS_OPS",
    ):
        assert len(getattr(messages_en, name)) == len(getattr(messages, name)), name
    for situation, questions in messages.EXAMPLE_QUESTIONS_BY_SITUATION.items():
        english = messages_en.EXAMPLE_QUESTIONS_BY_SITUATION[situation]
        assert len(english) == len(questions), situation
