"""The model's view of the tools: the name, the description and the parameters of
every tool of the three agents stay as they were written down in
tests/tool_schemas.json. A change of them is a change of what the model is told
(and of every cached answer), so it is made on purpose: change the file with it."""

import json
from pathlib import Path

from tests.tool_schemas_support import current_schemas

SNAPSHOT = Path(__file__).with_name("tool_schemas.json")


def test_tools_show_the_model_what_they_showed_before(
    synthetic_db_path, fake_policy_index
):
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert current_schemas(synthetic_db_path, fake_policy_index) == expected


def test_every_agent_has_its_tools_in_the_file():
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert {name: len(tools) for name, tools in expected.items()} == {
        "ops": 4,
        "review_insight": 2,
        "support_en": 6,
        "support_tr": 6,
    }
