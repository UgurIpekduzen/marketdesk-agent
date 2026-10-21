"""Tests for the evaluation scoring."""

from datetime import date

import pytest

from eval.scoring import (
    arguments_match,
    citations,
    citations_returned,
    contains_all,
    decision_of,
    execution_match,
    future_dates,
    last_table,
    matches_none,
    percentile,
    rate,
    tool_call_accuracy,
    ungrounded_numbers,
)

CHECK = {
    "name": "check_return_eligibility",
    "args": {"order_ref": "SIP-1", "reason": "damaged"},
}
CREATE = {
    "name": "create_return_request",
    "args": {"order_ref": "SIP-1", "amount": "115.00"},
}


# --- Tool calls ---------------------------------------------------------------


def test_expected_calls_made_in_order_all_match():
    actual = [
        ("check_return_eligibility", {"order_ref": "SIP-1", "reason": "damaged"}),
        (
            "create_return_request",
            {"order_ref": "SIP-1", "reason": "damaged", "amount": "115.00"},
        ),
    ]

    assert tool_call_accuracy([CHECK, CREATE], actual) == (2, 2, 0)


def test_extra_calls_are_counted_but_do_not_lower_the_match():
    actual = [
        ("list_customer_orders", {"limit": 5}),
        ("check_return_eligibility", {"order_ref": "SIP-1", "reason": "damaged"}),
        ("search_policies", {"query": "iade"}),
    ]

    assert tool_call_accuracy([CHECK], actual) == (1, 1, 2)


def test_wrong_order_does_not_match():
    actual = [
        ("create_return_request", {"order_ref": "SIP-1", "amount": "115.00"}),
        ("check_return_eligibility", {"order_ref": "SIP-1", "reason": "damaged"}),
    ]

    assert tool_call_accuracy([CHECK, CREATE], actual) == (1, 2, 1)


def test_wrong_argument_does_not_match():
    actual = [
        ("check_return_eligibility", {"order_ref": "SIP-1", "reason": "wrong_item"})
    ]

    assert tool_call_accuracy([CHECK], actual) == (0, 1, 1)


def test_missing_call_does_not_match():
    assert tool_call_accuracy([CHECK, CREATE], []) == (0, 2, 0)


def test_no_expected_calls():
    assert tool_call_accuracy([], [("list_metrics", {})]) == (0, 0, 1)


def test_one_actual_call_cannot_match_two_expected_ones():
    actual = [("check_return_eligibility", {"order_ref": "SIP-1", "reason": "damaged"})]

    assert tool_call_accuracy([CHECK, CHECK], actual) == (1, 2, 0)


@pytest.mark.parametrize(
    ("expected", "actual", "result"),
    [
        ({"amount": "100.00"}, {"amount": 100}, True),
        ({"amount": "100.00"}, {"amount": "100"}, True),
        ({"amount": "100.00"}, {"amount": "100.01"}, False),
        ({"order_ref": "SIP-1"}, {"order_ref": "sip-1"}, True),
        ({"order_ref": "SIP-1"}, {"order_ref": "SIP-2"}, False),
        ({"reason": "late"}, {}, False),
        ({}, {"limit": 5}, True),
        ({"group_by": ["customer_state"]}, {"group_by": ["customer_state"]}, True),
        ({"top": 5}, {"top": None}, False),
    ],
)
def test_argument_comparison(expected, actual, result):
    assert arguments_match(expected, actual) is result


# --- Decision -----------------------------------------------------------------


def test_decision_is_the_rule_engines_last_decision():
    results = [
        ("list_customer_orders", {"orders": []}),
        ("check_return_eligibility", {"decision": "ELIGIBLE", "rule": "R6"}),
        ("create_return_request", {"error": "APPROVAL_REQUIRED"}),
    ]

    # The rule engine's decision, not the approval notice that came after it.
    assert decision_of(results) == "ELIGIBLE"
    assert decision_of(results[2:]) == "APPROVAL_REQUIRED"


def test_not_found_is_a_decision_too():
    assert decision_of([("get_order_status", {"error": "NOT_FOUND"})]) == "NOT_FOUND"


def test_no_decision_without_a_deciding_tool():
    assert decision_of([]) is None
    assert decision_of([("search_policies", {"results": []}), ("echo", "text")]) is None


# --- Execution match ------------------------------------------------------------


def test_same_values_match_whatever_the_columns_are_called():
    assert execution_match([[0.0358]], [[0.0358]])


def test_numbers_are_rounded_to_four_places():
    assert execution_match([[0.03580657]], [[0.0358]])
    assert execution_match([[0.03580657]], [[0.03584]])
    assert not execution_match([[0.03580657]], [[0.0359]])


def test_integer_and_float_of_the_same_value_match():
    assert execution_match([["SP", 29]], [["SP", 29.0]])


def test_row_order_is_ignored_without_an_order_by():
    golden = [["SP", 10], ["RJ", 5]]

    assert execution_match(golden, [["RJ", 5], ["SP", 10]])
    assert not execution_match(golden, [["RJ", 5], ["SP", 10]], ordered=True)
    assert execution_match(golden, [["SP", 10], ["RJ", 5]], ordered=True)


