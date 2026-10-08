"""Tests for the deploy trial page, run without a browser.

The embedding button is not pressed here: it downloads the model. Its code
is covered by test_embedding.py and by `task embed:check`.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_page_opens_without_an_error():
    page = AppTest.from_file(APP, default_timeout=30).run()

    assert not page.exception
    assert page.title[0].value == "MarketDesk: deploy trial"
    assert [button.label for button in page.button] == [
        "Embed the question",
        "Start the server and call its status tool",
    ]


def test_page_shows_memory_at_start():
    page = AppTest.from_file(APP, default_timeout=30).run()

    labels = [metric.label for metric in page.metric]
    assert labels == [
        "At start: this process",
        "Container, all processes",
        "Container limit",
    ]
    assert page.metric[0].value.endswith(" MB")


def test_mcp_button_starts_the_server_and_shows_its_answer():
    page = AppTest.from_file(APP, default_timeout=60).run()

    page.button[1].click().run()

    assert not page.exception
    answer = page.json[0].value
    assert '"status":"ok"' in answer.replace(" ", "")
    assert "After the call: this process" in [metric.label for metric in page.metric]
