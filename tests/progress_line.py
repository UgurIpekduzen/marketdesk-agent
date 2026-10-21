"""One progress line for a test run in a terminal, updated in place.

    [1234/2125] ███████░░░  58%  ✓ 1210  ✗ 0  x 24   2:31  tests/test_policy_index.py

pytest's own dots and file lines are left out; a failing test gets a line of
its own above the progress line, and pytest's summary follows at the end as
usual. With workers (-n, pytest-xdist) the line counts the tests of all of
them. Only in a terminal and at the default verbosity: when the output goes
to a file or a pipe (a log, tee, CI), or with -v or -q, pytest writes as it
always does.
"""

import shutil
import time

import pytest

BAR_WIDTH = 10
# Moves to the start of the line and clears it, so the next text replaces it.
REWRITE = "\r\x1b[K"


# ANSI colours of the parts of the line.
GREEN, RED, YELLOW, CYAN, DIM, RESET = (
    "\x1b[32m",
    "\x1b[31m",
    "\x1b[33m",
    "\x1b[36m",
    "\x1b[90m",
    "\x1b[0m",
)


def parts(
    done: int, total: int, counts: dict[str, int], seconds: float, current: str
) -> list[tuple[str, str]]:
    """The pieces of the line, each with the colour it is drawn in."""
    share = done / total if total else 1.0
    filled = round(share * BAR_WIDTH)
    minutes, rest = divmod(int(seconds), 60)
    folder, _, name = current.rpartition("/")
    failed, xfailed = counts["failed"], counts["xfailed"]
    return [
        (f"[{done:>{len(str(total))}}/{total}] ", ""),
        ("█" * filled, RED if failed else GREEN),
        ("░" * (BAR_WIDTH - filled), DIM),
        (f" {share:>4.0%}  ", ""),
        (f"✓ {counts['passed']}", GREEN),
        ("  ", ""),
        (f"✗ {failed}", RED if failed else DIM),
        ("  ", ""),
        (f"x {xfailed}", YELLOW if xfailed else DIM),
        (f"   {minutes}:{rest:02d}  ", DIM),
        (f"{folder}/" if folder else "", CYAN),
        (name, ""),
    ]


def render(pieces: list[tuple[str, str]], width: int, colour: bool) -> str:
    """The pieces as one line cut to the width; colours do not count."""
    room = max(width - 1, 0)
    line = []
    for text, code in pieces:
        text = text[:room]
        room -= len(text)
        if text:
            line.append(f"{code}{text}{RESET}" if colour and code else text)
    return "".join(line)


def progress_line(
    done: int,
    total: int,
    counts: dict[str, int],
    seconds: float,
    current: str,
    width: int,
    colour: bool = False,
) -> str:
    """The progress line, cut to the width of the terminal."""
    return render(parts(done, total, counts, seconds, current), width, colour)


def active(config: pytest.Config, stream=None) -> bool:
    """Whether the run gets the progress line instead of pytest's own output."""
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return False
    # By now pytest has replaced sys.stdout to capture the tests' output; its
    # terminal writer still holds the stream the run was started with.
    stream = stream or reporter._tw._file
    return stream.isatty() and config.get_verbosity() == 0


class ProgressLine:
    def __init__(self, config: pytest.Config) -> None:
        self.reporter = config.pluginmanager.get_plugin("terminalreporter")
        # Nor pytest's own [ 45%] at the end of its lines, nor the new line
        # and file name it writes when the run reaches the next file.
        self.reporter._show_progress_info = False
        self.reporter.showfspath = False
        self.total = 0
        self.done = 0
        self.counts = {"passed": 0, "failed": 0, "xfailed": 0}
        self.started = time.monotonic()

    def draw(self, current: str) -> None:
        width = shutil.get_terminal_size().columns
        line = progress_line(
            self.done,
            self.total,
            self.counts,
            time.monotonic() - self.started,
            current,
            width,
            # pytest's own choice, which follows NO_COLOR and the like.
            colour=self.reporter._tw.hasmarkup,
        )
        self.reporter.write(REWRITE + line, flush=True)

    @pytest.hookimpl(trylast=True)
    def pytest_collection_finish(self, session: pytest.Session) -> None:
        # With workers (pytest-xdist) this process collects nothing; the
        # workers report what they collected below.
        if session.items:
            self.total = len(session.items)
        self.started = time.monotonic()
        self.reporter.write("\n")

    @pytest.hookimpl(optionalhook=True)
    def pytest_xdist_node_collection_finished(self, node, ids: list[str]) -> None:
        # Every worker collects the whole run; the tests are shared out.
        self.total = len(ids)

    @pytest.hookimpl(wrapper=True)
    def pytest_report_teststatus(self, report: pytest.TestReport):
        # No letter and no word: pytest writes nothing for the test, but
        # still counts it for the summary.
        category, _, _ = yield
        return category, "", ""

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.failed:
            self.counts["failed"] += 1
            self.reporter.write(f"{REWRITE}✗ {report.nodeid}\n", red=True)
        elif report.when == "call":
            if hasattr(report, "wasxfail"):
                self.counts["xfailed"] += 1
            elif report.passed:
                self.counts["passed"] += 1

    def pytest_runtest_logfinish(self, nodeid: str) -> None:
        self.done += 1
        self.draw(nodeid.split("::", maxsplit=1)[0])

    @pytest.hookimpl(wrapper=True)
    def pytest_runtestloop(self, session: pytest.Session):
        result = yield
        self.reporter.write("\n")
        return result


def register(config: pytest.Config) -> None:
    """Put the progress line in place of pytest's output, when it is wanted."""
    if active(config):
        config.pluginmanager.register(ProgressLine(config), "progress-line")
