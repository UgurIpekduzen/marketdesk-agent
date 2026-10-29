"""Checks that the policy documents stay in step with the rules.

The documents are prose, so these tests cannot prove them right. They catch
the usual ways of drifting apart: a rule nobody wrote about, a section that
cannot be cited, and a number that no longer matches the settings.
"""

import re
from pathlib import Path

import pytest

import config
from src.rules.returns import check_return
from tests.synthetic_data import ALICE

POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"
DOCUMENTS = (
    "returns.md",
    "shipping_and_delays.md",
    "cancellation.md",
    "payments_and_refunds.md",
    "damaged_or_wrong_item.md",
)
ALL_RULES = {f"R{number}" for number in range(14)}

SECTION_HEADING = re.compile(r"^## (\d+)\. \S", re.MULTILINE)
RULE_LINE = re.compile(r"^Kural: (.+)$", re.MULTILINE)


def read(name):
    return (POLICIES_DIR / name).read_text(encoding="utf-8")


def rules_in(text):
    return {rule for line in RULE_LINE.findall(text) for rule in line.split(", ")}


def test_folder_holds_the_five_documents():
    assert sorted(path.name for path in POLICIES_DIR.glob("*.md")) == sorted(DOCUMENTS)


@pytest.mark.parametrize("name", DOCUMENTS)
def test_document_has_title_and_numbering(name):
    text = read(name)
    numbers = [int(number) for number in SECTION_HEADING.findall(text)]

    assert text.startswith("# ")
    assert len(re.findall(r"^# ", text, re.MULTILINE)) == 1
    assert len(numbers) >= 4
    assert numbers == list(range(1, len(numbers) + 1))


@pytest.mark.parametrize("name", DOCUMENTS)
def test_document_names_only_known_rules(name):
    rules = rules_in(read(name))

    assert rules
    assert rules <= ALL_RULES


def test_every_rule_has_a_document():
    covered = set().union(*(rules_in(read(name)) for name in DOCUMENTS))

    assert covered == ALL_RULES


@pytest.mark.parametrize("name", DOCUMENTS)
def test_sections_name_their_rules(name):
    sections = read(name).split("\n## ")[1:]

    assert all(RULE_LINE.search(section) for section in sections[:-1])
    assert RULE_LINE.search(sections[-1]) is None


@pytest.mark.parametrize("name", DOCUMENTS)
def test_document_states_what_it_omits(name):
    last_section = read(name).split("\n## ")[-1]

    assert "belirlenmemiştir" in last_section
    assert "müşteri temsilcisine aktarılır" in last_section


@pytest.mark.parametrize(
    ("name", "phrase"),
    [
        ("returns.md", f"{config.RETURN_WINDOW_SHORT_DAYS} takvim günü"),
        ("returns.md", f"{config.RETURN_WINDOW_SHORT_DAYS + 1}. günden itibaren"),
        ("returns.md", f"{config.APPROVAL_THRESHOLD_BRL} BRL'den fazlaysa"),
        ("returns.md", f"{config.FREIGHT_REFUND_DELAY_DAYS} gün ya da daha fazla"),
        ("damaged_or_wrong_item.md", f"{config.RETURN_WINDOW_LONG_DAYS} takvim günü"),
        (
            "damaged_or_wrong_item.md",
            f"{config.RETURN_WINDOW_LONG_DAYS + 1}. günden itibaren",
        ),
        (
            "damaged_or_wrong_item.md",
            f"{config.APPROVAL_THRESHOLD_BRL} BRL'den fazlaysa",
        ),
        (
            "shipping_and_delays.md",
            f"{config.FREIGHT_REFUND_DELAY_DAYS} gün ya da daha fazla",
        ),
        (
            "shipping_and_delays.md",
            f"{config.FREIGHT_REFUND_DELAY_DAYS - 1} gün ya da daha az",
        ),
        ("shipping_and_delays.md", f"{config.RETURN_WINDOW_LONG_DAYS} takvim günü"),
        ("shipping_and_delays.md", f"{config.RETURN_WINDOW_SHORT_DAYS} gün"),
        (
            "payments_and_refunds.md",
            f"{config.APPROVAL_THRESHOLD_BRL} BRL'den fazlaysa",
        ),
        (
            "payments_and_refunds.md",
            f"{config.FREIGHT_REFUND_DELAY_DAYS} gün ya da daha fazla",
        ),
        ("payments_and_refunds.md", f"en fazla {config.RETURN_WINDOW_LONG_DAYS} gün"),
    ],
)
def test_numbers_match_the_settings(name, phrase):
    assert phrase in read(name)


def test_voucher_example_matches_the_rules(synthetic_db):
    # The payments document works through the o_voucher order of the tests.
    decision = check_return(synthetic_db, "o_voucher", ALICE, "changed_mind")
    text = read("payments_and_refunds.md")

    assert f"İade tutarı {decision.refund_amount:.0f} BRL" in text
    assert f"{decision.voucher_refund:.0f} BRL hediye çeki olarak" in text
    assert f"{decision.original_method_refund:.0f} BRL asıl ödeme yöntemine" in text
