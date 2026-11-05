"""The markdown tables of a run's text, drawn for the terminal.

The results file keeps markdown; what is printed gets aligned columns in a
frame, and a column that holds only "—" (nothing measured) is left out so
the table fits the screen.
"""

EMPTY = "—"


def cells(line: str) -> list[str]:
    """The cells of one markdown table line."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_rule(line: str) -> bool:
    """The |---|---| line under a markdown table's header."""
    return set(line.replace("|", "").strip()) <= {"-", ":"} and "-" in line


def frame_line(widths: list[int], left: str, middle: str, right: str) -> str:
    """A horizontal border of the table."""
    return left + middle.join("─" * (width + 2) for width in widths) + right


def frame_row(row: list[str], widths: list[int]) -> str:
    """One framed table row."""
    shown = [
        # The first column names the row; the others are figures.
        f" {cell:<{width}} " if column == 0 else f" {cell:>{width}} "
        for column, (cell, width) in enumerate(zip(row, widths, strict=True))
    ]
    return "│" + "│".join(shown) + "│"


def draw(rows: list[list[str]]) -> str:
    """A framed table; the first row is the header."""
    keep = [
        column
        for column in range(len(rows[0]))
        if column == 0 or any(row[column] != EMPTY for row in rows[1:])
    ]
    rows = [[row[column] for column in keep] for row in rows]
    widths = [max(len(row[column]) for row in rows) for column in range(len(keep))]

    return "\n".join(
        [
            frame_line(widths, "┌", "┬", "┐"),
            frame_row(rows[0], widths),
            frame_line(widths, "├", "┼", "┤"),
            *(frame_row(row, widths) for row in rows[1:]),
            frame_line(widths, "└", "┴", "┘"),
        ]
    )


def terminal_tables(text: str) -> str:
    """The text with every markdown table in it drawn as a framed table."""
    lines = text.split("\n")
    out = []
    index = 0
    while index < len(lines):
        if (
            lines[index].startswith("|")
            and index + 1 < len(lines)
            and is_rule(lines[index + 1])
        ):
            rows = [cells(lines[index])]
            index += 2
            while index < len(lines) and lines[index].startswith("|"):
                rows.append(cells(lines[index]))
                index += 1
            out.append(draw(rows))
        else:
            out.append(lines[index])
            index += 1
    return "\n".join(out)
