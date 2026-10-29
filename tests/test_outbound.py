"""Tests for cleaning text before it goes to the model provider."""

import logging
from collections import Counter

import pytest

from src.guardrails.outbound import Redactor, log_findings
from src.guardrails.pii import looks_like_phone
from src.tools.session import Session

RAW_ID = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"
OTHER_ID = "ffeeddccbbaa99887766554433221100"


def clean(text, **kwargs):
    return Redactor(**kwargs).redact(text)


# --- Raw ids ------------------------------------------------------------


def test_raw_id_is_masked_without_a_session():
    text, found = clean(f"Order {RAW_ID} is late.")

    assert text == "Order [id] is late."
    assert found == {"id": 1}


def test_raw_id_becomes_the_session_alias():
    session = Session("u_alice")

    text, found = clean(
        f"{RAW_ID} numaralı siparişim nerede?", alias_for=session.alias_for
    )

    assert text == "SIP-1 numaralı siparişim nerede?"
    assert found == {"id": 1}
    # The tools can turn the alias back into the id.
    assert session.order_id_for("SIP-1") == RAW_ID


def test_same_id_same_alias():
    session = Session("u_alice")

    text, _ = clean(
        f"{RAW_ID}, {OTHER_ID}, {RAW_ID.upper()}", alias_for=session.alias_for
    )

    assert text == "SIP-1, SIP-2, SIP-1"


def test_id_inside_json_is_replaced():
    text, _ = clean(f'{{"order_id": "{RAW_ID}", "status": "delivered"}}')

    assert text == '{"order_id": "[id]", "status": "delivered"}'


@pytest.mark.parametrize(
    "harmless",
    [
        "SIP-1 siparişiniz teslim edildi.",
        "0a1b2c3d",  # too short
        RAW_ID + "0",  # too long: 33 characters
        "g" * 32,  # not hexadecimal
    ],
)
def test_non_id_text_is_left_alone(harmless):
    assert clean(harmless) == (harmless, Counter())


# --- E-mail and phone ---------------------------------------------------


@pytest.mark.parametrize(
    "address", ["ayse@example.com", "a.b+tag@mail.example.com.tr", "X_1@EXAMPLE.ORG"]
)
def test_email_is_masked(address):
    text, found = clean(f"Bana {address} adresinden ulaşın.")

    assert text == "Bana [email] adresinden ulaşın."
    assert found == {"email": 1}


@pytest.mark.parametrize(
    "number",
    [
        "+90 532 123 45 67",
        "0532 123 45 67",
        "05321234567",
        "0 (532) 123-45-67",
        "(11) 91234-5678",
        "+55 11 91234 5678",
        "532 123 45 67",
    ],
)
def test_phone_number_is_masked(number):
    text, found = clean(f"Telefonum {number}, arayın.")

    assert text == "Telefonum [phone], arayın."
    assert found == {"phone": 1}


@pytest.mark.parametrize(
    "not_a_phone",
    [
        "2018-08-25 15:30:00",
        "2018-07-01 2018-07-31",
        "13494255.74",
        "99421 sipariş, 96090 müşteri",
        "1209087049",  # a long count with no phone-like start or grouping
        "500.01 BRL",
        "12 34 56",
        "SIP-12",
        "LIMIT 1000",
        "0.0672 (6481 / 96417)",
    ],
)
def test_dates_amounts_are_not_phones(not_a_phone):
    assert clean(not_a_phone) == (not_a_phone, Counter())


def test_phone_rule_itself():
    assert looks_like_phone("+90 532 123 45 67")
    assert not looks_like_phone("2018-08-25 15")
    assert not looks_like_phone("123 456")
    assert not looks_like_phone("1234567890123456")


# --- Values known to be personal in this session ------------------------


def test_known_city_and_zip_code_are_masked():
    known = {"sao paulo": "[city]", "01310": "[zip]"}

    text, found = clean(
        "Sao Paulo'da oturuyorum, posta kodum 01310.", known_values=known
    )

    assert text == "[city]'da oturuyorum, posta kodum [zip]."
    assert found == {"city": 1, "zip": 1}


def test_known_value_matches_whole_word():
    known = {"sao paulo": "[city]", "01310": "[zip]", "sp": "[state]"}

    text, _ = clean("sao paulos, 013100, 201310, spor", known_values=known)

    assert text == "sao paulos, 013100, 201310, spor"


def test_longer_known_value_wins():
    known = {"rio": "[city]", "rio de janeiro": "[city]"}

    text, found = clean("Rio de Janeiro ve Rio", known_values=known)

    assert text == "[city] ve [city]"
    assert found == {"city": 2}


def test_empty_known_value_is_ignored():
    assert clean("metin", known_values={"": "[city]"}) == ("metin", Counter())


# --- Everything together ------------------------------------------------


def test_several_kinds_in_one_text():
    session = Session("u_alice")

    text, found = clean(
        f"{RAW_ID} için ayse@example.com ya da 0532 123 45 67, Campinas.",
        alias_for=session.alias_for,
        known_values={"campinas": "[city]"},
    )

    assert text == "SIP-1 için [email] ya da [phone], [city]."
    assert found == {"id": 1, "email": 1, "phone": 1, "city": 1}


def test_clean_text_is_returned_unchanged():
    text = (
        "İade süresi teslimden itibaren 14 takvim günüdür (İade Politikası, Bölüm 2)."
    )

    assert clean(text) == (text, Counter())


