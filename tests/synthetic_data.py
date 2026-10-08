"""Hand-written orders for the tests: one or more for every return rule.

Nothing here comes from the Olist dataset. Order ids say what the order is
for. "Today" is 2018-09-01, so a delivery on 2018-08-18 is 14 days old.

Unless an order says otherwise it belongs to ALICE, was delivered on time,
has one item (100.00 + 15.00 freight) and was paid by credit card.

The return reason (changed_mind, late, damaged, wrong_item) is not stored
with an order: the customer gives it when asking, so the same order is used
with several reasons.
"""

ALICE = "u_alice"
BOB = "u_bob"

PURCHASED = "2018-06-15 10:00:00"
HANDED_TO_CARRIER = "2018-06-18 09:00:00"
SHIPPING_LIMIT = "2018-06-20 09:00:00"
NOT_DELIVERED_ESTIMATE = "2018-09-10 00:00:00"

# Each order: id, status, delivered (customer date) and estimated delivery.
# Optional keys: customer, purchased, carrier, payments [(type, value)] and
# items [(price, freight)] or [(price, freight, shipping_limit)].
ORDERS = [
    # --- R0: purchased on the simulated today, left out when loading ----
    {
        "id": "o_purchased_today",
        "status": "canceled",
        "purchased": "2018-09-01 00:00:00",
        "delivered": None,
        "estimated": NOT_DELIVERED_ESTIMATE,
        "carrier": None,
    },
    # --- R1: belongs to another customer --------------------------------
    {
        "id": "o_other_customer",
        "customer": BOB,
        "status": "delivered",
        "delivered": "2018-08-25 15:30:00",
        "estimated": "2018-08-30 00:00:00",
    },
    # --- R2: not delivered yet, can be cancelled ------------------------
    {
        "id": "o_created",
        "status": "created",
        "delivered": None,
        "estimated": NOT_DELIVERED_ESTIMATE,
        "carrier": None,
    },
    {
        "id": "o_approved",
        "status": "approved",
        "delivered": None,
        "estimated": NOT_DELIVERED_ESTIMATE,
        "carrier": None,
    },
    {
        "id": "o_invoiced",
        "status": "invoiced",
        "delivered": None,
        "estimated": NOT_DELIVERED_ESTIMATE,
        "carrier": None,
    },
    {
        "id": "o_processing",
        "status": "processing",
        "delivered": None,
        "estimated": NOT_DELIVERED_ESTIMATE,
        "carrier": None,
    },
    # --- R3: on its way --------------------------------------------------
    {
        "id": "o_shipped",
        "status": "shipped",
        "delivered": None,
        "estimated": NOT_DELIVERED_ESTIMATE,
    },
    {
        # Marked delivered, but the delivery date is after the simulated today.
        "id": "o_delivered_future",
        "status": "delivered",
        "delivered": "2018-09-05 11:00:00",
        "estimated": "2018-09-10 00:00:00",
    },
    # --- R4: closed ------------------------------------------------------
    {
        "id": "o_canceled",
        "status": "canceled",
        "delivered": None,
        "estimated": NOT_DELIVERED_ESTIMATE,
        "carrier": None,
    },
    {
        "id": "o_unavailable",
        "status": "unavailable",
        "delivered": None,
        "estimated": NOT_DELIVERED_ESTIMATE,
        "carrier": None,
    },
    # --- R5: delivered without a delivery date --------------------------
    {
        "id": "o_no_delivery_date",
        "status": "delivered",
        "delivered": None,
        "estimated": "2018-08-20 00:00:00",
    },
    # --- R6 / R7: window boundaries -------------------------------------
    {
        "id": "o_day0",
        "status": "delivered",
        "delivered": "2018-09-01 18:00:00",
        "estimated": "2018-09-06 00:00:00",
    },
    {
        "id": "o_day14",
        "status": "delivered",
        "delivered": "2018-08-18 23:50:00",
        "estimated": "2018-08-23 00:00:00",
    },
    {
        "id": "o_day15",
        "status": "delivered",
        "delivered": "2018-08-17 00:10:00",
        "estimated": "2018-08-22 00:00:00",
    },
    {
        "id": "o_day30",
        "status": "delivered",
        "delivered": "2018-08-02 23:50:00",
        "estimated": "2018-08-07 00:00:00",
    },
    {
        "id": "o_day31",
        "status": "delivered",
        "delivered": "2018-08-01 00:10:00",
        "estimated": "2018-08-06 00:00:00",
    },
    # --- R9 / R8: late delivery and freight refund ----------------------
    {
        # Exactly 10 days late, 7 days ago: flagged and inside the window.
        "id": "o_late_10",
        "status": "delivered",
        "delivered": "2018-08-25 15:30:00",
        "estimated": "2018-08-15 00:00:00",
    },
    {
        # 9 days late: one day short of the flag.
        "id": "o_late_9",
        "status": "delivered",
        "delivered": "2018-08-25 15:30:00",
        "estimated": "2018-08-16 00:00:00",
    },
    {
        # 16 days late, 22 days ago: outside 14 days, inside 30: freight only.
        "id": "o_late_freight_only",
        "status": "delivered",
        "delivered": "2018-08-10 15:30:00",
        "estimated": "2018-07-25 00:00:00",
    },
    {
        # 13 days late, exactly 30 days ago: the last day for a freight claim.
        "id": "o_late_day30",
        "status": "delivered",
        "delivered": "2018-08-02 15:30:00",
        "estimated": "2018-07-20 00:00:00",
    },
    {
        # 15 days late, 31 days ago: one day too old, nothing to refund.
        "id": "o_late_day31",
        "status": "delivered",
        "delivered": "2018-08-01 15:30:00",
        "estimated": "2018-07-17 00:00:00",
    },
    # --- R8: refund amount over several items ---------------------------
    {
        "id": "o_two_items",
        "status": "delivered",
        "delivered": "2018-08-25 15:30:00",
        "estimated": "2018-08-30 00:00:00",
        "items": [("100.00", "10.00"), ("50.00", "5.00")],
    },
    # --- R10: approval level around 500 BRL -----------------------------
    {
        # 500.00 without freight (not above the threshold), 520.00 with it.
        "id": "o_amount_500",
        "status": "delivered",
        "delivered": "2018-08-25 15:30:00",
        "estimated": "2018-08-30 00:00:00",
        "items": [("500.00", "20.00")],
    },
    {
        "id": "o_amount_over",
        "status": "delivered",
        "delivered": "2018-08-25 15:30:00",
        "estimated": "2018-08-30 00:00:00",
        "items": [("500.01", "20.00")],
    },
    # --- R11: a request already exists (see RETURN_REQUESTS) ------------
    {
        "id": "o_duplicate",
        "status": "delivered",
        "delivered": "2018-08-25 15:30:00",
        "estimated": "2018-08-30 00:00:00",
    },
    {
        # Outside every window: the duplicate check still comes first.
        "id": "o_duplicate_old",
        "status": "delivered",
        "delivered": "2018-07-01 15:30:00",
        "estimated": "2018-07-06 00:00:00",
    },
    # --- R12: part of the payment was a voucher (50 of 200) -------------
    {
        "id": "o_voucher",
        "status": "delivered",
        "delivered": "2018-08-25 15:30:00",
        "estimated": "2018-08-30 00:00:00",
        "items": [("180.00", "20.00")],
        "payments": [("voucher", "50.00"), ("credit_card", "150.00")],
    },
    # --- R13: the seller handed the parcel over after the limit ---------
    {
        "id": "o_seller_late",
        "status": "delivered",
        "delivered": "2018-08-25 15:30:00",
        "estimated": "2018-08-30 00:00:00",
        "carrier": "2018-06-22 09:00:00",
    },
    {
        # Two items; only the second one's limit was missed. One is enough.
        "id": "o_seller_late_one_item",
        "status": "delivered",
        "delivered": "2018-08-25 15:30:00",
        "estimated": "2018-08-30 00:00:00",
        "items": [
            ("100.00", "15.00"),
            ("40.00", "5.00", "2018-06-17 09:00:00"),
        ],
    },
    {
        # Handed over on the limit day, later in the day: same calendar day,
        # so not after the limit.
        "id": "o_seller_same_day",
        "status": "delivered",
        "delivered": "2018-08-25 15:30:00",
        "estimated": "2018-08-30 00:00:00",
        "carrier": "2018-06-20 18:00:00",
    },
]

