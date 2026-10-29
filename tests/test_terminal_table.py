"""Tests for drawing a run's markdown tables for the terminal."""

from eval.terminal_table import terminal_tables

TEXT = """dev

| Group | n | Task success | SQL execution | Steps |
|---|---|---|---|---|
| attack | 4 | 100% | — | 5.0 |
| all | 4 | 75% | — | 12.5 |

Failed in dev: none"""


def test_table_is_framed_and_aligned():
    drawn = terminal_tables(TEXT).split("\n")

    assert drawn[0] == "dev"
    table = drawn[2:8]
    assert table == [
        "┌────────┬───┬──────────────┬───────┐",
        "│ Group  │ n │ Task success │ Steps │",
        "├────────┼───┼──────────────┼───────┤",
        "│ attack │ 4 │         100% │   5.0 │",
        "│ all    │ 4 │          75% │  12.5 │",
        "└────────┴───┴──────────────┴───────┘",
    ]
    assert drawn[-1] == "Failed in dev: none"


def test_empty_column_is_left_out():
    assert "SQL execution" not in terminal_tables(TEXT)
    assert "SQL execution" in TEXT


def test_text_without_a_table_is_left_alone():
    text = "Model calls: 0 live, 14 from the cache\n| not a table"

    assert terminal_tables(text) == text
