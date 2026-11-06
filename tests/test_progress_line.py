"""Tests for the progress line of a test run in a terminal."""

import os
import pty
import re
import subprocess
import sys
from pathlib import Path

from tests.progress_line import GREEN, RED, RESET, REWRITE, active, progress_line

ROOT = Path(__file__).resolve().parent.parent
COUNTS = {"passed": 1210, "failed": 0, "xfailed": 24}

SAMPLE = """
import pytest

def test_one(): pass
def test_two(): pass
def test_three(): pass
def test_fails(): assert False

@pytest.mark.xfail(strict=True)
def test_expected_to_fail(): assert False
"""
SAMPLE_CONFTEST = """
import pytest

from tests import progress_line

@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    progress_line.register(config)
"""


NONE = {"passed": 0, "failed": 0, "xfailed": 0}


def start_of_bar_fills_with_share_done(done, total):
    return progress_line(done, total, NONE, 0, "", 200).split("  ✓")[0]


def test_bar_fills_with_share_done():

    assert start_of_bar_fills_with_share_done(0, 4) == "[0/4] ░░░░░░░░░░   0%"
    assert start_of_bar_fills_with_share_done(1, 4) == "[1/4] ██░░░░░░░░  25%"
    assert (
        start_of_bar_fills_with_share_done(1234, 2125) == "[1234/2125] ██████░░░░  58%"
    )
    assert (
        start_of_bar_fills_with_share_done(2125, 2125) == "[2125/2125] ██████████ 100%"
    )


def test_line_shows_counts_time_and_file():
    line = progress_line(1234, 2125, COUNTS, 151, "tests/test_x.py", 200)

    assert line == (
        "[1234/2125] ██████░░░░  58%  ✓ 1210  ✗ 0  x 24   2:31  tests/test_x.py"
    )


def test_line_is_cut_to_terminal_width():
    line = progress_line(1234, 2125, COUNTS, 151, "tests/test_x.py", 40)

    assert len(line) == 39


def test_bar_turns_red_on_failure():
    passing = progress_line(1, 4, NONE, 0, "tests/test_x.py", 200, colour=True)
    failing = progress_line(
        1, 4, {**NONE, "failed": 1}, 0, "tests/test_x.py", 200, colour=True
    )
    cut = progress_line(1, 4, NONE, 0, "tests/test_x.py", 30, colour=True)

    assert f"{GREEN}██{RESET}" in passing
    assert f"{RED}██{RESET}" in failing
    assert f"{RED}✗ 1{RESET}" in failing
    assert len(re.sub(r"\x1b\[[0-9;]*m", "", cut)) == 29


class Stream:
    def __init__(self, terminal: bool) -> None:
        self.terminal = terminal

    def isatty(self) -> bool:
        return self.terminal


class Config:
    def __init__(self, verbosity: int) -> None:
        self.verbosity = verbosity
        self.pluginmanager = self

    def get_verbosity(self) -> int:
        return self.verbosity

    def get_plugin(self, name: str) -> object:
        return object()


def test_only_default_terminal_gets_the_line():
    assert active(Config(0), Stream(terminal=True))
    assert not active(Config(0), Stream(terminal=False))
    assert not active(Config(1), Stream(terminal=True))
    assert not active(Config(-1), Stream(terminal=True))


def run_sample(tmp_path: Path, terminal: bool, workers: int = 0) -> str:
    """Run a small test file with the progress line; its output as text."""
    (tmp_path / "test_sample.py").write_text(SAMPLE)
    (tmp_path / "test_second.py").write_text("def test_four(): pass\n")
    (tmp_path / "conftest.py").write_text(SAMPLE_CONFTEST)
    command = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", str(tmp_path)]
    if workers:
        command += ["-n", str(workers)]
    env = {**os.environ, "PYTHONPATH": str(ROOT), "COLUMNS": "120"}
    if not terminal:
        done = subprocess.run(
            command, cwd=tmp_path, env=env, capture_output=True, text=True, check=False
        )
        return done.stdout
    leader, follower = pty.openpty()
    process = subprocess.Popen(
        command, cwd=tmp_path, env=env, stdout=follower, stderr=follower
    )
    os.close(follower)
    chunks = []
    while True:
        try:
            chunk = os.read(leader, 4096)
        except OSError:  # the run closed the terminal
            break
        if not chunk:
            break
        chunks.append(chunk)
    process.wait()
    os.close(leader)
    return b"".join(chunks).decode()


def test_terminal_shows_line_and_failure(tmp_path):
    output = run_sample(tmp_path, terminal=True)

    assert REWRITE in output
    plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
    assert "[6/6] ██████████ 100%  ✓ 4  ✗ 1  x 1" in plain
    assert "✗ test_sample.py::test_fails" in plain
    # One line from the first test to the last, also from one file to the
    # next; only the failure gets a line of its own.
    updates = plain[plain.index("[1/6]") : plain.index("[6/6]")]
    assert updates.count("\n") == 1
    # pytest's own dots are gone; its summary is still there.
    assert "test_sample.py ..." not in plain
    assert "1 failed, 4 passed, 1 xfailed" in plain


def test_line_counts_tests_of_all_workers(tmp_path):
    output = run_sample(tmp_path, terminal=True, workers=2)

    plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
    assert "[6/6] ██████████ 100%  ✓ 4  ✗ 1  x 1" in plain
    assert "✗ test_sample.py::test_fails" in plain
    assert "1 failed, 4 passed, 1 xfailed" in plain


def test_file_output_looks_like_pytest(tmp_path):
    output = run_sample(tmp_path, terminal=False)

    assert REWRITE not in output
    assert "test_sample.py ...Fx" in output
    assert "1 failed, 4 passed, 1 xfailed" in output
