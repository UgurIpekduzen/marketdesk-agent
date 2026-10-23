"""The critic of the operations agent: do the answer's numbers come from the tools?

A check in code, no model: every number the answer states must be a number
some tool returned for this question (rounded as written, or a share
written as a percentage), apart from dates, years, citations and numbers
the question itself holds. The check is `src.grounding.ungrounded_numbers`,
the one the evaluation scores answers with.

What it cannot see: numbers that are in the tool output but attached to the
wrong thing (two states swapped), a figure used in the wrong sense, a
comparison that is wrong, and numbers written as words.
"""

import config
from src import messages
from src.grounding import ungrounded_numbers

OK = "ok"
CORRECTED = "corrected"
FLAGGED = "flagged"


# The ways the model is asked to correct an answer, by the name of the variant.
CORRECTIONS = {
    "plain": messages.CRITIC_CORRECTION,
    "compute": messages.CRITIC_CORRECTION_COMPUTE,
}


def correction_request(numbers: list[str]) -> str:
    """What the model is told when its answer holds numbers no tool returned."""
    wording = CORRECTIONS[config.CRITIC_CORRECTION_VARIANT]
    return wording.format(numbers=", ".join(numbers))


def unsupported(
    text: str, tool_results: list[tuple[str, object]], question: str
) -> list[str]:
    """The numbers in the answer that no tool of this question returned."""
    return ungrounded_numbers(text, tool_results, question)
