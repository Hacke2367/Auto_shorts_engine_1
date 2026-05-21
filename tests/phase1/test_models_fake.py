from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from src.agents.core.models import (
    AuditTrail,
    BarChartRow,
    SourceAudit,
    TemplateDataset,
    TopicCandidate,
    VsCardRow,
)


def test_template_dataset_accepts_correct_rows():
    ds = TemplateDataset(
        template_name="bar_chart",
        rows=[
            BarChartRow(name="A", value=10),
            BarChartRow(name="B", value=20),
        ],
    )
    assert ds.template_name == "bar_chart"
    assert len(ds.rows) == 2


def test_template_dataset_rejects_wrong_row_type():
    try:
        TemplateDataset(
            template_name="bar_chart",
            rows=[
                VsCardRow(
                    metric="Speed",
                    p1_value="10",
                    p2_value="8",
                    winner="A",
                )
            ],
        )
        raise AssertionError("Expected wrong row type validation error")
    except ValidationError:
        pass
    except ValueError:
        pass


def test_template_dataset_rejects_capacity_overflow():
    rows = [BarChartRow(name=f"Item{i}", value=i) for i in range(11)]  # max is 10
    try:
        TemplateDataset(template_name="bar_chart", rows=rows)
        raise AssertionError("Expected capacity overflow validation error")
    except ValidationError:
        pass
    except ValueError:
        pass


def test_topic_candidate_computes_final_score():
    c = TopicCandidate(
        topic="Nvidia vs AMD revenue race",
        normalized_topic="nvidia-vs-amd-revenue-race",
        virality_score=8,
        data_feasibility_score=9,
        template_fit_score=8,
        visual_potential_score=9,
        source_quality_score=7,
        fallback_strength_score=6,
        best_fit_template="vs_card",
        fallback_template="bar_chart",
    )
    assert c.final_score > 0
    assert c.best_fit_template == "vs_card"


def test_topic_candidate_rejects_invalid_template():
    try:
        TopicCandidate(
            topic="Bad template topic",
            normalized_topic="bad-template-topic",
            best_fit_template="not_a_real_template",
        )
        raise AssertionError("Expected invalid template validation error")
    except ValidationError:
        pass
    except ValueError:
        pass


def test_audit_trail_saves_file():
    trail = AuditTrail(job_id="job_test_01", template_name="bar_chart")
    trail.add_source(
        SourceAudit(
            url="https://example.com",
            raw_snippet="Example snippet",
        )
    )

    with TemporaryDirectory() as tmpdir:
        out = trail.save_to_file(Path(tmpdir))
        assert out.exists(), "sources_audit.json was not created"
        assert out.name == "sources_audit.json"


def main():
    tests = [
        test_template_dataset_accepts_correct_rows,
        test_template_dataset_rejects_wrong_row_type,
        test_template_dataset_rejects_capacity_overflow,
        test_topic_candidate_computes_final_score,
        test_topic_candidate_rejects_invalid_template,
        test_audit_trail_saves_file,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            print(f"PASS: {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__} -> {e}")
            failed += 1

    print(f"\\nSUMMARY: passed={passed}, failed={failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()