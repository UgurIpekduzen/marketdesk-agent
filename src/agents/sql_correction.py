"""Limits how often an agent may retry a failed SQL query.

Within one question the agent may run a query, and if it fails correct it
at most config.SQL_MAX_CORRECTIONS times. After that no further query is
run for that question: the agent has to say that it could not answer, and
the queries it tried are shown. The count starts again with every new
question.
"""

import config

LIMIT_REACHED = {
    "error": "SQL_CORRECTION_LIMIT",
    "message": (
        "The query failed and the allowed corrections are used up. Do not "
        "call run_sql again for this question: tell the user that you could "
        "not answer it."
    ),
}


class SqlCorrectionLimit:
    def __init__(self, max_corrections: int = config.SQL_MAX_CORRECTIONS) -> None:
        # The first attempt plus the corrections.
        self._max_failures = max_corrections + 1
        self.failed_queries: list[str] = []

    def reset(self) -> None:
        """Forget all failures; called at the start of every question."""
        self.failed_queries = []

    @property
    def exhausted(self) -> bool:
        """True once the first attempt and every correction have failed."""
        return len(self.failed_queries) >= self._max_failures

    @property
    def corrections_left(self) -> int:
        return max(self._max_failures - len(self.failed_queries), 0)

    def record_failure(self, query: str) -> None:
        self.failed_queries.append(query)
