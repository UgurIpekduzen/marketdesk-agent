"""Tests for the daily budget of model calls shared by all visitors."""

import threading

import pytest

from src.failures import DAILY_BUDGET, failure_code
from src.ui.call_budget import WINDOW_SECONDS, CallBudget, CallBudgetReached


class Clock:
    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        return self.seconds


def test_calls_are_counted_up_to_the_budget():
    budget = CallBudget(per_day=3)
    for _ in range(3):
        budget.take()

    with pytest.raises(CallBudgetReached):
        budget.take()


def test_checking_counts_no_call():
    budget = CallBudget(per_day=1)
    for _ in range(5):
        budget.check()

    budget.take()

    with pytest.raises(CallBudgetReached):
        budget.check()


def test_call_is_returned_after_a_day():
    clock = Clock()
    budget = CallBudget(per_day=2, clock=clock)
    budget.take()
    clock.seconds = 3600
    budget.take()

    clock.seconds = WINDOW_SECONDS - 1
    with pytest.raises(CallBudgetReached):
        budget.take()
    clock.seconds = WINDOW_SECONDS
    budget.take()
    with pytest.raises(CallBudgetReached):
        budget.take()


def test_parallel_calls_respect_the_budget():
    budget = CallBudget(per_day=50)
    refused = []

    def call():
        try:
            budget.take()
        except CallBudgetReached:
            refused.append(1)

    threads = [threading.Thread(target=call) for _ in range(80)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(refused) == 30


def test_used_up_budget_has_own_failure_code():
    budget = CallBudget(per_day=0)

    with pytest.raises(CallBudgetReached) as refused:
        budget.take()

    assert failure_code(refused.value) == DAILY_BUDGET
