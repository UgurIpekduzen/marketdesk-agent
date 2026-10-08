"""Tests for id hashing and masking."""

import hashlib

from src.guardrails.pii import hash_id, mask_raw_ids

RAW_ID = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"


def test_hash_is_the_first_ten_characters_of_sha256():
    assert hash_id(RAW_ID) == hashlib.sha256(RAW_ID.encode()).hexdigest()[:10]
    assert len(hash_id(RAW_ID)) == 10


def test_same_id_gives_the_same_hash_and_another_id_another():
    assert hash_id(RAW_ID) == hash_id(RAW_ID)
    assert hash_id(RAW_ID) != hash_id(RAW_ID[::-1])


def test_raw_ids_in_a_text_are_masked():
    text = f"Order {RAW_ID} and {RAW_ID.upper()}, twice."

    assert mask_raw_ids(text) == "Order [id] and [id], twice."


def test_text_without_ids_is_left_alone():
    text = "SIP-1 arrived damaged on 2018-08-25; refund 115.00 BRL."

    assert mask_raw_ids(text) == text
