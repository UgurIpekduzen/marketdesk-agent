"""Build the English golden and attack sets from the Turkish ones.

Usage:  python -m eval.build_english_sets

Each English example is its Turkish example with the language-bound fields
replaced from translations_en.json: the question, the texts the answer must
or must not hold, and the reference answer. The rest (ids, splits, tools,
decisions, the SQL that picks an order) is copied, so both languages are
held to the same expectations. Policy citations are written with the
English document titles by code. Change a Turkish set or a translation,
then run this again; a test checks that the English sets are what it
writes.
"""

import json
import re
from pathlib import Path

from src import messages, messages_en
from src.i18n import Language

EVAL_DIR = Path(__file__).resolve().parent
TRANSLATIONS = EVAL_DIR / "translations_en.json"
# Turkish set -> English set.
SETS = {
    EVAL_DIR / "golden_set.jsonl": EVAL_DIR / "golden_set_en.jsonl",
    EVAL_DIR / "injection_tests.jsonl": EVAL_DIR / "injection_tests_en.jsonl",
}
# Expected texts that are the same in every language: a number, a mark, an
# alias or ticket prefix, a placeholder.
LANGUAGE_FREE = re.compile(r"[\d\W_]*|\{\w+\}|[A-Z]+-")
TRANSLATED_FIELDS = ("must_contain", "must_not_match")
# What stands between the title and the section number in a Turkish
# citation: ", Bölüm ".
CITATION_SEPARATOR = messages.POLICY_CITATION.split("{document}")[1].split("{number}")[
    0
]


def language_free(value) -> bool:
    """True when the value holds no text of a language, so it needs no translation."""
    items = value if isinstance(value, list) else [value]
    return all(
        language_free(item) if isinstance(item, list) else LANGUAGE_FREE.fullmatch(item)
        for item in items
    )


def english_source(citation: str) -> str:
    """A Turkish citation as an English answer gives it."""
    prefix, _, number = citation.rpartition(CITATION_SEPARATOR)
    if not prefix:
        raise ValueError(f"not a citation: {citation!r}")
    return messages_en.POLICY_CITATION.format(
        document=messages_en.POLICY_DOCUMENT_TITLES[prefix], number=number
    )


def translate(example: dict, translation: dict) -> dict:
    """The English example; raises when a language-bound field has no
    translation."""
    english = json.loads(json.dumps(example))
    english["language"] = Language.EN.value
    english["question"] = translation["question"]
    for field in TRANSLATED_FIELDS:
        turkish = example["expected"].get(field)
        if turkish is None:
            if field in translation:
                raise ValueError(f"{example['id']}: {field} is not in the Turkish set")
            continue
        if field in translation:
            english["expected"][field] = translation[field]
        elif not language_free(turkish):
            raise ValueError(f"{example['id']}: {field} needs a translation")
    if "reference_answer" in example:
        if "reference_answer" not in translation:
            raise ValueError(f"{example['id']}: reference_answer needs a translation")
        english["reference_answer"] = translation["reference_answer"]
    if "source" in example:
        source = example["source"]
        english["source"] = (
            [english_source(item) for item in source]
            if isinstance(source, list)
            else english_source(source)
        )
    return english


def build(turkish_sets: dict[Path, str], translations: dict) -> dict[Path, str]:
    """The English sets as JSON lines, by the path they are written to."""
    used = set()
    built = {}
    for turkish_path, english_path in SETS.items():
        lines = []
        for line in turkish_sets[turkish_path].splitlines():
            if not line.strip():
                continue
            example = json.loads(line)
            if example["id"] not in translations:
                raise ValueError(f"{example['id']}: no translation")
            used.add(example["id"])
            english = translate(example, translations[example["id"]])
            lines.append(json.dumps(english, ensure_ascii=False) + "\n")
        built[english_path] = "".join(lines)
    unknown = set(translations) - used - {"_about"}
    if unknown:
        raise ValueError(f"translations for no example: {sorted(unknown)}")
    return built


def main() -> None:
    """Run the command line entry point."""
    turkish = {path: path.read_text(encoding="utf-8") for path in SETS}
    translations = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    for path, text in build(turkish, translations).items():
        path.write_text(text, encoding="utf-8")
        print(f"{text.count(chr(10))} examples written to {path.name}")


if __name__ == "__main__":
    main()
