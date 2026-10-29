"""Tests for scripts/smoke.py, on the same synthetic data as the loader tests."""

import hashlib
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from scripts import load_sqlite, smoke
from tests.test_load_sqlite import write_raw

SIMULATED_TODAY = date(2018, 9, 1)

# What the synthetic rows in test_load_sqlite.ROWS produce.
EXPECTED = smoke.Expected(
    raw_rows={
        "olist_orders_dataset.csv": 3,
        "olist_customers_dataset.csv": 3,
        "olist_order_items_dataset.csv": 3,
    },
    raw_order_status={"delivered": 1, "canceled": 1, "shipped": 1},
    raw_distinct_customers=2,
    db_rows={"orders": 2, "customers": 2, "order_items": 2, "order_reviews": 2},
    order_status={"delivered": 1, "shipped": 1},
    distinct_customers=1,
)


@pytest.fixture
def raw_dir(tmp_path):
    return write_raw(tmp_path / "raw")


@pytest.fixture
def db_path(raw_dir, tmp_path):
    path = tmp_path / "marketdesk.db"
    load_sqlite.build_database(raw_dir, path, SIMULATED_TODAY)
    return path


def run(db_path, raw_dir, expected=EXPECTED):
    return smoke.run_checks(db_path, raw_dir, expected, SIMULATED_TODAY)


def failed_names(checks):
    return [check.name for check in checks if not check.ok]


def execute(db_path, sql):
    conn = sqlite3.connect(db_path)
    conn.execute(sql)
    conn.commit()
    conn.close()


def test_correct_database_passes_all_checks(db_path, raw_dir):
    checks = run(db_path, raw_dir)

    assert failed_names(checks) == []
    assert any(check.name == "return_requests table exists" for check in checks)


def test_wrong_row_count_reports_both(db_path, raw_dir):
    wrong = smoke.Expected(
        raw_rows=EXPECTED.raw_rows,
        raw_order_status=EXPECTED.raw_order_status,
        raw_distinct_customers=EXPECTED.raw_distinct_customers,
        db_rows={**EXPECTED.db_rows, "orders": 99},
        order_status=EXPECTED.order_status,
        distinct_customers=EXPECTED.distinct_customers,
    )

    checks = run(db_path, raw_dir, wrong)

    assert failed_names(checks) == ["orders rows"]
    message = str(next(check for check in checks if not check.ok))
    assert message == "FAIL  orders rows: expected 99, found 2"


def test_wrong_raw_row_count_fails(db_path, raw_dir):
    with (raw_dir / "olist_orders_dataset.csv").open("a") as handle:
        handle.write("o9,c9,delivered,2018-01-01 00:00:00,,,,\n")

    assert failed_names(run(db_path, raw_dir)) == [
        "raw olist_orders_dataset.csv rows",
        "raw orders with status delivered",
    ]


def test_unexpected_raw_status_is_reported(db_path, raw_dir):
    path = raw_dir / "olist_orders_dataset.csv"
    path.write_text(path.read_text().replace("o3,c3,shipped", "o3,c3,lost"))

    assert failed_names(run(db_path, raw_dir)) == [
        "raw orders with status lost",
        "raw orders with status shipped",
    ]


def test_wrong_raw_distinct_customers_fails(db_path, raw_dir):
    path = raw_dir / "olist_customers_dataset.csv"
    path.write_text(path.read_text().replace("c3,u1", "c3,u3"))

    assert failed_names(run(db_path, raw_dir)) == ["raw distinct customer_unique_id"]


def test_unexpected_order_status_is_reported(db_path, raw_dir):
    execute(db_path, "UPDATE orders SET order_status = 'lost' WHERE order_id = 'o3'")

    assert failed_names(run(db_path, raw_dir)) == [
        "orders with status lost",
        "orders with status shipped",
    ]


def test_order_on_today_is_reported(db_path, raw_dir):
    execute(
        db_path,
        "UPDATE orders SET order_purchase_timestamp = '2018-09-01 00:00:00' "
        "WHERE order_id = 'o3'",
    )

    assert failed_names(run(db_path, raw_dir)) == [
        "orders purchased on or after 2018-09-01 (R0)"
    ]


def test_rows_without_an_order_are_reported(db_path, raw_dir):
    execute(
        db_path,
        "INSERT INTO order_payments (order_id, payment_sequential) VALUES ('gone', 1)",
    )

    assert failed_names(run(db_path, raw_dir)) == [
        "order_payments rows without an order"
    ]


def test_missing_requests_table_is_reported(db_path, raw_dir):
    execute(db_path, "DROP TABLE return_requests")

    assert failed_names(run(db_path, raw_dir)) == ["return_requests table exists"]


def test_request_rows_do_not_fail_the_check(db_path, raw_dir):
    execute(
        db_path,
        "INSERT INTO return_requests "
        "(order_id, customer_unique_id, refund_amount, status, created_at) "
        "VALUES ('o1', 'u1', 100.0, 'PENDING_REVIEW', '2018-09-01')",
    )

    assert failed_names(run(db_path, raw_dir)) == []


def test_missing_raw_folder_skips_raw_checks(db_path, tmp_path):
    checks = run(db_path, tmp_path / "no-raw-here")

    assert failed_names(checks) == []
    assert not any(check.name.startswith("raw ") for check in checks)


def test_missing_database_raises_clearly(raw_dir, tmp_path):
    with pytest.raises(FileNotFoundError, match="Run the load step first"):
        run(tmp_path / "missing.db", raw_dir)


def test_database_is_not_changed(db_path, raw_dir):
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    run(db_path, raw_dir)

    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before


def test_main_explains_a_missing_database(tmp_path, capsys):
    code = smoke.main(["--db", str(tmp_path / "missing.db"), "--src", str(tmp_path)])

    assert code == 1
    assert "Smoke test could not run" in capsys.readouterr().out


def test_main_returns_1_when_a_check_fails(db_path, raw_dir, capsys):
    # The synthetic database cannot match the real Olist numbers.
    code = smoke.main(["--db", str(db_path), "--src", str(raw_dir)])

    output = capsys.readouterr().out
    assert code == 1
    assert "FAIL  orders rows: expected 99,421, found 2" in output
    assert "Smoke test FAILED" in output


def test_runs_as_file_from_another_directory(tmp_path):
    script = Path(__file__).resolve().parent.parent / "scripts" / "smoke.py"

    result = subprocess.run(
        [sys.executable, str(script), "--db", str(tmp_path / "missing.db")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Smoke test could not run" in result.stdout
