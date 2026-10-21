"""Tests for the progress bar at the bottom of the terminal during a run."""

import io
import logging
import re

from eval.live_bar import GREEN, RED, RESET, REWRITE, LiveBar


def plain(text: str) -> str:
    """The text without its colours."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_written_to_a_file_the_lines_come_as_before_and_nothing_is_rewritten():
    stream = io.StringIO()
    bar = LiveBar(2, stream)

    bar.begin("D1")
    bar.report("[1/2] █████░░░░░  50%   D1  ok")
    bar.finish(True, 3)
    bar.close()

    assert stream.getvalue() == "[1/2] █████░░░░░  50%   D1  ok\n"


def test_in_a_terminal_the_lines_stay_and_the_bar_is_rewritten_under_them():
    stream = Terminal()
    bar = LiveBar(4, stream)

    bar.begin("D1")
    bar.report("[1/4]   D1  ok")
    bar.finish(True, 3)
    bar.begin("D2")

    output = plain(stream.getvalue())
    assert f"{REWRITE}[1/4]   D1  ok\n" in output
    last = output.rsplit(REWRITE, 1)[1]
    assert last.startswith("[1/4] ██░░░░░░░░  25%  ✓ 1  ✗ 0   live 3   0:00")
    # Drawn with the cursor back at the start of the line, so another
    # process's output covers the bar instead of running on after it.
    assert last.endswith("D2\r")


def test_a_held_out_example_moves_the_bar_but_is_not_counted():
    bar = LiveBar(3, Terminal())

    bar.finish(True, 3)
    bar.finish(None, 7)
    bar.finish(False, 9)

    assert plain(bar.line()).startswith("[3/3] ██████████ 100%  ✓ 1  ✗ 1   live 9")


def test_a_log_line_clears_the_bar_and_the_bar_comes_back_after_it():
    stream = Terminal()
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        bar = LiveBar(2, stream)
        bar.begin("D1")
        logging.getLogger("x").warning("a log line")
        bar.close()
        # Given back: a later log line touches the bar no more.
        before = stream.getvalue()
        logging.getLogger("x").warning("after the run")
    finally:
        root.removeHandler(handler)

    assert "a log line" in log_stream.getvalue()
    # Drawn, cleared for the log line (once per handler), drawn again.
    assert before.count(REWRITE) >= 3
    assert plain(before).rstrip("\n").endswith("D1")
    assert "a log line" not in before
    assert stream.getvalue() == before


def test_in_colour_the_bar_turns_red_once_an_example_fails(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    bar = LiveBar(2, Terminal())
    bar.finish(True, 1)
    passing = bar.line()
    bar.finish(False, 2)
    failing = bar.line()

    assert f"{GREEN}█████{RESET}" in passing
    assert f"{RED}██████████{RESET}" in failing
    assert f"{RED}✗ 1{RESET}" in failing


def test_no_colour_when_asked_for_none_or_not_in_a_terminal(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")

    assert "\x1b[" not in LiveBar(2, Terminal()).line()
    monkeypatch.delenv("NO_COLOR")
    assert "\x1b[" not in LiveBar(2, io.StringIO()).line()
