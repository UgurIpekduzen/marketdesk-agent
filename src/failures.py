"""What kind of provider failure an exception is, as a fixed code.

The page turns the code into a message for the visitor, and tracing puts it
on the span, so a trace can be found by kind of failure without carrying the
error text.
"""

from src.guardrails.guarded_llm import API_KEY_VARIABLES

QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
PROVIDER_BUSY = "PROVIDER_BUSY"
KEY_REFUSED = "KEY_REFUSED"
KEY_NOT_SET = "KEY_NOT_SET"
DAILY_BUDGET = "DAILY_BUDGET"
# Any other failure of a run.
RUN_FAILED = "RUN_FAILED"

# Said by the page's daily budget of model calls when it is used up.
BUDGET_MARK = "daily model call budget"

# Marks in an error text, lower case, and the code for them.
FAILURE_MARKS = (
    ((BUDGET_MARK,), DAILY_BUDGET),
    (("429", "resource_exhausted", "quota", "rate limit"), QUOTA_EXCEEDED),
    (
        ("503", "unavailable", "overloaded", "high demand", "connecterror"),
        PROVIDER_BUSY,
    ),
    # The provider refused the key: Gemini and Groq say it in these words.
    (
        (
            "api_key_invalid",
            "api key not valid",
            "invalid_api_key",
            "invalid api key",
            "permission_denied",
            "unauthenticated",
        ),
        KEY_REFUSED,
    ),
    # No key at all: reading its environment variable failed.
    (
        tuple(f"keyerror '{name.lower()}'" for name in API_KEY_VARIABLES.values()),
        KEY_NOT_SET,
    ),
)


def failure_code(failure: BaseException) -> str:
    """The code of a failure, read from the whole chain of exceptions."""
    # The provider's error is often wrapped by the framework.
    chain = []
    current: BaseException | None = failure
    while current is not None and len(chain) < 10:
        chain.append(f"{type(current).__name__} {current}".lower())
        current = current.__cause__ or current.__context__
    text = " ".join(chain)
    for marks, code in FAILURE_MARKS:
        if any(mark in text for mark in marks):
            return code
    return RUN_FAILED
