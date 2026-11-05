"""The hand check of the judge: does a person agree with its scores?

Usage:  python -m eval.judge_check            write the sheet to fill in
        python -m eval.judge_check --agreement   count the filled-in sheet

The sheet is a CSV with one line per score the judge gave to a dev answer:
the question, the answer, the score and the judge's reason. The person
writes "yes" or "no" in the column "agree". Lines left empty are not
counted. Test answers are never written down, so only dev answers are in
the sheet. An existing sheet is not overwritten: the marks in it are work.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from eval.run_eval import GOLDEN_SET, RESULTS_DIR, load_golden
from src.guardrails.guarded_llm import configured_model

SCORES = ("faithfulness", "helpfulness", "no_causal_claim")
COLUMNS = (
    "system",
    "id",
    "score_name",
    "score",
    "agree",
    "question",
    "answer",
    "reason",
)
YES, NO = "yes", "no"


def sheet_rows(results: dict, questions: dict[str, str]) -> list[dict]:
    """One line per judge score in a results file."""
    lines = []
    for row in results.get("examples", []):
        for name in SCORES:
            score = row.get("judge", {}).get(name)
            if score is None:
                continue
            reason = row["judge"].get(f"{name}_reason") or ""
            if name == "faithfulness":
                claims = "; ".join(
                    f"[{claim['verdict']}] {claim['claim']}"
                    for claim in row["judge"].get("claims", [])
                )
                reason = f"{claims} | {reason}" if claims else reason
            lines.append(
                {
                    "system": row.get("baseline", "Final"),
                    "id": row["id"],
                    "score_name": name,
                    "score": f"{score:.2f}",
                    "agree": "",
                    "question": questions.get(row["id"], ""),
                    "answer": row["answer"],
                    "reason": reason,
                }
            )
    return lines


def write_sheet(path: Path, lines: list[dict]) -> None:
    """Write the rows to the CSV sheet for checking by hand."""
    with path.open("w", encoding="utf-8", newline="") as sheet:
        writer = csv.DictWriter(sheet, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(lines)


def agreement(path: Path) -> dict:
    """How many marked lines there are and on how many the person agrees."""
    with path.open(encoding="utf-8", newline="") as sheet:
        marks = [line["agree"].strip().lower() for line in csv.DictReader(sheet)]
    unknown = sorted({mark for mark in marks if mark not in ("", YES, NO)})
    if unknown:
        raise ValueError(f'the column "agree" takes yes or no, found: {unknown}')
    checked = [mark for mark in marks if mark]
    agreed = checked.count(YES)
    return {
        "lines": len(marks),
        "checked": len(checked),
        "agreed": agreed,
        "rate": agreed / len(checked) if checked else None,
    }


def main() -> int:
    """Run the command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agreement", action="store_true")
    parser.add_argument("--sheet", type=Path)
    args = parser.parse_args()

    model = configured_model()[1].replace("/", "_")
    sheet = args.sheet or RESULTS_DIR / f"judge_check_{model}.csv"
    if args.agreement:
        result = agreement(sheet)
        if result["rate"] is None:
            print(f"No line of {sheet} is marked yet.")
            return 1
        print(
            f"Checked {result['checked']} of {result['lines']} judge scores; "
            f"agreed with {result['agreed']} ({result['rate']:.0%})."
        )
        return 0

    if sheet.exists():
        print(f"{sheet} exists and was left as it is; delete it to start again.")
        return 1
    questions = {
        example["id"]: example["question"] for example in load_golden(GOLDEN_SET)
    }
    lines = []
    for name in (f"golden_v1_{model}.json", f"baselines_v1_{model}.json"):
        path = RESULTS_DIR / name
        if path.exists():
            lines += sheet_rows(json.loads(path.read_text(encoding="utf-8")), questions)
    if not lines:
        print("No judge scores found: run the evaluation with --judge first.")
        return 1
    write_sheet(sheet, lines)
    print(f"{len(lines)} judge scores written to {sheet}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
