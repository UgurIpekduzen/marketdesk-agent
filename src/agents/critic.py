"""The critic of the operations agent: do the answer's numbers come from the tools?

A check in code, no model: every number the answer states must be a number
some tool returned for this question (rounded as written, or a share
written as a percentage, or the number of rows a result holds), apart from
dates, years, citations and numbers the question itself holds. The check is
`src.grounding.ungrounded_numbers`,
the one the evaluation scores answers with.

What it cannot see: numbers that are in the tool output but attached to the
wrong thing (two states swapped), a figure used in the wrong sense, a
comparison that is wrong, and numbers written as words.
"""

import logging

import config
from src import messages, tracing
from src.agents.runner import run_agent
from src.grounding import ungrounded_numbers
from src.i18n import DEFAULT_LANGUAGE, Language, catalog

logger = logging.getLogger(__name__)

OK = "ok"
CORRECTED = "corrected"
FLAGGED = "flagged"


# The ways the model is asked to correct an answer, by the name of the variant.
CORRECTIONS = {
    "plain": messages.CRITIC_CORRECTION,
    "compute": messages.CRITIC_CORRECTION_COMPUTE,
}


def correction_request(numbers: list[str], variant: str | None = None) -> str:
    """What the model is told when its answer holds numbers no tool returned.

    variant is the wording; the one in use (config) unless named. An agent
    without run_sql asks for the first wording, which does not send the
    model to it.

    Args:
        numbers (list[str]): The numbers in the answer that no tool returned.
        variant (str | None): The wording to use; the configured variant when None.

    Returns:
        The message that asks the model to correct its answer.
    """
    wording = CORRECTIONS[variant or config.CRITIC_CORRECTION_VARIANT]
    return wording.format(numbers=", ".join(numbers))


def unsupported(
    text: str, tool_results: list[tuple[str, object]], question: str
) -> list[str]:
    """The numbers in the answer that no tool of this question returned.

    Args:
        text (str): The model's answer.
        tool_results (list[tuple[str, object]]): The (tool name, result) pairs of this
            question.
        question (str): The person's question; numbers they typed themselves are not
            counted.

    Returns:
        The numbers in the answer that no tool returned.
    """
    return ungrounded_numbers(text, tool_results, question)


async def review(
    agent,
    context,
    question: str,
    text: str,
    log,
    language: Language = DEFAULT_LANGUAGE,
    variant: str | None = None,
) -> tuple[str, str]:
    """Check the numbers of an answer; ask for a correction a limited number
    of times; note what could not be traced.

    Returns the text to show and the status (ok, corrected or flagged). The
    cost of a correction is added to the run's log.

    Args:
        agent: The agent that wrote the answer.
        context: Its conversation context.
        question (str): The person's question.
        text (str): The agent's answer.
        log: The run log; correction runs are added to it.
        language (Language): The session's language.
        variant (str | None): The correction wording; the configured variant when None.

    Returns:
        The final text and the check's status.
    """
    numbers = unsupported(text, log.tool_results, question)
    status = OK
    for _ in range(config.CRITIC_MAX_CORRECTIONS if numbers else 0):
        text, correction = await run_agent(
            agent, context, correction_request(numbers, variant)
        )
        log.absorb(correction)
        numbers = unsupported(text, log.tool_results, question)
        status = CORRECTED
        if not numbers:
            break
    if numbers:
        status = FLAGGED
        text = f"{text}\n\n{catalog(language).CRITIC_NOTE}"
    # Counts and a code only: the numbers themselves stay in the answer.
    logger.info("critic status=%s unsupported=%d", status, len(numbers))
    tracing.mark(critic=status)
    return text, status
