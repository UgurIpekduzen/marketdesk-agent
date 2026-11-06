"""The example questions offered above an empty conversation.

They come from a fixed pool in the language's catalog: the Turkish ones
were tried with the real model and answered well, the English ones are
their translations. The model never writes them. A few are picked at random
when a conversation starts and kept until it ends.
"""

import random

from src.i18n import DEFAULT_LANGUAGE, Language, catalog

# How many policy questions a customer is offered, and how many questions an
# operations analyst is offered: four buttons on either side.
CUSTOMER_POLICY_COUNT = 2
OPS_COUNT = 4


def pick_examples(
    identity: tuple, rng: random.Random, language: Language = DEFAULT_LANGUAGE
) -> list[str]:
    """The examples for a session: ("customer", situation) or ("ops",).

    A customer gets one question for their situation, one that fits every
    situation and two policy questions; an analyst gets four metric
    questions, in the session's language. The generator is passed in, so a
    test can seed it.

    Args:
        identity (tuple): ("customer", situation) or ("ops",).
        rng (random.Random): The random source.
        language (Language): The session's language.

    Returns:
        The example questions.
    """
    messages = catalog(language)
    if identity[0] == "ops":
        return rng.sample(messages.EXAMPLE_QUESTIONS_OPS, OPS_COUNT)
    situation = identity[1]
    return [
        rng.choice(messages.EXAMPLE_QUESTIONS_BY_SITUATION[situation]),
        rng.choice(messages.EXAMPLE_QUESTIONS_GENERAL),
        *rng.sample(messages.EXAMPLE_QUESTIONS_POLICY, CUSTOMER_POLICY_COUNT),
    ]
