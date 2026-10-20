"""Tests for the multi-turn set file and the script that builds it."""

import json

from eval import build_multi_turn, run_eval

CLICKS = ("approve", "decline")


def test_set_file_is_what_the_script_builds():
    sentences = json.loads(build_multi_turn.SENTENCES.read_text(encoding="utf-8"))

    built = build_multi_turn.build(sentences)

    assert built == build_multi_turn.MULTI_TURN_SET.read_text(encoding="utf-8"), (
        "run `task eval:build-multi` after changing the flows or the sentences"
    )


def test_set_file_loads_and_test_messages_come_from_the_sentences():
    examples = run_eval.load_golden(build_multi_turn.MULTI_TURN_SET)
    sentences = json.loads(build_multi_turn.SENTENCES.read_text(encoding="utf-8"))
    outside = {
        text
        for flow in ("S1", "S2", "S3", "S4")
        for variant in sentences[flow]
        for text in variant.values()
    }

    assert len(examples) == 16
    assert len({e["id"] for e in examples}) == 16
    assert {e["flow"] for e in examples if e["split"] == "dev"} == {
        "M1",
        "M3",
        "M6",
        "M8",
    }
    assert sum(e["split"] == "test" for e in examples) == 12
    for e in examples:
        assert e["group"] == "multi" and e["session"] == "customer"
        assert e["label"]["decision"] and "select_sql" in e
        for turn in e["turns"]:
            assert len({"say", "click", "check"} & turn.keys()) == 1
            assert turn.get("click") in (None, *CLICKS)
        if e["split"] == "test":
            assert {t["say"] for t in e["turns"] if "say" in t} <= outside


def test_every_test_example_picks_a_different_order():
    examples = run_eval.load_golden(build_multi_turn.MULTI_TURN_SET)

    selections = [e["select_sql"] for e in examples]

    assert len(set(selections)) == len(selections)
