"""Tests for approval tokens."""

from decimal import Decimal

import pytest

from src.guardrails.approval import Approvals, ReturnAction

ACTION = ReturnAction("o_one", "damaged", Decimal("115.00"))


def approved_token(approvals, action=ACTION):
    approvals.request(action)
    return approvals.approve()


def test_token_fits_the_action_it_was_issued_for():
    approvals = Approvals()
    token = approved_token(approvals)

    assert approvals.consume(token, ACTION) is True


def test_no_token_is_no_approval():
    approvals = Approvals()
    approvals.request(ACTION)

    assert approvals.consume(None, ACTION) is False


@pytest.mark.parametrize("made_up", ["", "approved", "yes", "onaylandı", "true"])
def test_made_up_token_is_refused(made_up):
    approvals = Approvals()
    approved_token(approvals)

    assert approvals.consume(made_up, ACTION) is False


def test_token_works_only_once():
    approvals = Approvals()
    token = approved_token(approvals)
    approvals.consume(token, ACTION)

    assert approvals.consume(token, ACTION) is False


@pytest.mark.parametrize(
    "other",
    [
        ReturnAction("o_two", "damaged", Decimal("115.00")),
        ReturnAction("o_one", "changed_mind", Decimal("115.00")),
        ReturnAction("o_one", "damaged", Decimal("115.01")),
    ],
)
def test_token_does_not_fit_another_order_reason_or_amount(other):
    approvals = Approvals()
    token = approved_token(approvals)

    assert approvals.consume(token, other) is False


def test_token_tried_on_the_wrong_action_is_gone():
    approvals = Approvals()
    token = approved_token(approvals)
    approvals.consume(token, ReturnAction("o_two", "damaged", Decimal("115.00")))

    assert approvals.consume(token, ACTION) is False


def test_token_of_another_session_is_refused():
    token = approved_token(Approvals())

    assert Approvals().consume(token, ACTION) is False


def test_nothing_to_approve_issues_no_token():
    with pytest.raises(LookupError):
        Approvals().approve()


def test_approving_clears_what_was_waiting():
    approvals = Approvals()
    approved_token(approvals)

    assert approvals.awaiting is None
    with pytest.raises(LookupError):
        approvals.approve()


def test_rejected_action_cannot_be_approved_afterwards():
    approvals = Approvals()
    approvals.request(ACTION)
    approvals.reject()

    with pytest.raises(LookupError):
        approvals.approve()


def test_tokens_are_different_and_long():
    approvals = Approvals()
    first = approved_token(approvals)
    second = approved_token(approvals)

    assert first != second
    assert len(first) >= 32
