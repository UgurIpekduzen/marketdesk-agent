"""Tests for the limit on SQL corrections."""

import config
from src.agents.sql_correction import LIMIT_REACHED, SqlCorrectionLimit


def test_first_attempt_and_two_corrections_may_fail_before_the_limit():
    limit = SqlCorrectionLimit()

    states = []
    for query in ("first", "second", "third"):
        states.append(limit.exhausted)
        limit.record_failure(query)

    assert config.SQL_MAX_CORRECTIONS == 2
    assert states == [False, False, False]
    assert limit.exhausted is True
    assert limit.failed_queries == ["first", "second", "third"]


def test_corrections_left_counts_down():
    limit = SqlCorrectionLimit()

    left = [limit.corrections_left]
    for query in ("a", "b", "c", "d"):
        limit.record_failure(query)
        left.append(limit.corrections_left)

    assert left == [3, 2, 1, 0, 0]


def test_reset_starts_again():
    limit = SqlCorrectionLimit()
    for query in ("a", "b", "c"):
        limit.record_failure(query)

    limit.reset()

    assert limit.exhausted is False
    assert limit.failed_queries == []


def test_the_number_of_corrections_can_be_set():
    limit = SqlCorrectionLimit(max_corrections=0)

    limit.record_failure("only attempt")

    assert limit.exhausted is True


def test_refusal_tells_the_model_to_stop():
    assert LIMIT_REACHED["error"] == "SQL_CORRECTION_LIMIT"
    assert "Do not call run_sql again" in LIMIT_REACHED["message"]