def test_produced_table_may_carry_more_columns():
    golden = [["audio", 0.1178], ["baby", 0.0805]]
    produced = [["audio", 41, 348, 0.11781609], ["baby", 226, 2809, 0.08045568]]

    assert execution_match(golden, produced, ordered=True)


def test_columns_may_come_in_another_order():
    assert execution_match([[10, "SP"]], [["SP", 10]])


def test_a_missing_golden_column_does_not_match():
    assert not execution_match([["SP", 10, 0.5]], [["SP", 10]])


def test_different_values_or_row_counts_do_not_match():
    assert not execution_match([["SP", 10]], [["SP", 11]])
    assert not execution_match([["SP", 10]], [["SP", 10], ["RJ", 5]])
    assert not execution_match([["SP", 10]], [])


def test_two_empty_tables_match():
    assert execution_match([], [])


def test_null_values_compare():
    assert execution_match([[None, 3]], [[3, None]])
    assert not execution_match([[None, 3]], [[0, 3]])


def test_last_table_is_the_last_result_with_rows():
    results = [
        ("list_metrics", {"metrics": []}),
        ("run_sql", {"error": "SQL_ERROR"}),
        ("run_metric", {"rows": [[1]]}),
        ("run_sql", {"rows": [[2]]}),
        ("run_sql", {"error": "SQL_ERROR"}),
    ]

    assert last_table(results) == [[2]]
    assert last_table(results[:2]) is None


# --- The answer text --------------------------------------------------------------


def test_every_required_item_must_be_there():
    text = "SIP-1 için 115,00 BRL iade edilir (İade Politikası, Bölüm 2)."

    assert contains_all(
        text, ["sip-1", ["115.00", "115,00"], "İade Politikası, Bölüm 2"]
    )
    assert not contains_all(text, ["SIP-1", ["100.00", "100,00"]])
    assert contains_all(text, [])


def test_forbidden_patterns():
    assert matches_none("Politikada belirlenmemiştir.", [r"\d+\s*(iş\s*)?gün"])
    assert not matches_none("3-5 iş günü içinde geçer.", [r"\d+\s*(iş\s*)?gün"])
    assert not matches_none("10 GÜN sürer.", [r"\d+\s*(iş\s*)?gün"])


# --- Summary numbers ----------------------------------------------------------------


def test_rate():
    assert rate([True, True, False, True]) == 0.75
    assert rate([]) is None


def test_percentiles_by_nearest_rank():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]

    assert percentile(values, 50) == 5.0
    assert percentile(values, 95) == 10.0
    assert percentile([4.2], 95) == 4.2
    assert percentile([], 50) is None


# --- Grounding ----------------------------------------------------------------

SEARCH = (
    "search_policies",
    {
        "query": "iade süresi",
        "results": [
            {"citation": "İade Politikası, Bölüm 2", "text": "14 takvim günü"},
            {"citation": "Kargo ve Gecikme Politikası, Bölüm 3", "text": "10 gün"},
        ],
    },
)


def test_citations_are_read_in_both_languages():
    text = (
        "Süre 14 gündür (İade Politikası, Bölüm 2). See Shipping and Delays "
        "Policy, Section 3."
    )

    assert citations(text) == {
        ("İade Politikası", 2),
        ("Kargo ve Gecikme Politikası", 3),
    }


def test_a_cited_section_must_have_come_back_from_the_search():
    assert citations_returned("Bkz. İade Politikası, Bölüm 2.", [SEARCH])
    assert not citations_returned("Bkz. İade Politikası, Bölüm 9.", [SEARCH])
    assert not citations_returned("Bkz. İade Politikası, Bölüm 2.", [])
    assert citations_returned("Politikada bu konu belirlenmemiştir.", [])


def test_numbers_from_the_tool_pass_however_they_are_written():
    table = ("run_metric", {"rows": [[13591643.7, 0.0812, 54011]]})

    for text in (
        "GMV 13.591.643,70 BRL.",
        "GMV yaklaşık 13,6 milyon BRL.",
        "Geç teslim oranı %8,1.",
        "Oran 0,08.",
        "54.011 sipariş.",
        "54,011 orders.",
    ):
        assert ungrounded_numbers(text, [table]) == [], text


def test_a_number_no_tool_returned_is_found():
    table = ("run_metric", {"rows": [[54011]]})

    assert ungrounded_numbers("Yaklaşık 60.000 sipariş var.", [table]) == ["60.000"]
    assert ungrounded_numbers("Tahminim 99441.", []) == ["99441"]


def test_dates_citations_list_numbers_and_the_questions_numbers_are_left_out():
    text = (
        "1. 2018-08-01 ile 01.09.2018 arasında (İade Politikası, Bölüm 2).\n"
        "2. Sorduğunuz %50 artış verilerde görünmüyor."
    )

    assert ungrounded_numbers(text, [], question="GMV %50 arttı mı?") == []


def test_a_date_after_today_is_found_unless_the_question_names_it():
    today = date(2018, 9, 1)

    assert future_dates("Veriler 2018-09-01'e kadar.", today) == []
    assert future_dates("2019'da GMV 20 milyon olacak.", today) == ["2019"]
    assert future_dates("Teslim 15.10.2018.", today) == ["15.10.2018"]
    assert future_dates("2019 için veri yok.", today, question="2019 GMV?") == []
