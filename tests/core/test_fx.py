"""Offline checks for src/fx.py (no render)."""
from manim import Text

from src.fx import build_loop_card, build_progress, count_up, split_number


def test_split_number_formats():
    assert split_number("$29T") == ("$", 29.0, 0, "T", False)
    assert split_number("-27%") == ("-", 27.0, 0, "%", False)
    assert split_number("3.2x") == ("", 3.2, 1, "x", False)
    assert split_number("$4,705/oz") == ("$", 4705.0, 0, "/oz", True)
    assert split_number("Losses") is None


def test_count_up_lands_exactly_on_final_text():
    seen = []

    def make(s):
        seen.append(s)
        return Text(s)

    mob = Text("?")
    anim = count_up(mob, "+125%", make, run_time=0.5)
    anim.begin()
    for a in (0.0, 0.3, 0.7, 1.0):
        anim.interpolate(a)
    assert seen[0] == "+0%"
    assert seen[-1] == "+125%"


def test_progress_and_loop_card_build():
    pips = build_progress(4, 7.8, 8.1, "#FFC74A")
    assert len(pips) == 4
    card = build_loop_card({"OUTRO_Q": "Gold ya Bitcoin?"}, "", 0.4, font="Montserrat", gold="#FFC74A")
    assert len(card) == 2
