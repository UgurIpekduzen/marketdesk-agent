"""Tests for the session's order aliases."""

import pytest

from src.tools.session import Session, open_session
from tests.synthetic_data import ALICE


def test_aliases_are_numbered_in_the_order_they_are_handed_out():
    session = Session("u_alice")

    assert session.alias_for("o_second_seen_first") == "SIP-1"
    assert session.alias_for("o_other") == "SIP-2"


def test_an_order_keeps_its_alias():
    session = Session("u_alice")
    session.alias_for("o_one")
    session.alias_for("o_two")

    assert session.alias_for("o_one") == "SIP-1"


@pytest.mark.parametrize("written", ["SIP-2", "sip-2", " SIP 2 ", "sip2"])
def test_an_alias_is_read_however_it_is_written(written):
    session = Session("u_alice")
    session.alias_for("o_one")
    session.alias_for("o_two")

    assert session.order_id_for(written) == "o_two"


@pytest.mark.parametrize("unknown", ["SIP-0", "SIP-3", "SIP-999"])
def test_an_alias_that_was_never_handed_out_resolves_to_no_order(unknown):
    session = Session("u_alice")
    session.alias_for("o_one")
    session.alias_for("o_two")

    assert session.order_id_for(unknown) == unknown


def test_a_raw_order_id_is_passed_through_trimmed():
    assert Session("u_alice").order_id_for("  o_raw_id ") == "o_raw_id"


def test_aliases_of_one_session_mean_nothing_in_another():
    first, second = Session("u_alice"), Session("u_bob")
    first.alias_for("o_of_alice")

    assert second.order_id_for("SIP-1") == "SIP-1"


def test_order_ids_are_not_in_the_session_repr():
    session = Session("u_alice")
    session.alias_for("o_secret")

    assert "o_secret" not in repr(session)


def test_every_session_has_its_own_approvals():
    assert Session("u_alice").approvals is not Session("u_bob").approvals


def test_opened_session_knows_the_customers_city_and_zip_code(synthetic_db):
    session = open_session(synthetic_db, ALICE)

    assert session.customer_unique_id == ALICE
    assert session.personal_values == {"sao paulo": "[city]", "01310": "[zip]"}


def test_customer_with_orders_in_two_places_has_both(synthetic_db):
    synthetic_db.execute(
        "UPDATE customers SET customer_city = 'campinas', "
        "customer_zip_code_prefix = '13010' WHERE customer_id = 'c_o_day14'"
    )

    session = open_session(synthetic_db, ALICE)

    assert session.personal_values == {
        "sao paulo": "[city]",
        "01310": "[zip]",
        "campinas": "[city]",
        "13010": "[zip]",
    }


def test_unknown_customer_gets_a_session_without_personal_values(synthetic_db):
    assert open_session(synthetic_db, "u_nobody").personal_values == {}


def test_session_redactor_uses_the_aliases_and_the_personal_values(synthetic_db):
    session = open_session(synthetic_db, ALICE)
    raw_id = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"

    text, found = session.redactor().redact(f"{raw_id}, Sao Paulo 01310")

    assert text == "SIP-1, [city] [zip]"
    assert found == {"id": 1, "city": 1, "zip": 1}
    assert session.order_id_for("SIP-1") == raw_id


def test_personal_values_are_not_in_the_session_repr(synthetic_db):
    assert "sao paulo" not in repr(open_session(synthetic_db, ALICE))
