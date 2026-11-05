"""Tests for the hourly question limit shared by all visitors."""

import functools
import threading

import pytest

from src.ui.question_limit import (
    WINDOW_SECONDS,
    QuestionLimit,
    QuestionLimitReachedError,
)


class Clock:
    def __init__(self) -> None:
        self.seconds = 1000.0

    def __call__(self) -> float:
        return self.seconds


def test_limit_passes_then_refuses():
    limit = QuestionLimit(per_hour=3, clock=Clock())

    for _ in range(3):
        limit.take()

    with pytest.raises(QuestionLimitReachedError):
        limit.take()


def test_old_questions_stop_counting():
    clock = Clock()
    limit = QuestionLimit(per_hour=2, clock=clock)
    limit.take()
    clock.seconds += 1800
    limit.take()

    clock.seconds += WINDOW_SECONDS - 1800 - 1
    with pytest.raises(QuestionLimitReachedError):
        limit.take()

    clock.seconds += 1
    limit.take()


def test_a_refused_question_takes_no_place():
    clock = Clock()
    limit = QuestionLimit(per_hour=1, clock=clock)
    limit.take()
    for _ in range(5):
        with pytest.raises(QuestionLimitReachedError):
            limit.take()

    clock.seconds += WINDOW_SECONDS
    limit.take()


def ask_of_parallel_visitors_respect_the_limit(limit, passed) -> None:
    for _ in range(20):
        try:
            limit.take()
        except QuestionLimitReachedError:
            continue
        passed.append(1)


def test_parallel_visitors_respect_the_limit():
    limit = QuestionLimit(per_hour=50)
    passed = []

    threads = [
        threading.Thread(
            target=functools.partial(
                ask_of_parallel_visitors_respect_the_limit, limit, passed
            )
        )
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(passed) == 50
