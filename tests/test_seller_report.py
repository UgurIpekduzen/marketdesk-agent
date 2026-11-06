"""Tests for the seller report, on the synthetic database.

The synthetic database has one seller (s_main, 24 items); the fixture here
gives one item of o_two_items to a second seller, s_other. Numbers are
checked against the seller-state groups of the same metrics, which reach
them by another way, and against worked-out values.
"""

import json

import pytest

from src import messages, messages_en
from src.formatting import (
    how_computed,
    report_computation,
    seller_report_sources,
    seller_report_table,
)
from src.i18n import Language
from src.knowledge.seller_report import (
    DETAIL_METRICS,
    RANKING_METRIC,
    build_seller_report,
)
from src.knowledge.semantic_layer import load_semantic_layer, run_metric

MAIN, OTHER = "S-0001", "S-0002"


@pytest.fixture
def two_sellers(synthetic_db):
    synthetic_db.executescript(
        """
        INSERT INTO sellers (seller_id, seller_city, seller_state)
            VALUES ('s_other', 'rio de janeiro', 'RJ');
        UPDATE order_items SET seller_id = 's_other'
            WHERE order_id = 'o_two_items' AND order_item_id = 2;
        """
    )
    return synthetic_db


def by_seller(report: dict) -> dict:
    return {row["seller"]: row for row in report["rows"]}


def test_sellers_show_pseudonym_and_numbers(two_sellers):
    report = build_seller_report(two_sellers, min_items=1)

    sellers = by_seller(report)
    assert set(sellers) == {MAIN, OTHER}
    assert sellers[MAIN]["items"] == 24
    assert sellers[OTHER]["items"] == 1
    assert sellers[OTHER]["orders"] == 1
    assert sellers[OTHER]["gmv"] == pytest.approx(50.00)
    assert sellers[MAIN]["gmv"] == pytest.approx(3670.01 - 50.00)


def test_numbers_match_metrics_by_state(two_sellers):
    sellers = by_seller(build_seller_report(two_sellers, min_items=1))

    for metric, field in ((RANKING_METRIC, "late_rate"), *DETAIL_METRICS.items()):
        for seller, state in ((MAIN, "SP"), (OTHER, "RJ")):
            result = run_metric(
                two_sellers, metric, {"seller_state": [state]}, ["seller_state"]
            )
            rows = result["rows"]
            value = rows[0][result["columns"].index("value")] if rows else None
            assert sellers[seller][field] == pytest.approx(value), (metric, seller)


def test_rows_ordered_by_late_rate_desc(two_sellers):
    rates = [
        row["late_rate"]
        for row in build_seller_report(two_sellers, min_items=1)["rows"]
    ]

    assert rates == sorted(rates, reverse=True)
    assert len(rates) == 2


def test_small_seller_is_left_out(two_sellers):
    report = build_seller_report(two_sellers, min_items=2)

    assert set(by_seller(report)) == {MAIN}
    assert report["min_items"] == 2


def test_report_respects_row_limit(two_sellers):
    assert len(build_seller_report(two_sellers, min_items=1, rows=1)["rows"]) == 1


def test_no_one_over_threshold_is_empty(two_sellers):
    report = build_seller_report(two_sellers, min_items=1000)

    assert report["rows"] == []
    # Only the ranking was asked; no query for sellers that are not there.
    assert [source["metric"] for source in report["sources"]] == [RANKING_METRIC]


def test_every_number_has_its_source(two_sellers):
    report = build_seller_report(two_sellers, min_items=1)

    assert [source["metric"] for source in report["sources"]] == [
        RANKING_METRIC,
        *DETAIL_METRICS,
    ]
    for source in report["sources"]:
        assert source["sql"].lstrip().upper().startswith("SELECT")
        assert source["group_by"] == ["seller_key"]
    detail = report["sources"][1]
    assert detail["filters"]["seller_key"] == [row["seller"] for row in report["rows"]]


def test_every_metric_brings_its_caveat(two_sellers):
    metrics = load_semantic_layer().metrics

    for language in Language:
        report = build_seller_report(two_sellers, min_items=1, language=language)
        assert {item["metric"]: item["caveat"] for item in report["caveats"]} == {
            name: metrics[name].caveat_in(language)
            for name in (RANKING_METRIC, *DETAIL_METRICS)
        }


def test_no_real_seller_id_is_in_the_report(two_sellers):
    report = build_seller_report(two_sellers, min_items=1)

    text = json.dumps(report)
    assert "s_main" not in text
    assert "s_other" not in text
    # Nor does the SQL carry the id out: the pseudonym is built from the row number.
    assert "seller_id" not in text.split('"sql"')[0]


def test_the_period_limits_every_number(two_sellers):
    everything = by_seller(build_seller_report(two_sellers, min_items=1))
    later = build_seller_report(
        two_sellers, min_items=1, period={"purchase_from": "2018-07-01"}
    )

    assert later["rows"] == [] or (
        by_seller(later)[MAIN]["items"] < everything[MAIN]["items"]
    )
    assert later["sources"][0]["filters"] == {"purchase_from": "2018-07-01"}


def test_bad_period_returns_metric_error(two_sellers):
    report = build_seller_report(
        two_sellers, min_items=1, period={"purchase_from": "yesterday"}
    )

    assert report["error"] == "INVALID_FILTER"


def test_unreviewed_seller_has_empty_score(two_sellers):
    two_sellers.execute("DELETE FROM order_reviews")

    for row in build_seller_report(two_sellers, min_items=1)["rows"]:
        assert row["avg_review_score"] is None


def test_headers_and_percentage_rate(
    two_sellers,
):
    report = build_seller_report(two_sellers, min_items=1)

    for language, texts in ((Language.TR, messages), (Language.EN, messages_en)):
        table = seller_report_table(report, language)
        assert table["columns"] == list(texts.SELLER_REPORT_COLUMNS.values())
        assert table["rows"][0][2] == pytest.approx(
            report["rows"][0]["late_rate"] * 100
        )
    # Whole numbers are written as whole numbers, the others are not.
    assert table["numbers"] == {
        "Items": True,
        "Late shipping rate (%)": False,
        "Orders": True,
        "GMV (BRL)": False,
        "Avg. review score": False,
    }


def test_sources_are_told_in_words(
    two_sellers,
):
    report = build_seller_report(two_sellers, min_items=2)

    (ranking, *details) = [
        how_computed(report_computation(source)) for source in report["sources"]
    ]
    assert "en az 2 kalem" in ranking
    assert messages.COMPUTED_REPORT_SELLERS not in ranking
    assert len(details) == 3
    assert all(line.endswith(messages.COMPUTED_REPORT_SELLERS) for line in details)
    # The sellers themselves are not listed in the words.
    assert not any(MAIN in line for line in details)
    assert [sql for _, sql in seller_report_sources(report)] == [
        source["sql"] for source in report["sources"]
    ]
