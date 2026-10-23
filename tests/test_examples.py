"""Tests for the example questions: drawn from the pool, in the right mix."""

import json
import random
from pathlib import Path

import pytest

from src import messages, messages_en
from src.i18n import Language
from src.ui.demo_customers import SITUATIONS
from src.ui.examples import CUSTOMER_POLICY_COUNT, OPS_COUNT, pick_examples

GOLDEN_SET = Path(__file__).resolve().parent.parent / "eval" / "golden_set.jsonl"
CUSTOMER_POOL = [
    *(
        q
        for questions in messages.EXAMPLE_QUESTIONS_BY_SITUATION.values()
        for q in questions
    ),
    *messages.EXAMPLE_QUESTIONS_GENERAL,
    *messages.EXAMPLE_QUESTIONS_POLICY,
]


def test_the_pool_holds_the_30_verified_questions_once_each():
    pool = [*CUSTOMER_POOL, *messages.EXAMPLE_QUESTIONS_OPS]

    assert len(pool) == 30
    assert len(set(pool)) == 30


def test_every_demo_situation_has_its_own_questions():
    assert set(messages.EXAMPLE_QUESTIONS_BY_SITUATION) == set(SITUATIONS)


def test_no_example_is_a_question_of_the_held_out_test_split():
    examples = [json.loads(line) for line in GOLDEN_SET.read_text().splitlines()]
    held_out = {e["question"] for e in examples if e["split"] == "test"}

    assert held_out
    assert not held_out & {*CUSTOMER_POOL, *messages.EXAMPLE_QUESTIONS_OPS}


@pytest.mark.parametrize("situation", list(SITUATIONS))
def test_a_customer_gets_one_situation_one_general_and_two_policy_questions(
    situation,
):
    picked = pick_examples(("customer", situation), random.Random(1))

    assert len(picked) == 2 + CUSTOMER_POLICY_COUNT
    assert picked[0] in messages.EXAMPLE_QUESTIONS_BY_SITUATION[situation]
    assert picked[1] in messages.EXAMPLE_QUESTIONS_GENERAL
    assert set(picked[2:]) <= set(messages.EXAMPLE_QUESTIONS_POLICY)
    assert len(set(picked)) == len(picked)


def test_an_analyst_gets_four_different_metric_questions():
    picked = pick_examples(("ops",), random.Random(1))

    assert len(picked) == OPS_COUNT
    assert set(picked) <= set(messages.EXAMPLE_QUESTIONS_OPS)
    assert len(set(picked)) == OPS_COUNT


@pytest.mark.parametrize("identity", [("customer", "many_orders"), ("ops",)])
def test_the_same_seed_picks_the_same_questions(identity):
    assert pick_examples(identity, random.Random(7)) == pick_examples(
        identity, random.Random(7)
    )


@pytest.mark.parametrize("identity", [("customer", "many_orders"), ("ops",)])
def test_other_seeds_pick_other_questions(identity):
    picks = {tuple(pick_examples(identity, random.Random(seed))) for seed in range(20)}

    assert len(picks) > 1


@pytest.mark.parametrize("identity", [("customer", "window_passed"), ("ops",)])
def test_english_examples_are_the_translations_of_the_turkish_picks(identity):
    """The same seed picks the same places in both pools, so an English page
    offers the translations of what a Turkish page would."""
    turkish = pick_examples(identity, random.Random(3))
    english = pick_examples(identity, random.Random(3), Language.EN)

    def place(question, catalog):
        pools = [
            *catalog.EXAMPLE_QUESTIONS_BY_SITUATION.values(),
            catalog.EXAMPLE_QUESTIONS_GENERAL,
            catalog.EXAMPLE_QUESTIONS_POLICY,
            catalog.EXAMPLE_QUESTIONS_OPS,
        ]
        return next(
            (number, pool.index(question))
            for number, pool in enumerate(pools)
            if question in pool
        )

    assert [place(q, messages) for q in turkish] == [
        place(q, messages_en) for q in english
    ]
