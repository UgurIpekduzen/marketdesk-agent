"""The judge: a model that scores what the rule-based checks cannot.

Three scores, each between 0 and 1:

- faithfulness of a policy answer: the share of its claims that the policy
  documents the question is about support (DeepEval's FaithfulnessMetric; a claim the documents
  say nothing about counts as unsupported);
- helpfulness of a policy answer: does it answer the question, or say
  plainly that the policy does not cover it;
- no causal or profit claim in an operations answer: metrics here are
  observational, and GMV is sales volume, not profit.

The last two use DeepEval's GEval with the steps written out below, so the
judge's instructions are in this file.

The judge model is called through the project's outbound guard and the
response cache, like every other model call: DeepEval is given the model
as an object and never talks to a provider itself.
"""

import asyncio
import os

# Before deepeval is imported: no usage data is sent and .env is not read.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_DISABLE_DOTENV", "1")

from deepeval.metrics import FaithfulnessMetric, GEval
from deepeval.metrics.faithfulness.faithfulness import FaithfulnessTemplate
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase, SingleTurnParams
from llama_index.core.llms import ChatMessage
from llama_index.core.llms.function_calling import FunctionCallingLLM
from pydantic import ValidationError

import config
from src.guardrails.guarded_llm import GuardedLLM
from src.guardrails.outbound import Redactor
from src.i18n import DEFAULT_LANGUAGE, LANGUAGE_NAMES, Language
from src.knowledge.policy_index import read_sections

HELPFULNESS_STEPS = [
    (
        "The input is a customer's question to a marketplace's support assistant, "
        "in Turkish. The actual output is the assistant's answer."
    ),
    "If the answer gives the rule the customer asked about, it is helpful.",
    (
        "If the answer says that the policy does not cover the question and "
        "offers to hand the case to a person, it is helpful too: that is the "
        "right answer when there is no rule."
    ),
    (
        "If the answer talks about something else, refuses without a reason, or "
        "leaves the customer without a next step, it is not helpful."
    ),
    (
        "Do not judge whether the rule in the answer is true; only whether the "
        "answer responds to what was asked."
    ),
]
NO_CAUSAL_CLAIM_STEPS = [
    (
        "The input is a question from operations staff of a marketplace, in "
        "Turkish. The actual output is the answer of a data assistant."
    ),
    (
        "The figures are observational. The answer may report numbers and say "
        "that two things occur together."
    ),
    (
        "The answer fails if it states, as its own conclusion, that one thing "
        "caused, led to, or was the reason for another."
    ),
    (
        "The answer fails if it calls sales volume (GMV) profit, earnings or "
        "revenue the company kept."
    ),
    (
        "An answer that repeats the question's assumption in order to reject or "
        "qualify it does not fail. A note such as 'this is not causality' counts "
        "in the answer's favour."
    ),
    "Score 1 if the answer makes no such claim, 0 if it does.",
]
# The same steps on GEval's own scale. GEval reads the score as one out of
# 10 and divides it by 10: the configured judge still gives 10 for "no
# claim", but the independent judge writes the 1 the last step asks for,
# which comes out as 0.1 for an answer its reason says has no claim.
NO_CAUSAL_CLAIM_STEPS_OUT_OF_TEN = [
    *NO_CAUSAL_CLAIM_STEPS[:-1],
    "Score 10 if the answer makes no such claim, 0 if it does.",
]


# Put in front of DeepEval's own prompt that splits an answer into claims.
# Without it "the policy does not cover this", "shall I hand you over?" and
# "(İade Politikası, Bölüm 2)" are taken as claims the documents do not
# support, and a right answer loses points for them.
CLAIMS_NOTE = (
    "Extra rule for this task. The text is an answer of a support assistant "
    "about a marketplace's policy. Do NOT extract as claims: (1) statements "
    "that the policy or the documents do not cover, mention or set a topic; "
    "(2) offers of help, offers to hand the case to a person, and questions "
    "to the customer; (3) references that only name where a rule is written, "
    "such as a document title and a section number. Extract only statements "
    "about what the rules are.\n\n"
)


class PolicyFaithfulnessTemplate(FaithfulnessTemplate):
    """DeepEval's faithfulness prompts, with the note above on the claims."""

    @staticmethod
    def generate_claims(**kwargs) -> str:
        return CLAIMS_NOTE + FaithfulnessTemplate.generate_claims(**kwargs)


# Added to a prompt whose answer could not be read as JSON, for one more try.
JSON_REMINDER = (
    "\n\nYour previous answer was not valid JSON. Answer again with valid "
    "JSON only, and escape every double quote inside a string."
)


def parse_json(text: str, schema):
    """Read the JSON object in an answer, which may sit in a code fence."""
    return schema.model_validate_json(text[text.find("{") : text.rfind("}") + 1])


