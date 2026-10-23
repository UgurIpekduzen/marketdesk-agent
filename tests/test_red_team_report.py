"""Tests for docs/red_team_report.md: the report and the code agree.

Every finding names the lock that keeps it from coming back, a unit test or
an evaluation example. The report is read here, so a lock that is renamed or
deleted, a table row left half empty or a summary that no longer matches the
table fails the check. No model is called: the live examples are only looked
up by their id, they run with the evaluation.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT = (ROOT / "docs" / "red_team_report.md").read_text(encoding="utf-8")

LAYERS = ("Client", "IDE", "Protocol", "Agent", "Application", "Model", "Server")
SEVERITIES = ("High", "Medium", "Low")
STATUSES = ("Fixed", "Open", "Accepted")
TEST_LOCK = re.compile(r"`(tests/[\w/]+\.py)::(test_\w+)`")
EXAMPLE_LOCK = re.compile(r"`(eval/[\w/]+\.jsonl)#(\w+)`")


def findings() -> list[list[str]]:
    """The cells of every finding row of section 3."""
    rows = []
    for line in section("3. Findings by layer").splitlines():
        if line.startswith("| RT-"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split(" | ")])
    return rows


def section(title: str) -> str:
    """The text of a second-level section, up to the next one."""
    return REPORT.split(f"\n## {title}", 1)[1].split("\n## ", 1)[0]


def test_the_report_has_findings_and_each_has_all_its_cells():
    rows = findings()

    assert rows
    for row in rows:
        assert len(row) == 6, row[0]
        assert all(cell and cell != "–" for cell in (row[0], row[1], row[2], row[3])), (
            row[0]
        )


def test_finding_ids_are_numbered_without_gaps():
    ids = [row[0] for row in findings()]

    assert ids == [f"RT-{number:02d}" for number in range(1, len(ids) + 1)]


def test_every_finding_has_a_severity_and_a_status_from_the_lists():
    for row in findings():
        assert row[2] in SEVERITIES, row[0]
        assert row[3].startswith(STATUSES), row[0]


def test_every_finding_names_a_lock():
    for row in findings():
        assert TEST_LOCK.search(row[5]) or EXAMPLE_LOCK.search(row[5]), row[0]


def test_every_finding_names_codes_unless_it_is_not_a_security_risk():
    for row in findings():
        assert row[4], row[0]


@pytest.mark.parametrize("path, name", sorted(set(TEST_LOCK.findall(REPORT))))
def test_every_test_the_report_names_exists(path, name):
    source = (ROOT / path).read_text(encoding="utf-8")

    assert re.search(rf"^(async )?def {name}\(", source, re.MULTILINE), (path, name)


@pytest.mark.parametrize("path, example", sorted(set(EXAMPLE_LOCK.findall(REPORT))))
def test_every_example_the_report_names_exists(path, example):
    ids = [
        json.loads(line)["id"]
        for line in (ROOT / path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert example in ids, (path, example)


def test_each_of_the_seven_layers_has_its_heading():
    headings = re.findall(r"^### (\w+)$", section("3. Findings by layer"), re.MULTILINE)

    assert [layer for layer in headings if layer in LAYERS] == list(LAYERS)


def test_the_summary_counts_are_the_tables():
    rows = findings()
    statuses = [row[3].split()[0] for row in rows]
    severities = [row[2] for row in rows]
    summary = section("1. Summary")

    counts = {status: statuses.count(status) for status in STATUSES}
    assert f"| Findings in this report | {len(rows)}: " in summary
    assert (
        f"**{counts['Fixed']} fixed, {counts['Open']} open, "
        f"{counts['Accepted']} accepted**"
    ) in summary
    assert (
        f"| Severity | {severities.count('High')} high, "
        f"{severities.count('Medium')} medium, {severities.count('Low')} low "
    ) in summary


def test_the_open_findings_are_in_the_list_of_open_issues():
    open_ids = [row[0] for row in findings() if row[3].startswith("Open")]
    issues = section("7. Open issues and limits")

    for finding in open_ids:
        assert finding in issues, finding


def test_the_report_holds_no_ticket_key():
    # Ticket keys belong to commit messages only.
    assert not re.search(r"MKDSK-\d+", REPORT)


def test_the_author_sections_are_left_for_the_author():
    assert "*To be written by the author.*" in section("9. Reading of the results")
