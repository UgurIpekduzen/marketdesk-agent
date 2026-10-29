"""Tests for the order lookups, on the synthetic database."""

import json
import re

import pytest

from src import messages
from src.tools.orders import ORDER_STATUSES, get_order_status, list_customer_orders
from src.tools.session import Session
from tests.synthetic_data import ALICE, BOB

NOT_FOUND = {"error": "NOT_FOUND", "message": messages.ORDER_NOT_FOUND}

ORDER_FIELDS = {
    "order",
    "status",
    "purchased_on",
    "handed_to_carrier_on",
    "delivered_on",
    "estimated_delivery_on",
    "items",
    "items_total",
    "items_total_text",
}
ITEM_FIELDS = {"category", "price", "price_text", "freight", "freight_text"}
LISTED_ORDER_FIELDS = {
    "order",
    "status",
    "purchased_on",
    "delivered_on",
    "estimated_delivery_on",
    "items_total",
    "items_total_text",
}

# An order id shaped like the real ones: 32 hexadecimal characters.
REAL_SHAPED_ORDER_ID = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"
RAW_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


@pytest.fixture
def alice():
    return Session(ALICE)


@pytest.fixture
def bob():
    return Session(BOB)


# --- get_order_status ---------------------------------------------------


def test_order_status_of_an_own_order(synthetic_db, alice):
    assert get_order_status(alice, synthetic_db, "o_two_items") == {
        "order": "SIP-1",
        "status": "delivered",
        "purchased_on": "2018-06-15",
        "handed_to_carrier_on": "2018-06-18",
        "delivered_on": "2018-08-25",
        "estimated_delivery_on": "2018-08-30",
        "items": [
            {
                "category": "furniture_decor",
                "price": "100.00",
                "price_text": "100,00 BRL",
                "freight": "10.00",
                "freight_text": "10,00 BRL",
            },
            {
                "category": "furniture_decor",
                "price": "50.00",
                "price_text": "50,00 BRL",
                "freight": "5.00",
                "freight_text": "5,00 BRL",
            },
        ],
        "items_total": "165.00",
        "items_total_text": "165,00 BRL",
    }


def test_unshipped_order_has_no_carrier_day(synthetic_db, alice):
    order = get_order_status(alice, synthetic_db, "o_processing")

    assert order["status"] == "processing"
    assert order["handed_to_carrier_on"] is None
    assert order["delivered_on"] is None


def test_future_delivery_shows_as_shipped(synthetic_db, alice):
    order = get_order_status(alice, synthetic_db, "o_delivered_future")

    assert order["status"] == "shipped"
    assert order["delivered_on"] is None
    assert order["estimated_delivery_on"] == "2018-09-10"


def test_order_is_found_again_by_its_alias(synthetic_db, alice):
    first = get_order_status(alice, synthetic_db, "o_day14")

    assert get_order_status(alice, synthetic_db, first["order"]) == first


def test_ten_foreign_orders_not_found(synthetic_db, bob):
    alice_orders = [
        row[0]
        for row in synthetic_db.execute(
            "SELECT o.order_id FROM orders AS o "
            "JOIN customers AS c ON c.customer_id = o.customer_id "
            "WHERE c.customer_unique_id = ? ORDER BY o.order_id LIMIT 10",
            (ALICE,),
        )
    ]
    assert len(alice_orders) == 10

    answers = [get_order_status(bob, synthetic_db, order) for order in alice_orders]

    assert answers == [NOT_FOUND] * 10


def test_foreign_missing_unknown_same_answer(synthetic_db, alice):
    foreign = get_order_status(alice, synthetic_db, "o_other_customer")
    missing = get_order_status(alice, synthetic_db, "o_does_not_exist")
    unknown_alias = get_order_status(alice, synthetic_db, "SIP-7")
    left_out_at_load = get_order_status(alice, synthetic_db, "o_purchased_today")

    assert foreign == missing == unknown_alias == left_out_at_load == NOT_FOUND


def test_other_session_alias_not_found(synthetic_db, alice, bob):
    alias = get_order_status(alice, synthetic_db, "o_day14")["order"]

    assert get_order_status(bob, synthetic_db, alias) == NOT_FOUND


def test_a_failed_lookup_hands_out_no_alias(synthetic_db, alice):
    get_order_status(alice, synthetic_db, "o_other_customer")

    assert get_order_status(alice, synthetic_db, "o_day14")["order"] == "SIP-1"