class JudgeModel(DeepEvalBaseLLM):
    """Gives DeepEval a model that goes through the guard and the cache."""

    def __init__(
        self, provider_llm: FunctionCallingLLM, name: str | None = None
    ) -> None:
        """name is the model's name in DeepEval's reports; the judge's by default."""
        self._llm = GuardedLLM(inner=provider_llm, redactor=Redactor())
        self._name = name
        self.calls = 0

    def load_model(self) -> GuardedLLM:
        return self._llm

    def get_model_name(self) -> str:
        return self._name or config.JUDGE_MODEL

    async def _ask(self, prompt: str) -> str:
        self.calls += 1
        response = await self._llm.achat([ChatMessage(role="user", content=prompt)])
        return response.message.content or ""

    async def a_generate(self, prompt: str, schema=None):
        text = await self._ask(prompt)
        if schema is None:
            return text
        try:
            return parse_json(text, schema)
        except ValidationError:
            # Usually a quotation mark left unescaped inside a string.
            return parse_json(await self._ask(prompt + JSON_REMINDER), schema)

    def generate(self, prompt: str, schema=None):
        return asyncio.run(self.a_generate(prompt, schema))


def policy_context(documents: list[str] | None = None) -> list[str]:
    """Policy sections, each under its citation: what an answer may rest on.

    documents are titles of policy documents; without them every section of
    every document is returned.
    """
    return [
        f"[{section.citation}] {section.heading}\n{section.text}"
        for section in read_sections()
        if documents is None or section.document in documents
    ]


def in_language(steps: list[str], language: Language) -> list[str]:
    """The steps for questions in this language; the Turkish ones as written."""
    return [
        step.replace("in Turkish", f"in {LANGUAGE_NAMES[language]}") for step in steps
    ]


class Judge:
    def __init__(
        self,
        provider_llm: FunctionCallingLLM,
        language: Language = DEFAULT_LANGUAGE,
        name: str | None = None,
        ops_steps: list[str] = NO_CAUSAL_CLAIM_STEPS,
    ) -> None:
        """language is that of the questions and answers judged; the policy
        text the answers are checked against is always Turkish. name is the
        judge model's name, the configured judge's by default. ops_steps
        are the steps an operations answer is scored with."""
        self.model = JudgeModel(provider_llm, name)
        self.language = Language(language)
        self.ops_steps = ops_steps

    @property
    def live_calls(self) -> int:
        """Calls that reached the provider: those of the cache the evaluation
        puts in front of the judge; 0 for a model without one."""
        return getattr(self.model.load_model().inner, "live_calls", 0)

    def _g_eval(self, name: str, steps: list[str]) -> GEval:
        return GEval(
            name=name,
            evaluation_steps=steps,
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
            ],
            model=self.model,
            async_mode=False,
        )

    def policy_answer(
        self, question: str, answer: str, documents: list[str] | None = None
    ) -> dict:
        """Score a policy answer against the text of the policy.

        documents are the policy documents the question is about. The
        metric first sums the text up and then checks the answer against
        that summary; given all five documents at once it drops details
        and marks true statements as unsupported, so the text is narrowed
        to the documents that matter. Without documents (a question no
        section covers) the whole policy is used.
        """
        case = LLMTestCase(
            input=question,
            actual_output=answer,
            retrieval_context=policy_context(documents),
        )
        faithfulness = FaithfulnessMetric(
            model=self.model,
            include_reason=True,
            async_mode=False,
            # A claim the policy neither supports nor contradicts counts
            # against the answer: an invented rule is the fault looked for.
            penalize_ambiguous_claims=True,
            evaluation_template=PolicyFaithfulnessTemplate,
        )
        faithfulness.measure(case)
        helpfulness = self._g_eval(
            "Helpfulness", in_language(HELPFULNESS_STEPS, self.language)
        )
        helpfulness.measure(case)
        return {
            "faithfulness": faithfulness.score,
            "claims": [
                {"claim": claim, "verdict": verdict.verdict.value}
                for claim, verdict in zip(
                    faithfulness.claims, faithfulness.verdicts, strict=False
                )
            ],
            "faithfulness_reason": faithfulness.reason,
            "helpfulness": helpfulness.score,
            "helpfulness_reason": helpfulness.reason,
        }

    def ops_answer(self, question: str, answer: str) -> dict:
        """Score an operations answer for causal or profit claims."""
        metric = self._g_eval(
            "No causal or profit claim",
            in_language(self.ops_steps, self.language),
        )
        metric.measure(LLMTestCase(input=question, actual_output=answer))
        return {
            "no_causal_claim": metric.score,
            "no_causal_claim_reason": metric.reason,
        }
