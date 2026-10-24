"""The evaluation runner with one guard broken, for eval/mutations.py only.

Usage:  MARKETDESK_MUTATION_ROWS=rows.json python -m eval.mutated_eval NAME RUN_EVAL_ARGS...

Breaks the guard, then runs eval/run_eval.py with the arguments. The rows of
the run (id, split, success) are written to the file in the environment
variable; no results file is written (give --only).
"""

import json
import os
import sys
from contextlib import ExitStack

from eval import run_eval
from eval.mutations import apply_everywhere

ROWS_VARIABLE = "MARKETDESK_MUTATION_ROWS"


def main(name: str, arguments: list[str]) -> int:
    rows_path = os.environ[ROWS_VARIABLE]
    original = run_eval.summarise_by_split

    def keep_rows(rows):
        with open(rows_path, "w", encoding="utf-8") as handle:
            json.dump(
                [
                    {
                        "id": row["id"],
                        "split": row["split"],
                        "success": row["success"],
                        "failed": [k for k, v in row["checks"].items() if v is False],
                    }
                    for row in rows
                ],
                handle,
            )
        return original(rows)

    with ExitStack() as stack:
        apply_everywhere(name, stack)
        run_eval.summarise_by_split = keep_rows
        sys.argv = ["run_eval.py", *arguments]
        try:
            return run_eval.main()
        finally:
            run_eval.summarise_by_split = original


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
