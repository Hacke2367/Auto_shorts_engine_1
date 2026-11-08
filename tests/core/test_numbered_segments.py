"""numbered_segments must match both segment spellings the renderer receives.

Fixtures and hand-made jobs name segments "item_1"; final_handoff emits "item1".
Templates resolve their per-item timeline keys through this helper, so if it
misses a spelling the visuals silently drift off the narration.
"""
from src.sync.timeline import Timeline, numbered_segments


def test_underscore_spelling():
    order = ["hook", "setup", "item_1", "item_2", "winner", "outro"]
    assert numbered_segments(order, "item") == ["item_1", "item_2"]


def test_handoff_spelling():
    order = ["hook", "setup", "slice1", "slice2", "slice3", "winner", "outro"]
    assert numbered_segments(order, "slice") == ["slice1", "slice2", "slice3"]


def test_keeps_play_order_and_ignores_other_bases():
    order = ["hook", "node2", "node1", "nodes", "item1", "node_10", "round_1", "outro"]
    assert numbered_segments(order, "node") == ["node2", "node1", "node_10"]


def test_base_is_case_insensitive_but_names_are_preserved():
    assert numbered_segments(["Card1", "card_2"], "CARD") == ["Card1", "card_2"]


def test_empty_or_missing_order():
    assert numbered_segments(None, "item") == []
    assert numbered_segments([], "item") == []


def test_resolved_names_hit_real_timeline_durations():
    # The regression: bar_chart looked up "item_1" in a job whose timeline says
    # "item1", got the 2.0s default, and the bars ran ahead of the voice.
    timeline = {"hook": 5.4, "setup": 4.9, "item1": 4.7, "item2": 5.7, "winner": 7.1, "outro": 4.6}
    order = list(timeline)
    tl = Timeline.from_dict(timeline, defaults={"item_1": 2.0, "item_2": 2.0})
    tl.schedule(order)

    segs = numbered_segments(order, "item")
    assert [tl.seg_total(s, 2.0) for s in segs] == [4.7, 5.7]
    assert tl.target_elapsed(segs[-1]) == 5.4 + 4.9 + 4.7 + 5.7
