from src.agents.core.models import TemplateDataset, BarChartRow, VsCardRow

def get_dummy_dataset(num_rows: int = 3, template: str = "bar_chart") -> TemplateDataset:
    """Provides a deterministic dummy dataset for testing Phase 2 expansion."""
    rows = []
    if template == "bar_chart":
        for i in range(1, num_rows + 1):
            rows.append(BarChartRow(
                name=f"Dummy Item {i}",
                value=float(i * 10),
            ))
        meta = {"TITLE": "Dummy Title", "SUB": "Dummy Sub"}
    elif template == "vs_card":
        for i in range(1, num_rows + 1):
            rows.append(VsCardRow(
                metric=f"Metric {i}",
                p1_value=str(10 * i),
                p2_value=str(5 * i),
                winner="Player 1",
                emoji="🔥",
                notes=f"Player 1 dominated metric {i}.",
                weight=1.0,
                category="Performance"
            ))
        meta = {"TITLE": "P1 vs P2", "SUB": "Showdown", "P1_NAME": "P1", "P2_NAME": "P2"}
    else:
        raise ValueError(f"Template {template} not supported in dummy data.")

    return TemplateDataset(
        template_name=template,
        topic="Test Topic: Dummy Data Evaluation",
        rows=rows,
        meta=meta
    )
