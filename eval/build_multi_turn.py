"""Build the multi-turn set from the flows below and the test sentences.

Usage:  python -m eval.build_multi_turn

The dev examples (M1, M3, M6, M8) are written here. The customer messages of
the test examples (M2, M4, M5, M7) come unchanged from
multi_turn_test_sentences.json: an outside model wrote three variants for
each from a prompt that named no rule, tool or expectation, and every
variant becomes an example of its own. Change the flows or the sentences,
then run this again; a test checks that multi_turn_set.jsonl is what it
writes.

Like the golden set, an example holds no order or customer id: it carries
the SQL that picks its order when the run starts.
"""

import json
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
SENTENCES = EVAL_DIR / "multi_turn_test_sentences.json"
MULTI_TURN_SET = EVAL_DIR / "multi_turn_set.jsonl"

# A delivered order of a customer, delivered between two days. Left out:
# orders delivered 10 or more days after the estimate (R9 would add the
# freight back to the refund) and orders paid partly with a voucher (R12
# would split the refund), so the amount stays the plain R8 one.
# Examples approve requests on the run's copy, so each one takes a different
# order: OFFSET picks the next row, starting from 30 to stay clear of the
# golden set's orders.
DELIVERED = (
    "SELECT o.order_id, c.customer_unique_id FROM orders AS o JOIN customers AS c "
    "ON c.customer_id = o.customer_id WHERE o.order_status = 'delivered' "
    "AND DATE(o.order_delivered_customer_date) BETWEEN '{start}' AND '2018-{end}' "
    "AND julianday(DATE(o.order_delivered_customer_date)) - "
    "julianday(DATE(o.order_estimated_delivery_date)) < 10 "
    "AND NOT EXISTS (SELECT 1 FROM order_payments AS p WHERE p.order_id = o.order_id "
    "AND p.payment_type = 'voucher') "
    "AND (SELECT SUM(i.price + i.freight_value) FROM order_items AS i "
    "WHERE i.order_id = o.order_id) {total} "
    "ORDER BY o.order_id LIMIT 1 OFFSET {offset}"
)


def inside_14(offset: int) -> str:
    """Delivered 0 to 14 days before today (2018-09-01), refund up to 500
    BRL: inside the window of every reason (R6, R7)."""
    return DELIVERED.format(
        start="2018-08-18", end="09-01", total="<= 500", offset=offset
    )


def days_15_to_30(offset: int) -> str:
    """Delivered 15 to 30 days before today: damaged and wrong_item are
    still inside their 30-day window (R7), changed_mind is outside its 14
    days (R6)."""
    return DELIVERED.format(
        start="2018-08-02", end="08-17", total="<= 500", offset=offset
    )


def senior(offset: int) -> str:
    """Inside every window, with a refund above the 500 BRL threshold: the
    request starts as PENDING_SENIOR (R10)."""
    return DELIVERED.format(
        start="2018-08-18", end="09-01", total="> 500", offset=offset
    )


def shipped(offset: int) -> str:
    """An order on its way: it cannot be cancelled or returned yet (R3)."""
    return (
        "SELECT o.order_id, c.customer_unique_id FROM orders AS o JOIN customers AS c "
        "ON c.customer_id = o.customer_id WHERE o.order_status = 'shipped' "
        f"ORDER BY o.order_id LIMIT 1 OFFSET {offset}"
    )


def check(reason: str) -> dict:
    """A scripted check_return_eligibility call for the first alias."""
    return {
        "name": "check_return_eligibility",
        "args": {"order_ref": "SIP-1", "reason": reason},
    }


def create(reason: str) -> dict:
    """A scripted create_return_request call for the first alias."""
    return {
        "name": "create_return_request",
        "args": {"order_ref": "SIP-1", "reason": reason, "amount": "{refund_amount}"},
    }


AMOUNT = [["{refund_amount}", "{refund_amount_comma}"]]
# The customer has not said why: the agent asks, and no rule is checked
# without a reason (a check that ran anyway must have refused for it).
NO_REASON_YET = {
    "intent": "support",
    "tools": [],
    "forbidden_tools": ["create_return_request"],
    "must_contain": ["?"],
    "decision_if_called": "REASON_REQUIRED",
}


def written(count: int, status: str | None = None, reason: str | None = None) -> dict:
    """The return requests this example has written for its order so far."""
    expectation: dict = {"count": count}
    if count:
        expectation.update(
            {"status": status, "amount": "{refund_amount}", "reason": reason}
        )
    return {"written": expectation}


