"""The language of a session: Turkish or English.

The page starts in the browser's language and the visitor can switch it;
the session holds it from then on, like the session type. A message never
sets it, and changing it starts a new conversation.
"""

from enum import StrEnum
from types import ModuleType

from src import messages, messages_en


class Language(StrEnum):
    TR = "tr"
    EN = "en"


DEFAULT_LANGUAGE = Language.TR
# How the system prompts name the language the answer is written in.
LANGUAGE_NAMES = {Language.TR: "Turkish", Language.EN: "English"}
CATALOGS = {Language.TR: messages, Language.EN: messages_en}


def from_locale(locale: str | None) -> Language:
    """The language a browser locale such as "en-US" asks for.

    English for any English locale, Turkish for everything else: Turkish is
    the system's first language, and a browser in a third language gets it.
    """
    if locale and locale.strip().lower().split("-")[0].split("_")[0] == "en":
        return Language.EN
    return DEFAULT_LANGUAGE


def catalog(language: Language) -> ModuleType:
    """The user-facing strings of a language, under the same names."""
    return CATALOGS[Language(language)]
