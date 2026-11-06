"""A progress bar at the bottom of the terminal while a run goes on.

    [1/8]   D1  ok    check_return_eligibility   live +3 (system 3)   0:04
    [2/8]   D2  FAIL  search_policies   failed: text   live +3 (system 6)   0:27
    [2/8] ██░░░░░░░░  25%  ✓ 1  ✗ 1   live 6   0:31   D3

The line of each example is written once and stays; the bar under them is
rewritten in place. Only when the run writes to a terminal: through tee, to
a log or in CI the lines are written as before, each with its own bar, and
nothing is rewritten.

Held-out examples move the bar but are not counted as passed or failed,
so the counts never tell how one of them went.
"""

import functools
import logging
import os
import sys
import time

# Moves to the start of the line and clears it, so the next text replaces it.
REWRITE = "\r\x1b[K"
BAR_WIDTH = 10
# ANSI colours of the parts of the bar.
GREEN, RED, CYAN, DIM, RESET = "\x1b[32m", "\x1b[31m", "\x1b[36m", "\x1b[90m", "\x1b[0m"


class LiveBar:
    """A progress line that updates in place on a terminal."""

    def __init__(self, total: int, stream=None) -> None:
        self.stream = stream or sys.stdout
        self.active = self.stream.isatty()
        # In colour, unless the person asked for none (https://no-color.org).
        self.colour = self.active and not os.environ.get("NO_COLOR")
        self.total = total
        self.done = 0
        self.passed = 0
        self.failed = 0
        self.live = 0
        self.current = ""
        self.started = time.monotonic()
        self._handlers: list[tuple[logging.Handler, object]] = []
        if self.active:
            self._keep_log_lines_above()

    def _keep_log_lines_above(self) -> None:
        """Clear the bar before a log line and draw it again after."""
        for handler in logging.getLogger().handlers:
            original = handler.emit
            handler.emit = functools.partial(self._emit_above_bar, original)
            self._handlers.append((handler, original))

    def _emit_above_bar(self, original, record) -> None:
        self._write(REWRITE)
        original(record)
        self._draw()

    def _write(self, text: str) -> None:
        self.stream.write(text)
        self.stream.flush()

    def line(self) -> str:
        """The bar as it stands."""
        share = self.done / self.total if self.total else 1.0
        filled = round(share * BAR_WIDTH)
        minutes, seconds = divmod(int(time.monotonic() - self.started), 60)

        return (
            f"[{self.done:>{len(str(self.total))}}/{self.total}] "
            + self._paint("█" * filled, RED if self.failed else GREEN)
            + self._paint("░" * (BAR_WIDTH - filled), DIM)
            + f" {share:>4.0%}  "
            + self._paint(f"✓ {self.passed}", GREEN)
            + "  "
            + self._paint(f"✗ {self.failed}", RED if self.failed else DIM)
            + self._paint(f"   live {self.live}   {minutes}:{seconds:02d}   ", DIM)
            + self._paint(self.current, CYAN)
        )

    def _paint(self, text: str, code: str) -> str:
        return f"{code}{text}{RESET}" if self.colour and code and text else text

    def _draw(self) -> None:
        if self.active:
            # The cursor goes back to the start of the line: what another
            # process writes (the order server logs on its own) covers the
            # bar instead of running on after it, until the bar is drawn
            # again.
            self._write(REWRITE + self.line() + "\r")

    def begin(self, example_id: str) -> None:
        """An example starts: name it on the bar."""
        self.current = example_id
        self._draw()

    def report(self, text: str) -> None:
        """Write an example's line above the bar, or as a plain line."""
        if self.active:
            self._write(REWRITE + text + "\n")
            self._draw()
        else:
            print(text, file=self.stream, flush=True)

    def finish(self, success: bool | None, live: int) -> None:
        """An example ended. success is None for a held-out example."""
        self.done += 1
        if success is not None:
            self.passed += success
            self.failed += not success
            self.live = live
        self.current = ""
        self._draw()

    def close(self) -> None:
        """Leave the last bar on its line and give the log back its handlers."""
        if self.active:
            self._write(REWRITE + self.line() + "\n")
        for handler, original in self._handlers:
            handler.emit = original
        self._handlers.clear()
