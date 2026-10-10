"""Tests for id hashing and masking."""

import hashlib
import hmac

from src.guardrails import pii
from src.guardrails.pii import HASH_KEY_VARIABLE, hash_id, mask_raw_ids

RAW_ID = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"


def test_hash_is_the_first_ten_characters_of_a_keyed_hash(monkeypatch):
    monkeypatch.setenv(HASH_KEY_VARIABLE, "a-secret-key")

    expected = hmac.new(b"a-secret-key", RAW_ID.encode(), hashlib.sha256)

    assert hash_id(RAW_ID) == expected.hexdigest()[:10]
    assert len(hash_id(RAW_ID)) == 10


def test_hash_is_not_the_plain_hash_anyone_could_compute(monkeypatch):
    monkeypatch.setenv(HASH_KEY_VARIABLE, "a-secret-key")

    assert hash_id(RAW_ID) != hashlib.sha256(RAW_ID.encode()).hexdigest()[:10]


def test_same_id_gives_the_same_hash_and_another_id_another():
    assert hash_id(RAW_ID) == hash_id(RAW_ID)
    assert hash_id(RAW_ID) != hash_id(RAW_ID[::-1])


def test_another_key_gives_another_hash(monkeypatch):
    monkeypatch.setenv(HASH_KEY_VARIABLE, "first-key")
    first = hash_id(RAW_ID)
    monkeypatch.setenv(HASH_KEY_VARIABLE, "second-key")

    assert hash_id(RAW_ID) != first


def test_without_a_key_one_is_made_for_the_process_and_a_warning_logged(
    monkeypatch, caplog
):
    monkeypatch.delenv(HASH_KEY_VARIABLE, raising=False)
    monkeypatch.setattr(pii, "_generated_key", None)

    with caplog.at_level("WARNING"):
        first, second = hash_id(RAW_ID), hash_id(RAW_ID)

    assert first == second
    assert len(pii.hash_key()) == 64
    # Said once, and without the key itself.
    assert [HASH_KEY_VARIABLE in record.message for record in caplog.records] == [True]
    assert pii.hash_key() not in caplog.text


def test_raw_ids_in_a_text_are_masked():
    text = f"Order {RAW_ID} and {RAW_ID.upper()}, twice."

    assert mask_raw_ids(text) == "Order [id] and [id], twice."


def test_text_without_ids_is_left_alone():
    text = "SIP-1 arrived damaged on 2018-08-25; refund 115.00 BRL."

    assert mask_raw_ids(text) == text
