"""Tests for the pool of chat sessions: stand-in sessions on a clock the
test moves, and one real session with its order server process."""

import threading

import pytest

from src.ui.chat_session import ChatSession
from src.ui.session_pool import SessionLimitReachedError, SessionPool
from tests.fakes import FakeLLM
from tests.synthetic_data import ALICE
from tests.test_chat_session import child_processes


class Clock:
    def __init__(self) -> None:
        self.seconds = 1000.0

    def __call__(self) -> float:
        return self.seconds


class StandIn:
    """What the pool needs of a session."""

    def __init__(self, clock: Clock) -> None:
        self.last_used = clock.seconds
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def clock():
    return Clock()


def test_idle_session_is_closed(clock):
    pool = SessionPool(idle_seconds=900, max_open=5, clock=clock)
    session = pool.open(lambda: StandIn(clock))

    clock.seconds += 900
    assert pool.close_idle() == 0
    assert not session.closed

    clock.seconds += 1
    assert pool.close_idle() == 1
    assert session.closed
    assert pool.open_count == 0


def test_a_session_in_use_stays_open(clock):
    pool = SessionPool(idle_seconds=900, max_open=5, clock=clock)
    session = pool.open(lambda: StandIn(clock))

    clock.seconds += 800
    session.last_used = clock.seconds
    clock.seconds += 800

    assert pool.close_idle() == 0
    assert not session.closed


def test_full_pool_refuses_new_sessions(clock):
    pool = SessionPool(idle_seconds=900, max_open=2, clock=clock)
    pool.open(lambda: StandIn(clock))
    pool.open(lambda: StandIn(clock))
    started = []

    with pytest.raises(SessionLimitReachedError):
        pool.open(lambda: started.append(1) or StandIn(clock))

    assert started == []
    assert pool.open_count == 2


def test_idle_sessions_make_room(clock):
    pool = SessionPool(idle_seconds=900, max_open=1, clock=clock)
    old = pool.open(lambda: StandIn(clock))
    clock.seconds += 901

    new = pool.open(lambda: StandIn(clock))

    assert old.closed
    assert not new.closed
    assert pool.open_count == 1


def test_closed_session_frees_its_place(clock):
    pool = SessionPool(idle_seconds=900, max_open=1, clock=clock)
    pool.open(lambda: StandIn(clock)).close()

    pool.open(lambda: StandIn(clock))

    assert pool.open_count == 1


def fail_of_failed_start_takes_no_place():
    raise OSError("server did not start")


def test_failed_start_takes_no_place(clock):
    pool = SessionPool(idle_seconds=900, max_open=1, clock=clock)

    with pytest.raises(OSError):
        pool.open(fail_of_failed_start_takes_no_place)

    assert pool.open_count == 0
    pool.open(lambda: StandIn(clock))


def test_background_check_closes_idle(clock):
    pool = SessionPool(idle_seconds=900, max_open=5, clock=clock)
    session = pool.open(lambda: StandIn(clock))
    clock.seconds += 901
    closed = threading.Event()
    session.close = closed.set

    pool.start_checking(every_seconds=0.01)
    try:
        assert closed.wait(timeout=5)
    finally:
        pool.stop()


def test_closing_stops_the_order_server(synthetic_db_path, fake_policy_index):
    pool = SessionPool(idle_seconds=900, max_open=5)
    before = child_processes()
    session = pool.open(
        lambda: ChatSession(synthetic_db_path, fake_policy_index, ALICE, FakeLLM())
    )
    try:
        assert len(child_processes() - before) == 1
        session.last_used -= 901

        assert pool.close_idle() == 1

        assert session.closed
        assert child_processes() == before
    finally:
        session.close()
