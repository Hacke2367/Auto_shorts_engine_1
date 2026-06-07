"""
AutoShorts Phase 2 — Hinglish Number Normalizer
================================================
Converts numeric dataset values to their Hinglish spoken form so the LLM
can copy exact forms rather than transliterating on its own (which risks
errors like "pandrah" for 14.3 or "das" for 10.5).

Public API
----------
  hinglish_number(value, unit="") -> str
      16.0, "%"    -> "solah percent"
      14.3, "%"    -> "chaudah point teen percent"
      2500000, ""  -> "do lakh pachaas hajar"
      0            -> "zero"

  build_number_reference(dataset) -> str
      Returns a formatted "=== NUMBER REFERENCE ===" block for the LLM
      user-prompt. Empty string if no numeric values are found.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.core.models import TemplateDataset

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

# Single digits — used for decimal-digit-by-digit pronunciation
_DIGITS_0_9 = [
    "zero", "ek", "do", "teen", "chaar", "paanch",
    "chhah", "saat", "aath", "nau",
]

# 1–19 (complete irregular forms)
_ONES = [
    "", "ek", "do", "teen", "chaar", "paanch", "chhah", "saat", "aath", "nau",
    "das", "gyarah", "baarah", "terah", "chaudah", "pandrah", "solah", "satrah",
    "athaarah", "unnis",
]

# 20–99 (all irregular Hindi compound forms)
_TWENTY_TO_99: dict[int, str] = {
    20: "bees",       21: "ikkees",     22: "baais",      23: "teis",
    24: "chaubees",   25: "pachees",    26: "chhabbees",  27: "sattaees",
    28: "atthaais",   29: "unntees",    30: "tees",       31: "ikattees",
    32: "battees",    33: "tentees",    34: "chauntees",  35: "paintees",
    36: "chhattees",  37: "saintees",   38: "artees",     39: "unntaalees",
    40: "chaalees",   41: "iktaalees",  42: "bayaalees",  43: "tentaalees",
    44: "chawaalees", 45: "paintaalees",46: "chhiyaalees",47: "saintaalees",
    48: "artaalees",  49: "unchaas",    50: "pachaas",    51: "ikyaavan",
    52: "baavan",     53: "tirepan",    54: "chauvan",    55: "pachhattan",
    56: "chhappan",   57: "sattavan",   58: "athavan",    59: "unsath",
    60: "saath",      61: "iksath",     62: "baasath",    63: "tirsath",
    64: "chausath",   65: "painsath",   66: "chhiyasath", 67: "sarsath",
    68: "arsath",     69: "unahattar",  70: "sattar",     71: "ikhattar",
    72: "bahattar",   73: "tihattar",   74: "chauhattar", 75: "pachhattar",
    76: "chhiyahattar",77: "sathattar", 78: "athattar",   79: "unaasi",
    80: "assi",       81: "ikyaasi",    82: "byaasi",     83: "tiraasi",
    84: "chauraasi",  85: "pachaasi",   86: "chhiyaasi",  87: "sattaasi",
    88: "atthaasi",   89: "nawaasi",    90: "nabbe",      91: "ikyaanbe",
    92: "baanbe",     93: "tiranbe",    94: "chauranbe",  95: "pachaanbe",
    96: "chhiyaanbe", 97: "sattaanbe",  98: "atthaanbe",  99: "ninaanbe",
}


# ---------------------------------------------------------------------------
# Core integer converter
# ---------------------------------------------------------------------------

def _int_spoken(n: int) -> str:
    """Non-negative integer → Hinglish spoken words."""
    if n == 0:
        return "zero"
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TWENTY_TO_99[n]
    if n < 1_000:
        h, r = divmod(n, 100)
        # 100 = "sau", 200 = "do sau", 300 = "teen sau" …
        base = "sau" if h == 1 else (_ONES[h] + " sau")
        return (base + " " + _int_spoken(r)).strip() if r else base
    if n < 1_00_000:
        t, r = divmod(n, 1_000)
        base = _int_spoken(t) + " hajar"
        return (base + " " + _int_spoken(r)).strip() if r else base
    if n < 1_00_00_000:
        l, r = divmod(n, 1_00_000)
        base = _int_spoken(l) + " lakh"
        return (base + " " + _int_spoken(r)).strip() if r else base
    c, r = divmod(n, 1_00_00_000)
    base = _int_spoken(c) + " crore"
    return (base + " " + _int_spoken(r)).strip() if r else base


# ---------------------------------------------------------------------------
# Public: hinglish_number
# ---------------------------------------------------------------------------

def hinglish_number(value: float, unit: str = "") -> str:
    """Convert a numeric dataset value to its Hinglish TTS-safe spoken form.

    Decimal part is spoken digit-by-digit after "point":
      14.3  → "chaudah point teen"
      2.57  → "do point paanch saat"

    Unit handling:
      "%" or anything containing "%" → append "percent"
      Other units are ignored (LLM adds context words naturally).
    """
    unit = (unit or "").strip()
    suffix = " percent" if "%" in unit else ""

    rounded = round(float(value), 10)
    if rounded == int(rounded):
        spoken = _int_spoken(int(rounded))
    else:
        int_part = int(rounded)
        dec_str = f"{rounded:.10f}".split(".")[1].rstrip("0")
        dec_words = " ".join(
            _DIGITS_0_9[int(d)] if int(d) < len(_DIGITS_0_9) else d
            for d in dec_str
        )
        spoken = f"{_int_spoken(int_part)} point {dec_words}"

    return (spoken + suffix).strip()


# ---------------------------------------------------------------------------
# Dataset reference block builder
# ---------------------------------------------------------------------------

# Fields that are labels / metadata — not values to convert
_SKIP_FIELDS = frozenset({
    # label / identity fields
    "name", "country", "category", "attribute", "metric", "year",
    # display/style metadata
    "image", "color", "group", "note", "notes", "emoji", "winner",
    # weighting/ordering — meaningful to the renderer, not to narration
    "order", "weight",
})

# Fields used as the human-readable row label
_LABEL_FIELDS = ("name", "country", "category", "attribute", "year")

# Max reference lines to avoid bloating the prompt
_MAX_REFERENCE_LINES = 24


def _row_label(row_dict: dict) -> str:
    for field in _LABEL_FIELDS:
        val = row_dict.get(field)
        if val and isinstance(val, str):
            return val
    return ""


def _row_numbers(row_dict: dict) -> list[tuple[str, float]]:
    """Extract (field_or_entity_name, float_value) pairs from a row dict."""
    results: list[tuple[str, float]] = []
    for field, val in row_dict.items():
        if field in _SKIP_FIELDS:
            continue
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)):
            results.append((field, float(val)))
        elif isinstance(val, dict):
            # scan_race: {"entities": {"YouTube": 2.5, "TikTok": 1.7}}
            for entity, ev in val.items():
                if isinstance(ev, (int, float)) and not isinstance(ev, bool):
                    results.append((entity, float(ev)))
    return results


def build_number_reference(dataset: "TemplateDataset") -> str:
    """Build a NUMBER REFERENCE block for the Phase 2 user prompt.

    The LLM is instructed to copy these spoken forms verbatim, eliminating
    transliteration guessing errors (e.g. "pandrah" instead of "chaudah point teen"
    for 14.3).

    Returns an empty string if the dataset has no convertible numeric values
    (e.g. vs_card which stores values as strings, or sort_card which is qualitative).
    """
    meta = getattr(dataset, "meta", None) or {}
    unit = meta.get("UNIT", "")

    lines: list[str] = []

    for row in dataset.rows:
        if len(lines) >= _MAX_REFERENCE_LINES:
            break

        row_dict = row.model_dump()
        label = _row_label(row_dict)
        nums = _row_numbers(row_dict)

        if not nums:
            continue

        if len(nums) == 1:
            _, val = nums[0]
            spoken = hinglish_number(val, unit)
            prefix = f"{label} " if label else ""
            lines.append(f"  {prefix}{val} → \"{spoken}\"")
        else:
            # Multiple values (butterfly_chart p1/p2, scan_race entities)
            parts = [
                f"{field} {val} → \"{hinglish_number(val, unit)}\""
                for field, val in nums
            ]
            row_label = f"{label}: " if label else ""
            entry = row_label + " | ".join(parts)
            lines.append(f"  {entry}")

    if not lines:
        return ""

    return (
        "=== NUMBER REFERENCE (copy spoken forms exactly — do not re-translate) ===\n"
        + "\n".join(lines)
        + "\n\n"
    )
