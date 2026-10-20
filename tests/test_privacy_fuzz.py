"""Privacy fuzzing: personal data written so a pattern might miss it, sent
through every guard that cleans text before it leaves.

The guards match by shape and against known values, and say so. These
tests record, case by case, what each guard catches today. A case it
misses is marked as an expected failure, strictly: when a change makes a
guard catch it, the test fails until the mark is removed, so the table in
the security review stays true.
"""

import pytest

from src import tracing
from src.guardrails.outbound import Redactor
from src.guardrails.pii import mask_raw_ids
from tests.privacy_fuzz_cases import KNOWN_VALUES, Case, cases, leaks

ALIAS = "SIP-1"


def outbound(text: str) -> str:
    """What reaches the model provider from a customer session."""
    redactor = Redactor(alias_for=lambda raw_id: ALIAS, known_values=KNOWN_VALUES)
    return redactor.redact(text)[0]


def ticket(text: str) -> str:
    """What a ticket keeps, logs and shows the rep, from a model's summary."""
    return mask_raw_ids(text)


GUARDS = {"outbound": outbound, "trace": tracing.scrub, "ticket": ticket}

# What each guard catches today, by (kind, variant).
SHAPE_GUARD_CATCHES = {
    ("id", "plain"),
    ("id", "upper case"),
    ("email", "plain"),
    ("email", "cyrillic look-alikes"),
    ("phone", "plain"),
    ("phone", "grouped"),
    ("phone", "international"),
    ("phone", "one digit at a time"),
    ("tckn", "grouped"),
    ("city", "plain"),
    ("city", "upper case"),
    ("zip", "plain"),
    # Since the text is normalised and known values are matched without
    # accents.
    ("id", "zero-width inside"),
    ("id", "full-width digits"),
    ("email", "full-width at"),
    ("email", "zero-width inside"),
    ("phone", "full-width digits"),
    ("phone", "zero-width inside"),
    ("city", "with accents"),
    ("city", "zero-width inside"),
}
CAUGHT_TODAY = {
    "outbound": SHAPE_GUARD_CATCHES,
    "trace": SHAPE_GUARD_CATCHES,
    "ticket": {("id", "plain"), ("id", "upper case")},
}


@pytest.fixture(autouse=True)
def personal_values_in_traces():
    """The session's values, registered as a customer session does."""
    before = dict(tracing._personal_values)
    tracing.register_personal_values(KNOWN_VALUES)
    yield
    tracing._personal_values.clear()
    tracing._personal_values.update(before)


def fuzz_params():
    for guard in GUARDS:
        for case in cases():
            known_miss = (case.kind, case.variant) not in CAUGHT_TODAY[guard]
            marks = (
                pytest.mark.xfail(strict=True, reason="known miss, see the table")
                if known_miss
                else ()
            )
            yield pytest.param(
                guard, case, marks=marks, id=f"{guard}-{case.kind}-{case.variant}"
            )


@pytest.mark.parametrize(("guard", "case"), list(fuzz_params()))
def test_hidden_personal_data_does_not_get_past_the_guard(guard: str, case: Case):
    assert not leaks(GUARDS[guard](case.text), case)


def test_every_case_is_listed_once():
    keys = [(case.kind, case.variant) for case in cases()]

    assert len(keys) == len(set(keys))
    for guard in GUARDS:
        assert CAUGHT_TODAY[guard] <= set(keys), guard


def test_a_plain_message_passes_every_guard_unchanged():
    text = "SIP-2 siparişim 2018-08-20'de geldi, 133,14 BRL iade istiyorum."

    for guard in GUARDS.values():
        assert guard(text) == text
