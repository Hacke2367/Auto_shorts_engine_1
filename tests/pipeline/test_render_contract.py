"""
Render-Contract Tests (offline, no API calls)
=============================================
Verifies that Phase-1 extraction output is RENDERER-COMPATIBLE end to end:

  1. Semantic validator    — wrong-shaped values are rejected (the gate).
  2. Extraction quality gate— wires the validator into _validate_dataset_quality.
  3. CSV writer headers     — canonical (renderer-facing) column names are emitted.
  4. resolve_job_csv        — renderer reads the JOB's csv, not a hardcoded file.
  5. Renderer-loader seam   — the templates actually parse the written CSV
                              (sort_card category -> int tier; vs_card winner -> 0/1/2,
                              including legacy 'p1'/'p2'/'tie' text).

Run:  python tests/pipeline/test_render_contract.py
(or:  python -m pytest tests/pipeline/test_render_contract.py -v)
"""
from __future__ import annotations

import csv
import logging
import os
import sys
import tempfile
from pathlib import Path

# Make repo root importable when run as a plain script.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.agents.core.models import (  # noqa: E402
    TemplateDataset,
    TEMPLATE_CSV_HEADERS,
    validate_template_semantics,
)
from src.agents.phase1_extraction.runner import _write_csv, _validate_dataset_quality  # noqa: E402
from src.sync.job import resolve_job_csv  # noqa: E402

_LOG = logging.getLogger("test_render_contract")


def _ds(template: str, rows: list[dict], meta: dict | None = None) -> TemplateDataset:
    return TemplateDataset.model_validate(
        {"template_name": template, "meta": meta or {}, "rows": rows}
    )


# ---------------------------------------------------------------------------
# 1. Semantic validator
# ---------------------------------------------------------------------------
def test_sortcard_category_must_be_1_or_2():
    good = _ds("sort_card", [
        {"image": "a.png", "category": "1", "reason": "fast"},
        {"image": "b.png", "category": "2", "reason": "slow"},
    ], meta={"TITLE": "Mainstream vs Emerging"})
    ok, reason = validate_template_semantics("sort_card", good.rows, good.meta)
    assert ok, f"valid 1/2 + 'A vs B' title should pass; got {reason!r}"

    bad = _ds("sort_card", [
        {"image": "a.png", "category": "Instant Settlement", "reason": "x"},
        {"image": "b.png", "category": "Digital Currency", "reason": "y"},
    ], meta={"TITLE": "Mainstream vs Emerging"})
    ok, reason = validate_template_semantics("sort_card", bad.rows, bad.meta)
    assert not ok and "category" in reason, f"text category must fail; got {reason!r}"


def test_sortcard_requires_both_tiers():
    one_sided = _ds("sort_card", [
        {"image": "a.png", "category": "1", "reason": "x"},
        {"image": "b.png", "category": "1", "reason": "y"},
    ], meta={"TITLE": "A vs B"})
    ok, reason = validate_template_semantics("sort_card", one_sided.rows, one_sided.meta)
    assert not ok and "BOTH" in reason, f"all-one-tier must fail; got {reason!r}"


def test_sortcard_title_must_name_two_groups():
    no_vs = _ds("sort_card", [
        {"image": "a.png", "category": "1", "reason": "x"},
        {"image": "b.png", "category": "2", "reason": "y"},
    ], meta={"TITLE": "Top 7 Payment Innovations"})
    ok, reason = validate_template_semantics("sort_card", no_vs.rows, no_vs.meta)
    assert not ok and "TITLE" in reason, f"single-line title must fail; got {reason!r}"


def test_vscard_winner_must_be_0_1_2():
    good = _ds("vs_card", [
        {"metric": "Speed", "p1_value": "200", "p2_value": "180", "winner": "1"},
        {"metric": "Range", "p1_value": "300", "p2_value": "400", "winner": "2"},
    ])
    ok, _ = validate_template_semantics("vs_card", good.rows)
    assert ok, "valid 0/1/2 winners should pass"

    bad = _ds("vs_card", [
        {"metric": "Speed", "p1_value": "200", "p2_value": "180", "winner": "p1"},
        {"metric": "Range", "p1_value": "300", "p2_value": "400", "winner": "tie"},
    ])
    ok, reason = validate_template_semantics("vs_card", bad.rows)
    assert not ok and "winner" in reason, f"text winner must fail; got {reason!r}"


def test_geo_max_10_rows_enforced_by_model():
    # Row-count capacity is enforced by the TemplateDataset model itself, so an
    # 11-row geo dataset must fail to even construct.
    rows = [{"country": f"C{i}", "group": "G", "value": float(i)} for i in range(11)]
    try:
        _ds("geo_universal", rows)
        raised = False
    except Exception:
        raised = True
    assert raised, "TemplateDataset should reject >10 geo_universal rows (capacity)"


# ---------------------------------------------------------------------------
# 2. Quality gate wiring
# ---------------------------------------------------------------------------
def test_quality_gate_rejects_wrong_shape():
    good = _ds("sort_card", [
        {"image": "a.png", "category": "1", "reason": "fast"},
        {"image": "b.png", "category": "2", "reason": "slow"},
    ], meta={"TITLE": "Mainstream vs Emerging"})
    ok, _ = _validate_dataset_quality(good, "sort_card", _LOG)
    assert ok, "schema-correct sort_card should pass the quality gate"

    bad = _ds("sort_card", [
        {"image": "a.png", "category": "Instant Settlement", "reason": "x"},
        {"image": "b.png", "category": "Digital Currency", "reason": "y"},
    ])
    ok, reason = _validate_dataset_quality(bad, "sort_card", _LOG)
    assert not ok, f"wrong-shaped sort_card must be rejected; got ok ({reason})"


