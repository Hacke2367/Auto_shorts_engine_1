"""
tests/fixtures/test_job_fixtures.py
=====================================
Validates all job.json fixture files in tests/fixtures/.

Tests cover:
  - Schema completeness (required fields present)
  - Internal consistency (audio.order == audio.segments names, timeline keys match)
  - Timeline sanity (values positive, meet MND floor from timing_registry.yaml)
  - Segment naming conventions per template
  - No duplicate segment names

Run:
    python -m pytest tests/fixtures/test_job_fixtures.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
FIXTURES_DIR = Path(__file__).parent
PROJECT_ROOT = FIXTURES_DIR.parent.parent
TIMING_REGISTRY = PROJECT_ROOT / ".agent" / "context" / "template_timing_registry.yaml"

ALL_FIXTURES = sorted(FIXTURES_DIR.glob("*.json"))

# ---------------------------------------------------------------------------
# Timing registry (loaded once)
# ---------------------------------------------------------------------------
def _load_timing_registry() -> dict:
    if not TIMING_REGISTRY.exists():
        return {}
    with open(TIMING_REGISTRY, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

TIMING = _load_timing_registry()
DEFAULTS = TIMING.get("defaults", {})
BUFFER_SEC: float = float(DEFAULTS.get("buffer_sec", 0.6))

# ---------------------------------------------------------------------------
# Expected segment patterns per template
# ---------------------------------------------------------------------------
# Maps template_id → expected prefix for dynamic segments (or None for fixed)
DYNAMIC_SEGMENT_PREFIXES: dict[str, str | None] = {
    "bar_chart":       "item_",
    "butterfly_chart": "item",     # no underscore: item1, item2, ...
    "scan_race":       "middle_",
    "geo_universal":   "node_",
    "donut_breakdown": "slice_",
    "sort_card":       "card_",
    "vs_card":         "round_",
}

FIXED_SEGMENTS = {"hook", "setup", "winner", "outro", "finish"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def _segment_names(job: dict) -> list[str]:
    return [s["name"] for s in job["audio"]["segments"]]

def _get_base_mnd(template_id: str, seg_name: str) -> float:
    """Get MND for a segment name from the timing registry."""
    template_timings = TIMING.get(template_id, {})
    # Try exact match first (hook, setup, winner, outro, finish)
    if seg_name in template_timings:
        return float(template_timings[seg_name])
    # Strip trailing digits (item_1 → item_, item1 → item, node_5 → node_)
    # Try progressively shorter base names
    import re
    base = re.sub(r"_?\d+$", "", seg_name).upper()
    if base in template_timings:
        return float(template_timings[base])
    return 0.0


# ===========================================================================
# Parametrize all fixture files
# ===========================================================================
@pytest.mark.parametrize("fixture_path", ALL_FIXTURES, ids=[f.name for f in ALL_FIXTURES])
class TestJobFixtureSchema:

    def test_required_top_level_fields(self, fixture_path: Path):
        """job.json must have job_id, template_id, audio, timeline."""
        job = _load(fixture_path)
        for field in ("job_id", "template_id", "audio", "timeline"):
            assert field in job, f"Missing required field '{field}' in {fixture_path.name}"

    def test_job_id_is_nonempty_string(self, fixture_path: Path):
        job = _load(fixture_path)
        assert isinstance(job["job_id"], str) and job["job_id"].strip(), \
            f"job_id must be a non-empty string in {fixture_path.name}"

    def test_template_id_is_known(self, fixture_path: Path):
        job = _load(fixture_path)
        known = set(DYNAMIC_SEGMENT_PREFIXES.keys())
        assert job["template_id"] in known, \
            f"Unknown template_id '{job['template_id']}' in {fixture_path.name}. Known: {known}"

    def test_audio_has_segments_and_order(self, fixture_path: Path):
        job = _load(fixture_path)
        audio = job["audio"]
        assert "segments" in audio, f"audio.segments missing in {fixture_path.name}"
        assert "order" in audio, f"audio.order missing in {fixture_path.name}"
        assert len(audio["segments"]) > 0, f"audio.segments is empty in {fixture_path.name}"
        assert len(audio["order"]) > 0, f"audio.order is empty in {fixture_path.name}"

    def test_audio_order_matches_segments(self, fixture_path: Path):
        """audio.order and audio.segments must cover exactly the same names."""
        job = _load(fixture_path)
        names_in_segments = _segment_names(job)
        order = job["audio"]["order"]
        assert names_in_segments == order, (
            f"Mismatch in {fixture_path.name}:\n"
            f"  segments names: {names_in_segments}\n"
            f"  order:          {order}"
        )

    def test_no_duplicate_segment_names(self, fixture_path: Path):
        job = _load(fixture_path)
        names = _segment_names(job)
        dupes = [n for n in names if names.count(n) > 1]
        assert not dupes, f"Duplicate segment names in {fixture_path.name}: {set(dupes)}"

    def test_timeline_keys_match_order(self, fixture_path: Path):
        """timeline keys must be exactly the same set as audio.order."""
        job = _load(fixture_path)
        order_set = set(job["audio"]["order"])
        timeline_set = set(job["timeline"].keys())
        assert order_set == timeline_set, (
            f"Timeline/order mismatch in {fixture_path.name}:\n"
            f"  In order but not timeline: {order_set - timeline_set}\n"
            f"  In timeline but not order: {timeline_set - order_set}"
        )

    def test_timeline_values_are_positive_floats(self, fixture_path: Path):
        job = _load(fixture_path)
        for seg_name, duration in job["timeline"].items():
            assert isinstance(duration, (int, float)), \
                f"Timeline value for '{seg_name}' is not a number in {fixture_path.name}"
            assert duration > 0, \
                f"Timeline value for '{seg_name}' is <= 0 in {fixture_path.name}: {duration}"

    def test_timeline_values_meet_mnd_floor(self, fixture_path: Path):
        """Every segment duration must be >= MND + buffer_sec from timing_registry.yaml."""
        job = _load(fixture_path)
        template_id = job["template_id"]
        for seg_name, duration in job["timeline"].items():
            mnd = _get_base_mnd(template_id, seg_name)
            min_required = mnd + BUFFER_SEC
            assert float(duration) >= min_required, (
                f"[{fixture_path.name}] Segment '{seg_name}' duration {duration}s "
                f"< MND({mnd}s) + buffer({BUFFER_SEC}s) = {min_required}s"
            )

    def test_audio_paths_start_with_audio_prefix(self, fixture_path: Path):
        job = _load(fixture_path)
        for seg in job["audio"]["segments"]:
            assert seg["path"].startswith("audio/"), (
                f"Audio path for '{seg['name']}' should start with 'audio/' "
                f"in {fixture_path.name}: got '{seg['path']}'"
            )

    def test_audio_paths_end_with_mp3(self, fixture_path: Path):
        job = _load(fixture_path)
        for seg in job["audio"]["segments"]:
            assert seg["path"].endswith(".mp3"), (
                f"Audio path for '{seg['name']}' should end with '.mp3' "
                f"in {fixture_path.name}: got '{seg['path']}'"
            )

    def test_required_bookend_segments_present(self, fixture_path: Path):
        """hook, setup, outro must always be present."""
        job = _load(fixture_path)
        names = set(_segment_names(job))
        for required in ("hook", "setup", "outro"):
            assert required in names, \
                f"Required segment '{required}' missing in {fixture_path.name}"

    def test_hook_is_first_segment(self, fixture_path: Path):
        job = _load(fixture_path)
        assert job["audio"]["order"][0] == "hook", \
            f"'hook' must be first in audio.order in {fixture_path.name}"

    def test_outro_is_last_segment(self, fixture_path: Path):
        job = _load(fixture_path)
        assert job["audio"]["order"][-1] == "outro", \
            f"'outro' must be last in audio.order in {fixture_path.name}"

    def test_dynamic_segments_are_contiguous(self, fixture_path: Path):
        """Dynamic segments (item_1..item_N, round_1..round_N, etc.) must be
        contiguous and start from 1 with no gaps."""
        job = _load(fixture_path)
        template_id = job["template_id"]
        prefix = DYNAMIC_SEGMENT_PREFIXES.get(template_id)
        if not prefix:
            pytest.skip(f"No dynamic segments for template '{template_id}'")

        import re
        order = job["audio"]["order"]
        # Collect dynamic segment indices
        dynamic = []
        for name in order:
            m = re.match(rf"^{re.escape(prefix)}(\d+)$", name)
            if m:
                dynamic.append(int(m.group(1)))

        if not dynamic:
            pytest.skip(f"No dynamic segments found with prefix '{prefix}' in {fixture_path.name}")

        assert dynamic == list(range(1, len(dynamic) + 1)), (
            f"Dynamic segments for prefix '{prefix}' are not contiguous from 1 "
            f"in {fixture_path.name}: got indices {dynamic}"
        )

    def test_output_section_has_final_mp4(self, fixture_path: Path):
        job = _load(fixture_path)
        assert "output" in job, f"'output' section missing in {fixture_path.name}"
        assert "final_mp4" in job["output"], \
            f"'output.final_mp4' missing in {fixture_path.name}"

    def test_gains_section_structure(self, fixture_path: Path):
        job = _load(fixture_path)
        assert "gains" in job, f"'gains' section missing in {fixture_path.name}"
        for key in ("gain_voice", "gain_sfx", "gain_bgm_db"):
            assert key in job["gains"], \
                f"gains.{key} missing in {fixture_path.name}"


# ===========================================================================
# Template-specific structural tests
# ===========================================================================

@pytest.mark.parametrize("fixture_path", ALL_FIXTURES, ids=[f.name for f in ALL_FIXTURES])
class TestTemplateSpecificRules:

    def test_bar_chart_item_count_in_valid_range(self, fixture_path: Path):
        job = _load(fixture_path)
        if job["template_id"] != "bar_chart":
            pytest.skip("Not a bar_chart fixture")
        import re
        items = [n for n in job["audio"]["order"] if re.match(r"^item_\d+$", n)]
        assert 3 <= len(items) <= 10, \
            f"bar_chart expects 3–10 items, got {len(items)} in {fixture_path.name}"

    def test_vs_card_has_at_least_2_rounds(self, fixture_path: Path):
        job = _load(fixture_path)
        if job["template_id"] != "vs_card":
            pytest.skip("Not a vs_card fixture")
        rounds = [n for n in job["audio"]["order"] if n.startswith("round_")]
        assert len(rounds) >= 2, \
            f"vs_card expects at least 2 rounds, got {len(rounds)} in {fixture_path.name}"

    def test_sort_card_has_at_least_2_cards(self, fixture_path: Path):
        job = _load(fixture_path)
        if job["template_id"] != "sort_card":
            pytest.skip("Not a sort_card fixture")
        cards = [n for n in job["audio"]["order"] if n.startswith("card_")]
        assert len(cards) >= 2, \
            f"sort_card expects at least 2 cards, got {len(cards)} in {fixture_path.name}"

    def test_scan_race_has_finish_segment(self, fixture_path: Path):
        job = _load(fixture_path)
        if job["template_id"] != "scan_race":
            pytest.skip("Not a scan_race fixture")
        assert "finish" in job["audio"]["order"], \
            f"scan_race must have a 'finish' segment in {fixture_path.name}"

    def test_geo_universal_has_at_least_3_nodes(self, fixture_path: Path):
        job = _load(fixture_path)
        if job["template_id"] != "geo_universal":
            pytest.skip("Not a geo_universal fixture")
        nodes = [n for n in job["audio"]["order"] if n.startswith("node_")]
        assert len(nodes) >= 3, \
            f"geo_universal expects at least 3 nodes, got {len(nodes)} in {fixture_path.name}"

    def test_donut_breakdown_has_at_least_2_slices(self, fixture_path: Path):
        job = _load(fixture_path)
        if job["template_id"] != "donut_breakdown":
            pytest.skip("Not a donut_breakdown fixture")
        slices = [n for n in job["audio"]["order"] if n.startswith("slice_")]
        assert len(slices) >= 2, \
            f"donut_breakdown expects at least 2 slices, got {len(slices)} in {fixture_path.name}"

    def test_butterfly_chart_items_no_underscore(self, fixture_path: Path):
        """butterfly_chart uses item1/item2/... (no underscore) by convention."""
        job = _load(fixture_path)
        if job["template_id"] != "butterfly_chart":
            pytest.skip("Not a butterfly_chart fixture")
        import re
        items_with_underscore = [
            n for n in job["audio"]["order"]
            if re.match(r"^item_\d+$", n)
        ]
        assert not items_with_underscore, (
            f"butterfly_chart should use 'item1' (no underscore), "
            f"found underscore names in {fixture_path.name}: {items_with_underscore}"
        )


# ===========================================================================
# Standalone: verify fixture count covers all known templates
# ===========================================================================

def test_all_templates_have_at_least_one_fixture():
    """Every template in DYNAMIC_SEGMENT_PREFIXES must have at least one fixture."""
    fixture_templates = set()
    for path in ALL_FIXTURES:
        try:
            job = _load(path)
            fixture_templates.add(job.get("template_id", ""))
        except Exception:
            pass

    for template_id in DYNAMIC_SEGMENT_PREFIXES:
        assert template_id in fixture_templates, (
            f"No fixture found for template '{template_id}'. "
            f"Add a fixture to tests/fixtures/ for it."
        )


def test_fixture_count():
    """Sanity: at least 7 fixtures (one per template), at most 20."""
    count = len(ALL_FIXTURES)
    assert 7 <= count <= 20, f"Expected 7–20 fixtures, found {count}"