def test_nested_values_are_cleaned():
    found = Counter()
    value = {"order": RAW_ID, "items": [{"note": "ayse@example.com"}], "count": 3}

    cleaned = Redactor().redact_value(value, found)

    assert cleaned == {"order": "[id]", "items": [{"note": "[email]"}], "count": 3}
    assert found == {"id": 1, "email": 1}


# --- Logging ------------------------------------------------------------


def test_findings_logged_as_kinds_counts(caplog):
    _, found = clean(f"{RAW_ID} ayse@example.com")

    with caplog.at_level(logging.WARNING, logger="src.guardrails.outbound"):
        log_findings(found)

    assert len(caplog.records) == 1
    line = caplog.records[0].getMessage()
    assert "email=1" in line
    assert "id=1" in line
    assert RAW_ID not in line
    assert "ayse" not in line


def test_nothing_found_logs_nothing(caplog):
    with caplog.at_level(logging.WARNING, logger="src.guardrails.outbound"):
        log_findings(Counter())

    assert caplog.records == []


# --- Normalising before matching -------------------------------------------------


def test_unicode_tricks_hide_nothing():
    text = "Numaram ０５３２\u200b１２３４５６７, e-postam ayse\u200b@ornek.com"

    cleaned, found = Redactor().redact(text)

    assert cleaned == "Numaram [phone], e-postam [email]"
    assert found == Counter(phone=1, email=1)


def test_turkish_letters_stay_as_they_are():
    text = "Şikâyetim: ürün ığdırlı satıcıdan geldi, çok üzgünüm."

    assert Redactor().redact(text)[0] == text


def test_known_value_found_with_accents():
    redactor = Redactor(known_values={"sao paulo": "[city]"})

    cleaned, found = redactor.redact("São Paulo'dan, yani SAO PAULO'dan geliyor.")

    assert cleaned == "[city]'dan, yani [city]'dan geliyor."
    assert found == Counter(city=2)


def test_other_accents_are_kept():
    redactor = Redactor(known_values={"sao paulo": "[city]"})

    assert redactor.redact("Müşteri São Paulo'da.")[0] == "Müşteri [city]'da."


def test_tckn_iban_card_numbers_masked():
    text = (
        "TCKN 10000000146, IBAN TR33 0006 1005 1978 6457 8413 26, "
        "kart 4111 1111 1111 1111."
    )

    cleaned, found = Redactor().redact(text)

    assert cleaned == "TCKN [tckn], IBAN [iban], kart [card]."
    assert found == Counter(tckn=1, iban=1, card=1)


@pytest.mark.parametrize(
    "text",
    [
        "Toplam 12345678901 kuruş değil, 99441 sipariş var.",
        "GMV 13591643,70 BRL; 2018-07-01 2018-07-31 arası.",
        "Sipariş anahtarı 4111111111111112 değil.",
        # A rate as an ops result gives it: its decimals pass the Luhn check.
        '"rows": [[97, 2709, 0.03580657069029162]]',
        "Oran 0,03580657069029162 ya da 1.4111111111111111",
    ],
)
def test_failed_checksums_are_left_alone(text):
    assert Redactor().redact(text)[0] == text


@pytest.mark.parametrize(
    "address",
    [
        "ayse@ornek.com",
        "ayse [at] ornek.com",
        "ayse(at)ornek.com.tr",
        "ayse @ ornek.com",
    ],
)
def test_obfuscated_email_is_masked(address):
    assert (
        Redactor().redact(f"Adresim {address}, yazın.")[0] == "Adresim [email], yazın."
    )


@pytest.mark.parametrize(
    "text",
    ["Fiyat @ 100.50 BRL", "Teslim at home dot com sayfasında yazıyor", "@ işareti"],
)
def test_address_lookalike_is_left_alone(text):
    assert Redactor().redact(text)[0] == text


# --- What a review can hold ------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kind", "masked"),
    [
        ("Meu CPF é 529.982.247-25, por favor.", "cpf", "[cpf]"),
        ("CPF 52998224725 no cadastro", "cpf", "[cpf]"),
        ("A empresa 11.222.333/0001-81 não entregou", "cnpj", "[cnpj]"),
        (
            "Veja em https://loja.example.com/produto?id=3 e www.exemplo.com.br",
            "url",
            "[url]",
        ),
    ],
)
def test_cpf_cnpj_and_urls_are_masked(text, kind, masked):
    cleaned, found = Redactor().redact(text)

    assert masked in cleaned
    assert found[kind] >= 1


@pytest.mark.parametrize(
    "text",
    [
        "Chegou em 12 dias, nota 10, 529982247 unidades.",
        "Paguei 52998224726 centavos",
        "Pedido atrasou 3.5 dias; custou 1.234.567,89 reais",
        "Cód. 11.222.333/0001-82 inválido",
        "Mande para a loja física, www sem ponto.",
    ],
)
def test_lookalikes_are_left_alone(text):
    cleaned, found = Redactor().redact(text)

    assert not found
    assert cleaned == text


def test_url_punctuation_stays_outside():
    cleaned, _ = Redactor().redact(
        "Veja (www.exemplo.com.br), ou https://loja.example.com/p?id=3."
    )

    assert cleaned == "Veja ([url]), ou [url]."
