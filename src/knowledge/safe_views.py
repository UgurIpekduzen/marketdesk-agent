"""Safe views: the only things free SQL may read.

Each view shows chosen columns of the raw tables and nothing else. Free SQL
is allowed to name these views only, so a column that is not listed here
cannot be reached: the protection is a list of what is allowed, not a list
of what is forbidden.

What the views leave out: order, customer, product and seller ids, city,
zip code prefix, coordinates, and the title and text of reviews.

Rows are linked by keys that mean nothing outside this database
(order_key, customer_key, product_key, seller_key): they are row numbers,
not the real ids. customer_key is the same for all orders of one person.

This module is the single place the views are defined. The loader creates
them from SAFE_VIEWS, and the SQL validator takes its list of allowed names
from the same dict, so the two cannot drift apart.
"""

SAFE_VIEWS = {
    "v_orders": """
        SELECT
            o.rowid AS order_key,
            (SELECT MIN(same.rowid) FROM customers AS same
             WHERE same.customer_unique_id = c.customer_unique_id) AS customer_key,
            c.customer_state,
            o.order_status,
            o.order_purchase_timestamp,
            o.order_approved_at,
            o.order_delivered_carrier_date,
            o.order_delivered_customer_date,
            o.order_estimated_delivery_date
        FROM orders AS o
        JOIN customers AS c ON c.customer_id = o.customer_id
    """,
    "v_order_items": """
        SELECT
            o.rowid AS order_key,
            i.order_item_id,
            p.rowid AS product_key,
            COALESCE(t.product_category_name_english, p.product_category_name)
                AS product_category_en,
            s.rowid AS seller_key,
            s.seller_state,
            i.shipping_limit_date,
            i.price,
            i.freight_value
        FROM order_items AS i
        JOIN orders AS o ON o.order_id = i.order_id
        LEFT JOIN products AS p ON p.product_id = i.product_id
        LEFT JOIN product_category_name_translation AS t
            ON t.product_category_name = p.product_category_name
        LEFT JOIN sellers AS s ON s.seller_id = i.seller_id
    """,
    "v_order_payments": """
        SELECT
            o.rowid AS order_key,
            pay.payment_sequential,
            pay.payment_type,
            pay.payment_installments,
            pay.payment_value
        FROM order_payments AS pay
        JOIN orders AS o ON o.order_id = pay.order_id
    """,
    "v_order_reviews": """
        SELECT
            o.rowid AS order_key,
            r.review_score,
            r.review_creation_date,
            r.review_answer_timestamp
        FROM order_reviews AS r
        JOIN orders AS o ON o.order_id = r.order_id
    """,
    "v_return_requests": """
        SELECT
            rr.id AS return_request_key,
            o.rowid AS order_key,
            rr.reason,
            rr.refund_amount,
            rr.status,
            rr.created_at
        FROM return_requests AS rr
        JOIN orders AS o ON o.order_id = rr.order_id
    """,
}

ALLOWED_VIEWS = tuple(SAFE_VIEWS)


def create_view_statements() -> list[str]:
    """The CREATE VIEW statements, one per safe view."""
    return [
        f"CREATE VIEW {name} AS {' '.join(body.split())}"
        for name, body in SAFE_VIEWS.items()
    ]
