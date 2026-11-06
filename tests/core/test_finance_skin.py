"""Finance skin regressions (offline, no render).

The templates wrap IntroManager.play_intro in try/except, so a HUD crash shows
up only as a video with no brand/source/border. These checks fail loudly instead.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils import IntroManager, fmt_value  # noqa: E402


def test_fmt_value_finance_formats():
    cases = [
        ((817, "B", "$"), "$817B"),
        ((1000, "B", "$"), "$1T"),        # magnitude unit folds in, no "$1KB"
        ((143.1, "B", "$"), "$143.1B"),
        ((2400000000, "", "$"), "$2.4B"),
        ((43.45, "%", ""), "43.5%"),
        ((-0.88, "", ""), "-0.88"),
        ((5595, "/oz", "$"), "$5.6K /oz"),
    ]
    for (v, unit, cur), want in cases:
        assert fmt_value(v, unit, cur) == want, (v, unit, cur)
    assert fmt_value(45000000, "", "₹", "indian") == "₹4.5 Cr"
    assert fmt_value(12345, "", "", "indian") == "12,345"
    assert fmt_value("n/a") == "n/a"


def test_hud_builds_and_shows_source():
    from manim import Scene

    scene = Scene()
    IntroManager.play_intro(scene, feed_text="FEED_BAR // MARKET", footer_text="CONFIDENTIAL // VERIFIED")
    assert getattr(scene, "_branding_attached", False), "HUD was not attached"
    overlay = scene._branding_objs["overlay"]
    IntroManager.set_source(scene, "World Bank")
    assert overlay.feed.width > 0.5, "source label missing"
    assert overlay.feed.get_center()[0] > 0, "source label must sit top-right"
