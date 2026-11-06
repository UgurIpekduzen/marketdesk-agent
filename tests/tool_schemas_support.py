"""What the model is shown of every tool of the three agents: the name, the
description and the parameters, as a tool call to a provider is built from
them. Shared by the test that keeps them as they are."""

from src.agents.loop_guard import LoopGuard
from src.agents.ops import OpsAgent
from src.agents.review_insight import ReviewInsightAgent
from src.agents.support import build_tools
from src.i18n import Language
from tests.fakes import FakeLLM


def shown_to_the_model(tools) -> dict:
    return {
        tool.metadata.name: tool.metadata.to_openai_tool()["function"] for tool in tools
    }


def current_schemas(db_path, policy_index) -> dict:
    schemas = {}
    for language in Language:
        tools = build_tools(None, policy_index, LoopGuard(), language)
        schemas[f"support_{language.value}"] = shown_to_the_model(tools)
    ops = OpsAgent(db_path, FakeLLM())
    schemas["ops"] = shown_to_the_model(ops._agent.tools)
    ops.close()
    reviews = ReviewInsightAgent(db_path, FakeLLM())
    schemas["review_insight"] = shown_to_the_model(reviews._agent.tools)
    reviews.close()
    return schemas
