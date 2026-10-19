"""The example questions offered above an empty conversation.

They come from a fixed pool in src/messages.py: questions that were tried
with the real model and answered well. The model never writes them. A few
are picked at random when a conversation starts and kept until it ends.
"""

import random

from src import messages

# How many policy questions a customer is offered, and how many questions an
# operations analyst is offered: four buttons on either side.
CUSTOMER_POLICY_COUNT = 2
OPS_COUNT = 4


def pick_examples(identity: tuple, rng: random.Random) -> list[str]:
    """The examples for a session: ("customer", situation) or ("ops",).

    A customer gets one question for their situation, one that fits every
    situation and two policy questions; an analyst gets four metric
    questions. The generator is passed in, so a test can seed it.
    """
    if identity[0] == "ops":
        return rng.sample(messages.EXAMPLE_QUESTIONS_OPS, OPS_COUNT)
    situation = identity[1]
    return [
        rng.choice(messages.EXAMPLE_QUESTIONS_BY_SITUATION[situation]),
        rng.choice(messages.EXAMPLE_QUESTIONS_GENERAL),
        *rng.sample(messages.EXAMPLE_QUESTIONS_POLICY, CUSTOMER_POLICY_COUNT),
    ]
