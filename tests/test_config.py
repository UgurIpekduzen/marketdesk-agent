"""Tests for config.py and for the rule that only config.py knows "today"."""

import ast
import tomllib
from datetime import date
from pathlib import Path

import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Folders that hold our own Python code. Virtual environments, caches and
# downloaded data are not ours to check.
CODE_DIRS = ("src", "scripts", "data", "tests", "eval")
SKIPPED_PARTS = {"raw", "__pycache__"}

# Attribute calls that read the machine clock: datetime.now(), date.today(),
# datetime.utcnow() and time.time().
CLOCK_ATTRIBUTES = {"now", "utcnow", "today"}


def project_python_files() -> list[Path]:
    files = sorted(PROJECT_ROOT.glob("*.py"))
    for folder in CODE_DIRS:
        files.extend(sorted((PROJECT_ROOT / folder).rglob("*.py")))
    return [path for path in files if not SKIPPED_PARTS & set(path.parts)]


def clock_calls(source: str) -> list[int]:
    """Return the line numbers where the source reads the machine clock."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Attribute):
            continue
        reads_clock = node.attr in CLOCK_ATTRIBUTES
        is_time_time = (
            node.attr == "time"
            and isinstance(node.value, ast.Name)
            and node.value.id == "time"
        )
        if reads_clock or is_time_time:
            lines.append(node.lineno)
    return lines


def test_simulated_today_is_the_first_of_september_2018():
    assert config.SIMULATED_TODAY == date(2018, 9, 1)


def test_return_windows_and_threshold():
    assert config.RETURN_WINDOW_SHORT_DAYS == 14
    assert config.RETURN_WINDOW_LONG_DAYS == 30
    assert config.FREIGHT_REFUND_DELAY_DAYS == 10
    assert config.APPROVAL_THRESHOLD_BRL == 500


def test_agent_step_limit():
    assert config.MAX_STEPS == 8


def test_model_provider_and_name_are_set():
    assert config.LLM_PROVIDER in {"gemini", "groq"}
    assert config.LLM_MODEL


def test_clock_detector_finds_every_form():
    source = (
        "import time\n"
        "from datetime import date, datetime\n"
        "a = datetime.now()\n"
        "b = date.today()\n"
        "c = datetime.utcnow()\n"
        "d = time.time()\n"
        "e = date(2018, 9, 1)\n"
    )

    assert clock_calls(source) == [3, 4, 5, 6]


def test_no_code_reads_the_machine_clock():
    files = project_python_files()
    assert files, "no Python files found to check"

    offenders = [
        f"{path.relative_to(PROJECT_ROOT)}:{line}"
        for path in files
        for line in clock_calls(path.read_text(encoding="utf-8"))
    ]

    assert offenders == [], "use config.SIMULATED_TODAY instead of the clock"


def test_the_page_shows_no_error_details_and_keeps_its_protections():
    settings = tomllib.loads(
        (PROJECT_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    )

    assert settings["client"]["showErrorDetails"] == "none"
    assert settings["server"]["enableXsrfProtection"] is True
    assert settings["server"]["enableCORS"] is True


def test_the_page_hides_the_developer_options_and_has_its_own_colours():
    settings = tomllib.loads(
        (PROJECT_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    )

    assert settings["client"]["toolbarMode"] == "minimal"
    assert settings["theme"]["base"] == "dark"
    assert settings["theme"]["primaryColor"] == "#5B5FE8"
