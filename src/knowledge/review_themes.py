"""Checks the themes the model draws from a sample of reviews, in code.

The model reads the sample and proposes themes: a name, a few Portuguese
words that stand for it and some quotes with their translation. What code
can check, it checks, so the numbers and the quotes of the answer are not
the model's word:

- a quote must be of a review of the sample, and its Portuguese text must
  be, word for word, a piece of that review's text (case and spacing aside);
- how often a theme comes up is counted here: the number of reviews of the
  sample that hold at least one of its words, not a number the model says;
- the sizes are kept small: a few themes, a few words, a few quotes.

What code cannot check: that the translation is faithful (an independent
judge scores it in the evaluation, and a person checks a few by hand), that
the name of a theme describes it, and that the words stand for the theme.
A word is matched as the start of a word of the text, accents and case
aside, so "atras" finds "atraso", "atrasou" and "atrasada".
"""

import json
import re
import unicodedata
from dataclasses import dataclass

MAX_THEMES = 5
MAX_KEYWORDS = 6
MAX_QUOTES = 3
MIN_KEYWORD_CHARS = 3
MIN_QUOTE_CHARS = 8
MAX_NAME_CHARS = 60


def folded(text: str) -> str:
    """Lower case without accents, spaces made single."""
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return " ".join(plain.split())


def error(code: str, message: str) -> dict:
    return {"error": code, "message": message}


@dataclass(frozen=True)
class Theme:
    name: str
    keywords: tuple[str, ...]
    quotes: tuple[tuple[str, str, str], ...]  # (review_id, Portuguese, translation)


def parse_themes(themes_json: str) -> list[Theme] | dict:
    """The themes the model sent as JSON, or an error answer for the model."""
    try:
        data = json.loads(themes_json)
    except (TypeError, ValueError):
        return error(
            "INVALID_THEMES",
            "themes_json is not valid JSON: keys and strings go in double quotes.",
        )
    if not isinstance(data, list) or not data:
        return error("INVALID_THEMES", "themes_json is a non-empty list of themes.")
    if len(data) > MAX_THEMES:
        return error("TOO_MANY_THEMES", f"At most {MAX_THEMES} themes.")
    themes = []
    for item in data:
        try:
            name = str(item["name"]).strip()
            keywords = tuple(str(word).strip() for word in item["keywords"])
            quotes = tuple(
                (str(q["review_id"]), str(q["text"]), str(q["translation"]))
                for q in item.get("quotes", [])
            )
        except (KeyError, TypeError):
            return error(
                "INVALID_THEMES",
                'Each theme is {"name", "keywords": [...], "quotes": '
                '[{"review_id", "text", "translation"}]}.',
            )
        if not name or len(name) > MAX_NAME_CHARS:
            return error(
                "INVALID_THEMES", f"A theme name is 1 to {MAX_NAME_CHARS} characters."
            )
        if not 1 <= len(keywords) <= MAX_KEYWORDS or any(
            len(word) < MIN_KEYWORD_CHARS for word in keywords
        ):
            return error(
                "INVALID_KEYWORDS",
                f"Theme {name!r}: 1 to {MAX_KEYWORDS} words of at least "
                f"{MIN_KEYWORD_CHARS} characters, as written in the reviews.",
            )
        if len(quotes) > MAX_QUOTES:
            return error(
                "TOO_MANY_QUOTES", f"Theme {name!r}: at most {MAX_QUOTES} quotes."
            )
        themes.append(Theme(name, keywords, quotes))
    return themes


def mentions(text: str, keyword: str) -> bool:
    """Whether a word of the text starts with the keyword."""
    return re.search(rf"\b{re.escape(folded(keyword))}", folded(text)) is not None


def verify_themes(sample: dict[str, str], themes_json: str) -> dict:
    """Check the themes against the sample (review id -> text) and count them.

    Returns the verified themes with their counts, or an error answer that
    names the first problem, for the model to correct.
    """
    parsed = parse_themes(themes_json)
    if isinstance(parsed, dict):
        return parsed
    verified = []
    for theme in parsed:
        count = sum(
            any(mentions(text, word) for word in theme.keywords)
            for text in sample.values()
        )
        if count == 0:
            return error(
                "NO_REVIEW_MENTIONS_THEME",
                f"Theme {theme.name!r}: none of its words is in a review of the "
                "sample. Use words as they are written in the reviews.",
            )
        quotes = []
        for review_id, text, translation in theme.quotes:
            if review_id not in sample:
                return error(
                    "UNKNOWN_REVIEW",
                    f"{review_id!r} is not a review of the sample you were given.",
                )
            if len(text) < MIN_QUOTE_CHARS or folded(text) not in folded(
                sample[review_id]
            ):
                return error(
                    "QUOTE_NOT_VERBATIM",
                    f"The quote for {review_id} is not a word-for-word piece of "
                    f"that review (at least {MIN_QUOTE_CHARS} characters).",
                )
            quotes.append(
                {"review_id": review_id, "text": text, "translation": translation}
            )
        verified.append(
            {
                "name": theme.name,
                "keywords": list(theme.keywords),
                "reviews": count,
                "share_percent": round(100 * count / len(sample), 1),
                "quotes": quotes,
            }
        )
    verified.sort(key=lambda theme: -theme["reviews"])
    return {
        "sampled": len(sample),
        "themes": verified,
        "how_counted": (
            "A theme's count is the number of reviews of the sample with at "
            "least one of its words; the quotes are word for word."
        ),
    }
