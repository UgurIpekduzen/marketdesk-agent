"""The hand check of the translations of review quotes.

Usage:  python -m eval.review_check              write the sheet to fill in
        python -m eval.review_check --agreement   count the filled-in sheet

The Review Insight Agent quotes Portuguese reviews with a translation. A
judge model scores each translation; the person who cannot read Portuguese
checks a few by hand with a translator of their own. The sheet has one line
per quote: the review, the Portuguese text, the translation, the judge's
verdict and reason. The person writes "yes" if the translation says what
the Portuguese says and "no" if not, in the column "agree". The sheet holds
at most 10 quotes, taken in turn from each example, so every example is seen.
An existing sheet is not overwritten: the marks in it are work.
"""

import argparse
import csv
import json
import sys
from itertools import zip_longest
from pathlib import Path

from eval.judge_check import YES, agreement  # noqa: F401  (agreement is used by main)
from eval.run_eval import RESULTS_DIR, REVIEW_INSIGHT_SET, result_name
from src.guardrails.guarded_llm import configured_model

MAX_LINES = 10
COLUMNS = (
    "example",
    "review_id",
    "portuguese",
    "translation",
    "judge",
    "judge_reason",
    "agree",
)


def sheet_rows(results: dict) -> list[dict]:
    """Quotes with a judge verdict, up to the limit, taken in turn per example."""
    per_example = []
    for row in results.get("examples", []):
        verdicts = {
            item["review_id"]: item
            for item in row.get("judge", {}).get("translations", [])
        }
        seen = set()
        lines = []
        per_example.append(lines)
        for quote in row.get("quotes", []):
            key = (quote["review_id"], quote["text"])
            if key in seen or quote["review_id"] not in verdicts:
                continue
            seen.add(key)
            verdict = verdicts[quote["review_id"]]
            lines.append(
                {
                    "example": row["id"],
                    "review_id": quote["review_id"],
                    "portuguese": quote["text"],
                    "translation": quote["translation"],
                    "judge": verdict["verdict"],
                    "judge_reason": verdict["reason"],
                    "agree": "",
                }
            )
    turns = zip_longest(*per_example)
    return [line for turn in turns for line in turn if line][:MAX_LINES]


def write_sheet(path: Path, lines: list[dict]) -> None:
    """Write the rows to the CSV sheet for checking by hand."""
    with path.open("w", encoding="utf-8", newline="") as sheet:
        writer = csv.DictWriter(sheet, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(lines)


def main() -> int:
    """Run the command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agreement", action="store_true")
    parser.add_argument("--sheet", type=Path)
    args = parser.parse_args()

    model = configured_model()[1]
    sheet = args.sheet or RESULTS_DIR / f"review_check_{model.replace('/', '_')}.csv"
    if args.agreement:
        result = agreement(sheet)
        if result["rate"] is None:
            print(f"No line of {sheet} is marked yet.")
            return 1
        print(
            f"Checked {result['checked']} of {result['lines']} translations; "
            f"agreed with {result['agreed']} ({result['rate']:.0%})."
        )
        return 0

    if sheet.exists():
        print(f"{sheet} exists and was left as it is; delete it to start again.")
        return 1
    results = RESULTS_DIR / f"{result_name(REVIEW_INSIGHT_SET, model)}.json"
    if not results.exists():
        print("No results of the review insight set: run the evaluation first.")
        return 1
    lines = sheet_rows(json.loads(results.read_text(encoding="utf-8")))
    if not lines:
        print("No judged quotes found: run the set with --judge --independent-judge.")
        return 1
    write_sheet(sheet, lines)
    print(f"{len(lines)} quotes written to {sheet}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