# --- list_customer_orders -----------------------------------------------


def test_list_has_only_own_orders(synthetic_db, bob):
    listed = list_customer_orders(bob, synthetic_db)

    assert len(listed["orders"]) == 1
    assert get_order_status(bob, synthetic_db, "o_other_customer")["order"] == "SIP-1"


def test_list_is_newest_first(synthetic_db, alice):
    synthetic_db.execute(
        "UPDATE orders SET order_purchase_timestamp = '2018-08-20 09:00:00' "
        "WHERE order_id = 'o_shipped'"
    )
    synthetic_db.execute(
        "UPDATE orders SET order_purchase_timestamp = '2018-08-10 09:00:00' "
        "WHERE order_id = 'o_processing'"
    )

    orders = list_customer_orders(alice, synthetic_db, limit=3)["orders"]

    assert [order["purchased_on"] for order in orders] == [
        "2018-08-20",
        "2018-08-10",
        "2018-06-15",
    ]
    assert [order["status"] for order in orders[:2]] == ["shipped", "processing"]


@pytest.mark.parametrize(
    ("limit", "count"), [(3, 3), (0, 1), (-5, 1), (20, 20), (500, 20)]
)
def test_list_limit_is_kept_between_1_and_20(synthetic_db, alice, limit, count):
    assert (
        len(list_customer_orders(alice, synthetic_db, limit=limit)["orders"]) == count
    )


def test_list_default_limit_is_five(synthetic_db, alice):
    assert len(list_customer_orders(alice, synthetic_db)["orders"]) == 5


def test_list_can_be_filtered_by_status(synthetic_db, alice):
    orders = list_customer_orders(alice, synthetic_db, status="canceled")["orders"]

    assert [order["status"] for order in orders] == ["canceled"]


def test_status_filter_uses_the_shown_status(synthetic_db, alice):
    # o_shipped and o_delivered_future: the second is stored as delivered.
    shipped = list_customer_orders(alice, synthetic_db, status="shipped")["orders"]
    delivered = list_customer_orders(alice, synthetic_db, limit=20, status="delivered")[
        "orders"
    ]

    assert len(shipped) == 2
    assert all(order["delivered_on"] is None for order in shipped)
    assert "2018-09-05" not in [order["delivered_on"] for order in delivered]


def test_unknown_status_lists_allowed(synthetic_db, alice):
    answer = list_customer_orders(alice, synthetic_db, status="lost")

    assert answer["error"] == "INVALID_STATUS"
    for status in ORDER_STATUSES:
        assert status in answer["message"]


def test_listed_alias_opens_the_same_order(synthetic_db, alice):
    listed = list_customer_orders(alice, synthetic_db, status="unavailable")["orders"][
        0
    ]

    order = get_order_status(alice, synthetic_db, listed["order"])

    assert order["status"] == "unavailable"
    assert order["items_total"] == listed["items_total"]


# --- What the outputs may contain ---------------------------------------


def test_outputs_have_only_allowed_fields(synthetic_db, alice):
    order = get_order_status(alice, synthetic_db, "o_two_items")
    listed = list_customer_orders(alice, synthetic_db, limit=20)["orders"]

    assert set(order) == ORDER_FIELDS
    assert all(set(item) == ITEM_FIELDS for item in order["items"])
    assert all(set(entry) == LISTED_ORDER_FIELDS for entry in listed)


def test_outputs_have_no_raw_id_city_zip(synthetic_db, alice):
    # Give one of Alice's orders an id shaped like the real ones.
    for table in ("orders", "order_items", "order_payments"):
        synthetic_db.execute(
            f"UPDATE {table} SET order_id = ? WHERE order_id = 'o_day14'",
            (REAL_SHAPED_ORDER_ID,),
        )

    outputs = json.dumps(
        [
            # The customer types the raw order number; the answer has an alias.
            get_order_status(alice, synthetic_db, REAL_SHAPED_ORDER_ID),
            list_customer_orders(alice, synthetic_db, limit=20),
            get_order_status(alice, synthetic_db, "o_other_customer"),
            list_customer_orders(alice, synthetic_db, status="lost"),
        ]
    )

    assert '"status": "delivered"' in outputs
    assert RAW_ID_PATTERN.search(outputs) is None
    for forbidden in (
        ALICE,
        "c_o_",
        "o_day",
        "p_chair",
        "s_main",
        "sao paulo",
        "01310",
    ):
        assert forbidden not in outputs
