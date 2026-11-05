"""Order lookups for the customer in the session.

Both functions take the customer from the session, never from a parameter,
and filter by it in the query itself. Outputs are built field by field: they
hold order aliases instead of raw ids, and no customer id, city or zip code.
"""

import sqlite3
from datetime import date
from decimal import Decimal

import config
from src import messages
from src.formatting import format_money
from src.i18n import DEFAULT_LANGUAGE, Language
from src.rules.returns import sum_money, to_calendar_day
from src.tools.session import Session

ORDER_STATUSES = (
    "created",
    "approved",
    "invoiced",
    "processing",
    "shipped",
    "delivered",
    "canceled",
    "unavailable",
)

DEFAULT_LIST_LIMIT = 5
MAX_LIST_LIMIT = 20

# An order marked delivered on a day that has not come yet counts as still
# on its way (R3), so it is shown as shipped, without a delivery day.
SHOWN_STATUS_SQL = (
    "CASE WHEN o.order_status = 'delivered' "
    "AND DATE(o.order_delivered_customer_date) > DATE(:today) "
    "THEN 'shipped' ELSE o.order_status END"
)

ORDER_COLUMNS_SQL = (
    f"o.order_id, {SHOWN_STATUS_SQL} AS shown_status, "
    "o.order_purchase_timestamp, o.order_delivered_carrier_date, "
    "o.order_delivered_customer_date, o.order_estimated_delivery_date"
)

NOT_FOUND = {"error": "NOT_FOUND", "message": messages.ORDER_NOT_FOUND}


def day_text(timestamp: str | None) -> str | None:
    """Turn a stored timestamp into a calendar day such as 2018-08-25.

    Args:
        timestamp (str | None): A stored timestamp, or None.

    Returns:
        The calendar day as text, or None.
    """
    day = to_calendar_day(timestamp)
    return day.isoformat() if day else None


def read_items(
    conn: sqlite3.Connection, order_id: str, language: Language = DEFAULT_LANGUAGE
) -> list[dict]:
    """Read the items of an order: category, price and freight, no ids.

    Args:
        conn (sqlite3.Connection): A connection to the database.
        order_id (str): The order.
        language (Language): The session's language.

    Returns:
        The items with category, price and freight.
    """
    rows = conn.execute(
        "SELECT COALESCE(t.product_category_name_english, p.product_category_name), "
        "i.price, i.freight_value "
        "FROM order_items AS i "
        "LEFT JOIN products AS p ON p.product_id = i.product_id "
        "LEFT JOIN product_category_name_translation AS t "
        "ON t.product_category_name = p.product_category_name "
        "WHERE i.order_id = ? ORDER BY i.order_item_id",
        (order_id,),
    ).fetchall()
    items = []
    for category, price, freight in rows:
        price_text, freight_text = str(sum_money([price])), str(sum_money([freight]))
        items.append(
            {
                "category": category,
                "price": price_text,
                "price_text": format_money(price_text, language),
                "freight": freight_text,
                "freight_text": format_money(freight_text, language),
            }
        )
    return items


def items_total(items: list[dict]) -> str:
    """Add up price and freight over all items.

    Args:
        items (list[dict]): The order's items.

    Returns:
        The sum of price and freight.
    """
    amounts = (Decimal(item["price"]) + Decimal(item["freight"]) for item in items)
    return str(sum(amounts, Decimal("0.00")))


def get_order_status(
    session: Session,
    conn: sqlite3.Connection,
    order_ref: str,
    today: date = config.SIMULATED_TODAY,
) -> dict:
    """Return the status, dates and items of one order of the current customer.

    order_ref is the order alias from an earlier answer (for example SIP-1)
    or the order number the customer wrote. Dates are calendar days and
    amounts are in BRL; each amount has a _text field that writes it for
    the customer (for example "133,14 BRL"). If the customer has no such order the \
result is
    {"error": "NOT_FOUND", "message": ...}.
    """
    row = conn.execute(
        f"SELECT {ORDER_COLUMNS_SQL} "
        "FROM orders AS o "
        "JOIN customers AS c ON c.customer_id = o.customer_id "
        "WHERE o.order_id = :order_id AND c.customer_unique_id = :customer",
        {
            "order_id": session.order_id_for(order_ref),
            "customer": session.customer_unique_id,
            "today": today.isoformat(),
        },
    ).fetchone()
    if row is None:
        return dict(NOT_FOUND)

    order_id, status, purchased, handed_over, delivered, estimated = row
    items = read_items(conn, order_id, session.language)
    return {
        "order": session.alias_for(order_id),
        "status": status,
        "purchased_on": day_text(purchased),
        "handed_to_carrier_on": day_text(handed_over),
        "delivered_on": day_text(delivered) if status == "delivered" else None,
        "estimated_delivery_on": day_text(estimated),
        "items": items,
        "items_total": items_total(items),
        "items_total_text": format_money(items_total(items), session.language),
    }


def list_customer_orders(
    session: Session,
    conn: sqlite3.Connection,
    limit: int = DEFAULT_LIST_LIMIT,
    status: str | None = None,
    today: date = config.SIMULATED_TODAY,
) -> dict:
    """List the current customer's orders, newest first.

    limit is how many orders to return (1 to 20, default 5). status, if
    given, keeps only orders in that status: created, approved, invoiced,
    processing, shipped, delivered, canceled or unavailable. Each order
    comes with its alias (for example SIP-1), which the other order tools
    accept. Dates are calendar days and amounts are in BRL; items_total_text
    writes the total for the customer (for example "133,14 BRL").
    """
    if status is not None and status not in ORDER_STATUSES:
        return {
            "error": "INVALID_STATUS",
            "message": messages.INVALID_ORDER_STATUS.format(
                allowed=", ".join(ORDER_STATUSES)
            ),
        }
    limit = min(max(limit, 1), MAX_LIST_LIMIT)

    rows = conn.execute(
        f"SELECT {ORDER_COLUMNS_SQL} "
        "FROM orders AS o "
        "JOIN customers AS c ON c.customer_id = o.customer_id "
        "WHERE c.customer_unique_id = :customer "
        "AND (:status IS NULL OR shown_status = :status) "
        "ORDER BY o.order_purchase_timestamp DESC, o.order_id "
        "LIMIT :limit",
        {
            "customer": session.customer_unique_id,
            "status": status,
            "today": today.isoformat(),
            "limit": limit,
        },
    ).fetchall()

    orders = []
    for order_id, shown_status, purchased, _, delivered, estimated in rows:
        total = items_total(read_items(conn, order_id, session.language))
        orders.append(
            {
                "order": session.alias_for(order_id),
                "status": shown_status,
                "purchased_on": day_text(purchased),
                "delivered_on": (
                    day_text(delivered) if shown_status == "delivered" else None
                ),
                "estimated_delivery_on": day_text(estimated),
                "items_total": total,
                "items_total_text": format_money(total, session.language),
            }
        )
    return {"orders": orders}
