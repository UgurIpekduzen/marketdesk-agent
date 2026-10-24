"""A pytest plugin that breaks one guard for the whole test run.

Used by eval/mutations.py: `pytest -p eval.mutation_plugin` with the name of
the guard in the environment variable MARKETDESK_MUTATION. Without the
variable it does nothing. For a guard that lives in the order server, the
server the tests start is the mutated one (eval/mutated_server.py).
"""

import os
from contextlib import ExitStack

from eval.mutations import MUTATION_VARIABLE, apply_everywhere

_stack = ExitStack()


def pytest_configure(config) -> None:
    name = os.environ.get(MUTATION_VARIABLE)
    if name:
        apply_everywhere(name, _stack)


def pytest_unconfigure(config) -> None:
    _stack.close()