# Requests that exist before any test runs (R11).
RETURN_REQUESTS = [
    {
        "order_id": "o_duplicate",
        "customer_unique_id": ALICE,
        "reason": "changed_mind",
        "refund_amount": "100.00",
        "status": "PENDING_REVIEW",
        "created_at": "2018-08-28 10:00:00",
    },
    {
        "order_id": "o_duplicate_old",
        "customer_unique_id": ALICE,
        "reason": "damaged",
        "refund_amount": "115.00",
        "status": "REJECTED",
        "created_at": "2018-07-05 10:00:00",
    },
]

DEFAULT_ITEMS = [("100.00", "15.00")]
MISSING = object()


def build_rows() -> dict[str, list[dict[str, str]]]:
    """Turn ORDERS into rows for each table, in the shape of the CSV files."""
    rows: dict[str, list[dict[str, str]]] = {
        "orders": [],
        "customers": [],
        "order_items": [],
        "order_payments": [],
        "order_reviews": [
            {"review_id": "r_day14", "order_id": "o_day14", "review_score": "5"},
            {"review_id": "r_late_10", "order_id": "o_late_10", "review_score": "2"},
        ],
        "products": [
            {"product_id": "p_chair", "product_category_name": "moveis_decoracao"},
        ],
        "sellers": [
            {"seller_id": "s_main", "seller_city": "sao paulo", "seller_state": "SP"},
        ],
        "geolocation": [
            {"geolocation_zip_code_prefix": "01310", "geolocation_state": "SP"},
        ],
        "product_category_name_translation": [
            {
                "product_category_name": "moveis_decoracao",
                "product_category_name_english": "furniture_decor",
            },
        ],
    }

    for order in ORDERS:
        order_id = order["id"]
        customer_id = f"c_{order_id}"
        carrier = order.get("carrier", MISSING)
        if carrier is MISSING:
            carrier = HANDED_TO_CARRIER
        # Give every item a shipping limit: its own, or the common default.
        items = [
            (*item, SHIPPING_LIMIT)[:3] for item in order.get("items", DEFAULT_ITEMS)
        ]
        total = sum(float(price) + float(freight) for price, freight, _ in items)
        payments = order.get("payments", [("credit_card", f"{total:.2f}")])

        rows["orders"].append(
            {
                "order_id": order_id,
                "customer_id": customer_id,
                "order_status": order["status"],
                "order_purchase_timestamp": order.get("purchased", PURCHASED),
                "order_delivered_carrier_date": carrier or "",
                "order_delivered_customer_date": order["delivered"] or "",
                "order_estimated_delivery_date": order["estimated"],
            }
        )
        rows["customers"].append(
            {
                "customer_id": customer_id,
                "customer_unique_id": order.get("customer", ALICE),
                "customer_zip_code_prefix": "01310",
                "customer_city": "sao paulo",
                "customer_state": "SP",
            }
        )
        for number, (price, freight, shipping_limit) in enumerate(items, start=1):
            rows["order_items"].append(
                {
                    "order_id": order_id,
                    "order_item_id": str(number),
                    "product_id": "p_chair",
                    "seller_id": "s_main",
                    "shipping_limit_date": shipping_limit,
                    "price": price,
                    "freight_value": freight,
                }
            )
        for number, (payment_type, value) in enumerate(payments, start=1):
            rows["order_payments"].append(
                {
                    "order_id": order_id,
                    "payment_sequential": str(number),
                    "payment_type": payment_type,
                    "payment_installments": "1",
                    "payment_value": value,
                }
            )
    return rows
