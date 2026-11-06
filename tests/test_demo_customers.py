"""Tests for the demo customers offered on the page."""

from src import messages
from src.rules.returns import DecisionCode, check_return
from src.tools.orders import list_customer_orders
from src.tools.session import open_session
from src.ui.demo_customers import SITUATIONS, demo_customers


def by_situation(conn):
    return {customer.situation: customer for customer in demo_customers(conn)}


def test_every_situation_has_a_turkish_label():
    assert set(SITUATIONS) == set(messages.DEMO_CUSTOMER_LABELS)


def test_customers_carry_situation_label(synthetic_db):
    found = demo_customers(synthetic_db)

    assert found
    for customer in found:
        assert customer.label == messages.DEMO_CUSTOMER_LABELS[customer.situation]
        assert customer.customer_unique_id not in customer.label


def test_selection_is_the_same_every_time(synthetic_db):
    assert demo_customers(synthetic_db) == demo_customers(synthetic_db)


def test_recent_customer_can_return(synthetic_db):
    customer = by_situation(synthetic_db)["recent_delivery"]
    session = open_session(synthetic_db, customer.customer_unique_id)
    orders = list_customer_orders(session, synthetic_db, limit=50)["orders"]

    decisions = {
        check_return(
            synthetic_db,
            session.order_id_for(order["order"]),
            customer.customer_unique_id,
            "changed_mind",
        ).code
        for order in orders
    }

    assert DecisionCode.ELIGIBLE in decisions


def test_in_transit_customer_order_shipped(synthetic_db):
    customer = by_situation(synthetic_db)["in_transit"]

    statuses = {
        row[0]
        for row in synthetic_db.execute(
            "SELECT o.order_status FROM orders AS o JOIN customers AS c "
            "ON c.customer_id = o.customer_id WHERE c.customer_unique_id = ?",
            (customer.customer_unique_id,),
        )
    }

    assert "shipped" in statuses


def test_situation_nobody_is_in_is_left_out(synthetic_db):
    synthetic_db.execute("UPDATE orders SET order_status = 'delivered'")

    assert "in_transit" not in by_situation(synthetic_db)