def dev_examples() -> list[dict]:
    """The development flows of the multi-turn set."""
    return [
        {
            "id": "M1",
            "group": "multi",
            "split": "dev",
            "flow": "M1",
            "session": "customer",
            "note": "reason asked first (R6 window), then the request, then approve: "
            "one row, PENDING_REVIEW, the rule engine's amount",
            "select_sql": inside_14(30),
            "label": {"reason": "changed_mind", "decision": "ELIGIBLE"},
            "turns": [
                {
                    "say": "{order} siparişimi iade etmek istiyorum.",
                    "expected": NO_REASON_YET,
                },
                {
                    "say": "Bedeni olmadı. Talebi açabilir misiniz?",
                    "expected": {
                        "intent": "support",
                        "decision": "ELIGIBLE",
                        "awaiting_approval": True,
                        "request_status": "PENDING_REVIEW",
                        "tools": [check("changed_mind"), create("changed_mind")],
                        "must_contain": AMOUNT,
                    },
                },
                {
                    "click": "approve",
                    "expected": written(1, "PENDING_REVIEW", "changed_mind"),
                },
            ],
        },
        {
            "id": "M3",
            "group": "multi",
            "split": "dev",
            "flow": "M3",
            "session": "customer",
            "note": "approved request (R7, damaged inside 30 days), then a second one "
            "for the same order: DUPLICATE_REQUEST (R11), no second row",
            "select_sql": days_15_to_30(30),
            "label": {"reason": "damaged", "decision": "ELIGIBLE"},
            "turns": [
                {
                    "say": "{order} siparişim hasarlı geldi, iade talebi açar mısınız?",
                    "expected": {
                        "intent": "support",
                        "decision": "ELIGIBLE",
                        "awaiting_approval": True,
                        "request_status": "PENDING_REVIEW",
                        "tools": [check("damaged"), create("damaged")],
                    },
                },
                {
                    "click": "approve",
                    "expected": written(1, "PENDING_REVIEW", "damaged"),
                },
                {
                    "say": "Aynı sipariş için bir iade talebi daha açın lütfen.",
                    "expected": {
                        "intent": "support",
                        "decision_if_called": "DUPLICATE_REQUEST",
                        "awaiting_approval": False,
                    },
                },
                {"check": "end", "expected": written(1, "PENDING_REVIEW", "damaged")},
            ],
        },
        {
            "id": "M6",
            "group": "multi",
            "split": "dev",
            "flow": "M6",
            "session": "customer",
            "note": "vague first: a question, no tool; then 'can I return it?': the "
            "decision and the amount, no request; then the request and approve",
            "select_sql": days_15_to_30(31),
            "label": {"reason": "damaged", "decision": "ELIGIBLE"},
            "turns": [
                {
                    "say": "Siparişimle ilgili bir sorun var.",
                    "expected": {
                        "intent": "support",
                        "tools": [],
                        "forbidden_tools": [
                            "check_return_eligibility",
                            "create_return_request",
                        ],
                        "must_contain": ["?"],
                    },
                },
                {
                    "say": "{order} hasarlı geldi, iade edebilir miyim?",
                    "expected": {
                        "intent": "support",
                        "decision": "ELIGIBLE",
                        "awaiting_approval": False,
                        "tools": [check("damaged")],
                        "forbidden_tools": ["create_return_request"],
                        "must_contain": AMOUNT,
                    },
                },
                {
                    "say": "Evet, iade talebini açın.",
                    "expected": {
                        "intent": "support",
                        "awaiting_approval": True,
                        "request_status": "PENDING_REVIEW",
                        "tools": [create("damaged")],
                    },
                },
                {
                    "click": "approve",
                    "expected": written(1, "PENDING_REVIEW", "damaged"),
                },
            ],
        },
        {
            "id": "M8",
            "group": "multi",
            "split": "dev",
            "flow": "M8",
            "session": "customer",
            "note": "cancel an order on its way: IN_TRANSIT from the rules (R3), no "
            "ticket; asking to open a return now writes nothing",
            "select_sql": shipped(0),
            "label": {"reason": "changed_mind", "decision": "IN_TRANSIT"},
            "turns": [
                {
                    "say": "{order} siparişimi iptal etmek istiyorum, vazgeçtim.",
                    "expected": {
                        "intent": "support",
                        "decision": "IN_TRANSIT",
                        "awaiting_approval": False,
                        "tools": [check("changed_mind")],
                        "forbidden_tools": [
                            "escalate_to_human",
                            "create_return_request",
                        ],
                    },
                },
                {
                    "say": "Peki, şimdiden iade talebi açın o zaman.",
                    "expected": {
                        "intent": "support",
                        "decision_if_called": "IN_TRANSIT",
                        "awaiting_approval": False,
                    },
                },
                {"check": "end", "expected": written(0)},
            ],
        },
    ]


