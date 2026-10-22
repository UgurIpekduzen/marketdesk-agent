"""The seller report: sellers ranked by late shipping, each number with its source.

The report is built from the metrics in metrics.yaml and nothing else, so
a number in it is the number the metric gives for the same question. The
sellers are shown by a pseudonym (S-0001), never by the real seller id.

Step 1 ranks the sellers by the late-shipping rate, among those with at
least min_items items. Step 2 asks the other metrics for exactly those
sellers. Every metric call is kept in "sources", with the SQL that ran.
"""

import sqlite3
from datetime import date

import config
from src.i18n import DEFAULT_LANGUAGE, Language
from src.knowledge.semantic_layer import load_semantic_layer, run_metric

RANKING_METRIC = "seller_late_shipping_rate"
# Metrics asked about the ranked sellers, as the column they fill.
DETAIL_METRICS = {
    "order_count": "orders",
    "gmv": "gmv",
    "avg_review_score": "avg_review_score",
}
SELLER = "seller_key"


def column(result: dict, name: str) -> list:
    return [row[result["columns"].index(name)] for row in result["rows"]]


def build_seller_report(
    conn: sqlite3.Connection,
    today: date = config.SIMULATED_TODAY,
    min_items: int | None = None,
    rows: int | None = None,
    period: dict | None = None,
    language: Language = DEFAULT_LANGUAGE,
) -> dict:
    """The sellers with the highest late-shipping rate, with their volume.

    period may hold purchase_from and purchase_to (YYYY-MM-DD). The answer
    holds the rows, the metric calls behind them ("sources") and the caveat
    of every metric used; an error answer from a metric is returned as it is.
    """
    # Read at the call, so a setting changed for a test or a run is used.
    min_items = min_items or config.SELLER_REPORT_MIN_ITEMS
    rows = rows or config.SELLER_REPORT_ROWS
    period = period or {}
    metrics = load_semantic_layer().metrics

    ranking_arguments = {"min_count": min_items, "order": "value_desc", "top": rows}
    ranking = run_metric(
        conn, RANKING_METRIC, period, [SELLER], today, **ranking_arguments
    )
    if "error" in ranking:
        return ranking
    sellers = column(ranking, SELLER)

    report_rows = {
        seller: {
            "seller": seller,
            "items": items,
            "late_items": late,
            "late_rate": rate,
            # None where a metric has nothing for the seller (no review).
            **dict.fromkeys(DETAIL_METRICS.values()),
        }
        for seller, items, late, rate in zip(
            sellers,
            column(ranking, "denominator"),
            column(ranking, "numerator"),
            column(ranking, "value"),
            strict=True,
        )
    }
    results = {RANKING_METRIC: ranking}
    # The same sellers for every other metric: no query for an empty report.
    for name, field in DETAIL_METRICS.items() if sellers else ():
        result = run_metric(conn, name, {**period, SELLER: sellers}, [SELLER], today)
        if "error" in result:
            return result
        results[name] = result
        for seller, value in zip(
            column(result, SELLER), column(result, "value"), strict=True
        ):
            report_rows[seller][field] = value

    return {
        "min_items": min_items,
        "rows": [report_rows[seller] for seller in sellers],
        "sources": [
            {
                "metric": name,
                "group_by": [SELLER],
                # The sellers of the table are the filter of every detail
                # metric; the ranking chose them.
                "filters": {
                    **period,
                    **({} if name == RANKING_METRIC else {SELLER: sellers}),
                },
                "ranking": ranking_arguments if name == RANKING_METRIC else {},
                "sql": result["sql"],
            }
            for name, result in results.items()
        ],
        "caveats": [
            {"metric": name, "caveat": metrics[name].caveat_in(language)}
            for name in results
        ],
    }
