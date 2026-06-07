"""Tests for the Hinglish number normalizer."""
import pytest
from src.agents.phase2_scripting.num_normalizer import hinglish_number, build_number_reference
from src.agents.core.models import TemplateDataset


# ---------------------------------------------------------------------------
# hinglish_number — basic integers
# ---------------------------------------------------------------------------

def test_zero():
    assert hinglish_number(0) == "zero"

def test_single_digits():
    assert hinglish_number(1) == "ek"
    assert hinglish_number(9) == "nau"

def test_teens():
    assert hinglish_number(11) == "gyarah"
    assert hinglish_number(16) == "solah"
    assert hinglish_number(19) == "unnis"

def test_twenties_to_99():
    assert hinglish_number(20) == "bees"
    assert hinglish_number(25) == "pachees"
    assert hinglish_number(40) == "chaalees"
    assert hinglish_number(50) == "pachaas"
    assert hinglish_number(99) == "ninaanbe"

def test_hundreds():
    assert hinglish_number(100) == "sau"
    assert hinglish_number(200) == "do sau"
    assert hinglish_number(101) == "sau ek"
    assert hinglish_number(250) == "do sau pachaas"

def test_thousands():
    assert hinglish_number(1000) == "ek hajar"
    assert hinglish_number(2500) == "do hajar paanch sau"

def test_lakh():
    assert hinglish_number(100000) == "ek lakh"
    assert hinglish_number(250000) == "do lakh pachaas hajar"

def test_crore():
    assert hinglish_number(10000000) == "ek crore"


# ---------------------------------------------------------------------------
# hinglish_number — floats with decimals
# ---------------------------------------------------------------------------

def test_float_no_decimal():
    assert hinglish_number(16.0) == "solah"

def test_float_one_decimal():
    assert hinglish_number(14.3) == "chaudah point teen"
    assert hinglish_number(2.5) == "do point paanch"

def test_float_two_decimals():
    assert hinglish_number(2.57) == "do point paanch saat"
    assert hinglish_number(28.78) == "atthaais point saat aath"

def test_float_decimal_with_zero():
    assert hinglish_number(10.05) == "das point zero paanch"


# ---------------------------------------------------------------------------
# hinglish_number — unit suffix
# ---------------------------------------------------------------------------

def test_percent_unit():
    assert hinglish_number(16.0, "%") == "solah percent"
    assert hinglish_number(14.3, "% savings rate") == "chaudah point teen percent"
    assert hinglish_number(14.3, "% of disposable income") == "chaudah point teen percent"

def test_non_percent_unit_no_suffix():
    assert hinglish_number(100, "USD") == "sau"
    assert hinglish_number(5, "km") == "paanch"


# ---------------------------------------------------------------------------
# build_number_reference — bar_chart dataset
# ---------------------------------------------------------------------------

def test_build_reference_bar_chart():
    ds = TemplateDataset.model_validate({
        "template_name": "bar_chart",
        "meta": {"TITLE": "Top Savers", "SUB": "Savings rate", "METRIC": "Savings Rate", "UNIT": "% of disposable income"},
        "rows": [
            {"name": "Sweden", "value": 16.0},
            {"name": "Hungary", "value": 14.3},
        ]
    })
    ref = build_number_reference(ds)
    assert "solah percent" in ref
    assert "chaudah point teen percent" in ref
    assert "Sweden" in ref
    assert "Hungary" in ref
    assert "NUMBER REFERENCE" in ref


def test_build_reference_no_unit():
    ds = TemplateDataset.model_validate({
        "template_name": "bar_chart",
        "meta": {"TITLE": "Top Cities", "SUB": "Population"},
        "rows": [
            {"name": "Tokyo", "value": 37.4},
            {"name": "Delhi", "value": 32.9},
        ]
    })
    ref = build_number_reference(ds)
    assert "point" in ref       # decimals present
    assert "percent" not in ref  # no % unit


def test_build_reference_vs_card_empty():
    """vs_card has string values — no reference should be generated."""
    ds = TemplateDataset.model_validate({
        "template_name": "vs_card",
        "meta": {"TITLE": "iPhone vs S24", "SUB": "Comparison", "P1_NAME": "Apple", "P2_NAME": "Samsung"},
        "rows": [
            {"metric": "Speed", "p1_value": "200 mph", "p2_value": "180 mph", "winner": "p1"},
        ]
    })
    ref = build_number_reference(ds)
    assert ref == ""


def test_build_reference_sort_card_empty():
    """sort_card is qualitative — no reference."""
    ds = TemplateDataset.model_validate({
        "template_name": "sort_card",
        "meta": {"TITLE": "AI Tools", "SUB": "Ranked", "METRIC": "Usefulness"},
        "rows": [
            {"category": "S Tier", "reason": "Best overall"},
        ]
    })
    ref = build_number_reference(ds)
    assert ref == ""