# ---------------------------------------------------------------------------
# 3. CSV writer canonical headers
# ---------------------------------------------------------------------------
def _write_and_read_headers(template: str, rows: list[dict], fname: str) -> list[str]:
    ds = _ds(template, rows)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / fname
        _write_csv(ds, p, _LOG)
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
        return next(csv.reader([lines[0]]))


def test_csv_headers_are_canonical():
    h = _write_and_read_headers(
        "sort_card",
        [{"image": "a.png", "category": "1", "reason": "x"},
         {"image": "b.png", "category": "2", "reason": "y"}],
        "sort_card_data.csv",
    )
    assert h[:3] == ["Image", "Category", "Reason"], f"sort_card headers wrong: {h}"

    h = _write_and_read_headers(
        "vs_card",
        [{"metric": "Speed", "p1_value": "1", "p2_value": "2", "winner": "1"},
         {"metric": "Range", "p1_value": "3", "p2_value": "4", "winner": "2"}],
        "vs_card_data.csv",
    )
    assert "Winner" in h and "Metric" in h and "P1_Value" in h, f"vs_card headers wrong: {h}"


def test_geo_headers_unchanged():
    # geo is NOT in TEMPLATE_CSV_HEADERS -> keeps lowercase field names (renderer title()s).
    assert "geo_universal" not in TEMPLATE_CSV_HEADERS
    h = _write_and_read_headers(
        "geo_universal",
        [{"country": "India", "group": "Asia", "value": 1.0},
         {"country": "USA", "group": "NA", "value": 2.0}],
        "geo_universal_data.csv",
    )
    assert h == ["country", "group", "value"], f"geo headers should stay lowercase: {h}"


# ---------------------------------------------------------------------------
# 4. resolve_job_csv
# ---------------------------------------------------------------------------
def test_resolve_job_csv_reads_job_data_csv():
    with tempfile.TemporaryDirectory() as d:
        job_dir = Path(d)
        (job_dir / "data" / "best_fit").mkdir(parents=True)
        real_csv = job_dir / "data" / "best_fit" / "sort_card_data.csv"
        real_csv.write_text("# meta\nImage,Category,Reason\nx.png,1,ok\n", encoding="utf-8")
        job_json = job_dir / "job.json"
        job_json.write_text('{"data_csv": "data/best_fit/sort_card_data.csv"}', encoding="utf-8")

        old = os.environ.get("JOB_JSON_PATH"), os.environ.get("JOB_DIR")
        try:
            os.environ["JOB_JSON_PATH"] = str(job_json)
            os.environ["JOB_DIR"] = str(job_dir)
            got = resolve_job_csv("sort_data.csv", "/some/global/data")
            # Compare by identity (samefile) to avoid Windows 8.3 short-path vs
            # long-path string differences.
            assert os.path.exists(got) and os.path.samefile(got, str(real_csv)), \
                f"should resolve the job's csv, got {got}"
        finally:
            for k, v in (("JOB_JSON_PATH", old[0]), ("JOB_DIR", old[1])):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def test_resolve_job_csv_legacy_fallback():
    for k in ("JOB_JSON_PATH", "JOB_DIR"):
        os.environ.pop(k, None)
    got = resolve_job_csv("sort_data.csv", "/global/data")
    assert got == os.path.join("/global/data", "sort_data.csv")


# ---------------------------------------------------------------------------
# 5. Renderer-loader seam (imports manim — skipped gracefully if unavailable)
# ---------------------------------------------------------------------------
def test_renderer_loaders_parse_written_csv():
    try:
        from src.templates.Sort_card.sort_card import load_csv_with_meta
        from src.templates.Vs_card.vs_card import load_vs_csv
    except Exception as e:  # manim not importable in this env
        print(f"  [SKIP] renderer-loader seam (import failed: {e})")
        return

    with tempfile.TemporaryDirectory() as d:
        # sort_card
        sc = _ds("sort_card", [
            {"image": "a.png", "category": "1", "reason": "fast"},
            {"image": "b.png", "category": "2", "reason": "slow"},
        ])
        p = Path(d) / "sort_card_data.csv"
        _write_csv(sc, p, _LOG)
        _meta, df = load_csv_with_meta(str(p))
        cats = sorted(int(x) for x in df["Category"].tolist())
        assert cats == [1, 2], f"sort_card loader should read int tiers, got {cats}"

        # vs_card with legacy text winners ('p1'/'tie') -> mapped to 1/0
        vp = Path(d) / "vs_card_data.csv"
        vp.write_text(
            "# TITLE=T\nMetric,P1_Value,P2_Value,Winner\nSpeed,200,180,p1\nRange,1,2,tie\n",
            encoding="utf-8",
        )
        _m, vdf = load_vs_csv(str(vp))
        winners = vdf["Winner"].tolist()
        assert winners == [1, 0], f"vs_card legacy winner mapping failed: {winners}"
    print("  [OK] renderer-loader seam (sort_card + vs_card)")


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
        except Exception as e:
            print(f"  [ERROR] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed.")
    return passed == len(tests)


if __name__ == "__main__":
    logging.basicConfig(level=logging.CRITICAL)
    sys.exit(0 if _run_all() else 1)