def test_examples(sentences: dict) -> list[dict]:
    """Every variant of every test flow, with the outside model's messages."""
    examples = []
    for n, variant in enumerate(sentences["S1"]):
        examples.append(
            {
                "id": f"M2{'abc'[n]}",
                "group": "multi",
                "split": "test",
                "flow": "M2",
                "session": "customer",
                "note": "damaged inside 30 days (R7): approval card, then decline: "
                "nothing written",
                "select_sql": days_15_to_30(32 + n),
                "label": {"reason": "damaged", "decision": "ELIGIBLE"},
                "turns": [
                    {
                        "say": variant["m1"],
                        "expected": {
                            "intent": "support",
                            "decision": "ELIGIBLE",
                            "awaiting_approval": True,
                            "request_status": "PENDING_REVIEW",
                            "tools": [check("damaged"), create("damaged")],
                        },
                    },
                    {"click": "decline", "expected": written(0)},
                ],
            }
        )
    for n, variant in enumerate(sentences["S2"]):
        examples.append(
            {
                "id": f"M4{'abc'[n]}",
                "group": "multi",
                "split": "test",
                "flow": "M4",
                "session": "customer",
                "note": "damaged, refund above 500 BRL (R10): the card and the row "
                "say PENDING_SENIOR",
                "select_sql": senior(n),
                "label": {"reason": "damaged", "decision": "ELIGIBLE"},
                "turns": [
                    {
                        "say": variant["m1"],
                        "expected": {
                            "intent": "support",
                            "decision": "ELIGIBLE",
                            "awaiting_approval": True,
                            "request_status": "PENDING_SENIOR",
                            "tools": [check("damaged"), create("damaged")],
                        },
                    },
                    {
                        "click": "approve",
                        "expected": written(1, "PENDING_SENIOR", "damaged"),
                    },
                ],
            }
        )
    for n, variant in enumerate(sentences["S3"]):
        examples.append(
            {
                "id": f"M5{'abc'[n]}",
                "group": "multi",
                "split": "test",
                "flow": "M5",
                "session": "customer",
                "note": "no reason first: asked; then changed mind after 14 days "
                "(R6): NOT_ELIGIBLE_WINDOW, no card, nothing written",
                "select_sql": days_15_to_30(35 + n),
                "label": {"reason": "changed_mind", "decision": "NOT_ELIGIBLE_WINDOW"},
                "turns": [
                    {"say": variant["m1"], "expected": NO_REASON_YET},
                    {
                        "say": variant["m2"],
                        "expected": {
                            "intent": "support",
                            "decision": "NOT_ELIGIBLE_WINDOW",
                            "awaiting_approval": False,
                            "tools": [check("changed_mind")],
                            "forbidden_tools": ["create_return_request"],
                        },
                    },
                    {"check": "end", "expected": written(0)},
                ],
            }
        )
    for n, variant in enumerate(sentences["S4"]):
        examples.append(
            {
                "id": f"M7{'abc'[n]}",
                "group": "multi",
                "split": "test",
                "flow": "M7",
                "session": "customer",
                "note": "wrong item (R7): card shown; the customer types an approval "
                "in the chat: nothing written; then decline",
                "select_sql": inside_14(31 + n),
                "label": {"reason": "wrong_item", "decision": "ELIGIBLE"},
                "turns": [
                    {
                        "say": variant["m1"],
                        "expected": {
                            "intent": "support",
                            "decision": "ELIGIBLE",
                            "awaiting_approval": True,
                            "request_status": "PENDING_REVIEW",
                            "tools": [check("wrong_item"), create("wrong_item")],
                        },
                    },
                    {
                        "say": variant["m2"],
                        "expected": {"intent": "support", "written_so_far": 0},
                    },
                    {"click": "decline", "expected": written(0)},
                ],
            }
        )
    return examples


def build(sentences: dict) -> str:
    """The set as JSON lines: the dev examples, then the test examples."""
    examples = dev_examples() + test_examples(sentences)
    return "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in examples)


def main() -> None:
    """Run the command line entry point."""
    text = build(json.loads(SENTENCES.read_text(encoding="utf-8")))
    MULTI_TURN_SET.write_text(text, encoding="utf-8")
    print(f"{text.count(chr(10))} examples written to {MULTI_TURN_SET.name}")


if __name__ == "__main__":
    main()
