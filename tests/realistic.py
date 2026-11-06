"""Gives the synthetic database ids shaped like the real ones.

The hand-written ids ("o_day14") are easy to read in tests, but nothing
like the 32 hexadecimal characters of the real data. The outbound guard and
the model both behave differently on real-shaped ids, so the leak test and
the live check of the agent run on a database converted with this module.
"""

import hashlib
import sqlite3

CITY = "campinas"
ZIP_PREFIX = "13010"


def real_shaped(value: str) -> str:
    """The id a synthetic value gets: 32 hexadecimal characters."""
    return hashlib.md5(value.encode(), usedforsecurity=False).hexdigest()


def make_realistic(conn: sqlite3.Connection) -> None:
    """Replace every id in the database and give customers a city and zip code."""
    conn.create_function("real_shaped", 1, real_shaped)
    conn.executescript(
        f"""
        UPDATE orders SET order_id = real_shaped(order_id),
            customer_id = real_shaped(customer_id);
        UPDATE customers SET customer_id = real_shaped(customer_id),
            customer_unique_id = real_shaped(customer_unique_id),
            customer_city = '{CITY}', customer_zip_code_prefix = '{ZIP_PREFIX}';
        UPDATE order_items SET order_id = real_shaped(order_id),
            product_id = real_shaped(product_id), seller_id = real_shaped(seller_id);
        UPDATE order_payments SET order_id = real_shaped(order_id);
        UPDATE order_reviews SET order_id = real_shaped(order_id),
            review_id = real_shaped(review_id);
        UPDATE products SET product_id = real_shaped(product_id);
        UPDATE sellers SET seller_id = real_shaped(seller_id), seller_city = '{CITY}';
        UPDATE return_requests SET order_id = real_shaped(order_id),
            customer_unique_id = real_shaped(customer_unique_id);
        """
    )
    conn.commit()
