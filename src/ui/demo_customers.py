"""Ready-made customers for the demo, picked from the database.

No id is written down anywhere: each customer is found by a query that
describes a situation worth trying, and is shown under that description.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

import config
from src import messages

# One delivered order of a customer, with the days it arrived after the
# estimate. Each situation below filters these rows.
DELIVERED = """
    SELECT c.customer_unique_id, o.order_id,
           DATE(o.order_delivered_customer_date) AS delivered_on,
           julianday(DATE(o.order_delivered_customer_date))
             - julianday(DATE(o.order_estimated_delivery_date)) AS days_late
    FROM orders AS o
    JOIN customers AS c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date <> ''
"""
# The situations, in the order they are offered. Every query returns one
# customer_unique_id and always the same one.
SITUATIONS = {
    "recent_delivery": f"""
        SELECT customer_unique_id FROM ({DELIVERED})
        WHERE delivered_on BETWEEN :short_window_start AND :today
          AND days_late < :delay_days
        ORDER BY delivered_on DESC, customer_unique_id LIMIT 1
    """,
    "late_delivery": f"""
        SELECT customer_unique_id FROM ({DELIVERED})
        WHERE delivered_on BETWEEN :short_window_start AND :today
          AND days_late >= :delay_days
        ORDER BY delivered_on DESC, customer_unique_id LIMIT 1
    """,
    "in_transit": """
        SELECT c.customer_unique_id FROM orders AS o
        JOIN customers AS c ON c.customer_id = o.customer_id
        WHERE o.order_status = 'shipped'
        ORDER BY o.order_purchase_timestamp DESC, c.customer_unique_id LIMIT 1
    """,
    "window_passed": f"""
        SELECT customer_unique_id FROM ({DELIVERED})
        GROUP BY customer_unique_id
        HAVING MAX(delivered_on) < :long_window_start
        ORDER BY MAX(delivered_on) DESC, customer_unique_id LIMIT 1
    """,
    "many_orders": """
        SELECT customer_unique_id FROM customers
        GROUP BY customer_unique_id
        ORDER BY COUNT(*) DESC, customer_unique_id LIMIT 1
    """,
}


@dataclass(frozen=True)
class DemoCustomer:
    situation: str
    label: str  # what the person choosing sees
    customer_unique_id: str  # never shown


def demo_customers(
    conn: sqlite3.Connection, today: date = config.SIMULATED_TODAY
) -> list[DemoCustomer]:
    """The customers to offer; a situation nobody is in is left out."""
    parameters = {
        "today": today.isoformat(),
        "short_window_start": (
            today - timedelta(days=config.RETURN_WINDOW_SHORT_DAYS)
        ).isoformat(),
        "long_window_start": (
            today - timedelta(days=config.RETURN_WINDOW_LONG_DAYS)
        ).isoformat(),
        "delay_days": config.FREIGHT_REFUND_DELAY_DAYS,
    }
    found = []
    for situation, query in SITUATIONS.items():
        row = conn.execute(query, parameters).fetchone()
        if row is not None:
            found.append(
                DemoCustomer(
                    situation, messages.DEMO_CUSTOMER_LABELS[situation], row[0]
                )
            )
    return found
