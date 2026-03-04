"""
AutoShorts — Manual Data Generation Test
=========================================
Isolated test that bypasses Tavily search/scrape and directly invokes
gemini_extract() with synthetic SourceAudit context for all 7 templates.

Usage:
    python tests/manual_test_data_gen.py

Zero production code is modified. All imports are read-only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import aiohttp

from src.agents.core.config import settings
from src.agents.core.models import (
    AuthorityTier,
    SourceAudit,
    TemplateDataset,
    TEMPLATE_CAPACITIES,
    TEMPLATE_ROW_MAP,
    VALID_TEMPLATES,
)
from src.agents.core.rate_limiter import TokenBucketRateLimiter
from src.agents.phase1_extraction.api_clients import gemini_extract
from src.agents.phase1_extraction.runner import _build_template_spec

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("test.data_gen")

# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------

OUTPUT_DIR = PROJECT_ROOT / "tests" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Mock SourceAudit factory
# ---------------------------------------------------------------------------


def _mock_source(url: str, snippet: str, tier: AuthorityTier = AuthorityTier.SECONDARY) -> SourceAudit:
    return SourceAudit(url=url, raw_snippet=snippet, authority_tier=tier)


# ---------------------------------------------------------------------------
# Test Case Definitions — one per template
# ---------------------------------------------------------------------------

TEST_CASES: list[dict] = [
    # ── bar_chart ──────────────────────────────────────────────────
    {
        "template": "bar_chart",
        "topic": "Top 5 Countries by GDP 2024",
        "context": [
            _mock_source(
                url="https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
                snippet="""
## World GDP Rankings 2024
The World Bank released the following nominal GDP estimates for 2024 (in trillions USD):
| Country        | GDP (Trillion USD) |
|---------------|-------------------|
| United States  | 28.78              |
| China          | 18.53              |
| Germany        | 4.59               |
| Japan          | 4.11               |
| India          | 3.94               |
| United Kingdom | 3.50               |
Source: World Bank Open Data, January 2024 update.
""",
                tier=AuthorityTier.PRIMARY,
            ),
            _mock_source(
                url="https://en.wikipedia.org/wiki/List_of_countries_by_GDP_(nominal)",
                snippet="""
As of 2024, the United States remains the world's largest economy with a nominal GDP
of approximately $28.78 trillion, followed by China ($18.53T), Germany ($4.59T),
Japan ($4.11T), and India ($3.94T). The gap between the US and China has widened
slightly compared to 2023 estimates.
""",
            ),
        ],
    },
    # ── butterfly_chart ────────────────────────────────────────────
    {
        "template": "butterfly_chart",
        "topic": "iPhone 16 Pro vs Samsung Galaxy S25 Ultra",
        "context": [
            _mock_source(
                url="https://www.gsmarena.com/compare.php3?idPhone1=12345&idPhone2=12346",
                snippet="""
## iPhone 16 Pro vs Galaxy S25 Ultra — Full Spec Comparison

| Attribute       | iPhone 16 Pro | Galaxy S25 Ultra |
|----------------|--------------|-----------------|
| Battery (mAh)   | 4685          | 5000             |
| Display (inches)| 6.3           | 6.9              |
| RAM (GB)        | 8             | 12               |
| Weight (grams)  | 199           | 218              |
| Camera (MP)     | 48            | 200              |
| Storage (GB)    | 256           | 256              |
| Price (USD)     | 999           | 1299             |
| Antutu Score    | 1650000       | 1720000          |
""",
                tier=AuthorityTier.SECONDARY,
            ),
        ],
    },
    # ── scan_race ──────────────────────────────────────────────────
    {
        "template": "scan_race",
        "topic": "YouTube vs TikTok Monthly Active Users 2019-2024",
        "context": [
            _mock_source(
                url="https://www.statista.com/statistics/272014/global-social-networks-ranked-by-number-of-users/",
                snippet="""
## Monthly Active Users (MAU) Over Time — YouTube vs TikTok

| Year | YouTube MAU (billions) | TikTok MAU (billions) |
|------|----------------------|---------------------|
| 2019 | 2.0                   | 0.5                  |
| 2020 | 2.3                   | 0.85                 |
| 2021 | 2.5                   | 1.0                  |
| 2022 | 2.6                   | 1.2                  |
| 2023 | 2.7                   | 1.5                  |
| 2024 | 2.8                   | 1.8                  |

YouTube has maintained its lead but TikTok's growth rate is significantly faster,
growing from 500 million users in 2019 to over 1.8 billion by 2024.
""",
                tier=AuthorityTier.PRIMARY,
            ),
        ],
    },
    # ── geo_universal ──────────────────────────────────────────────
    {
        "template": "geo_universal",
        "topic": "Top 8 Military Spenders by Country 2024",
        "context": [
            _mock_source(
                url="https://www.sipri.org/databases/milex",
                snippet="""
## Military Expenditure by Country 2024 (SIPRI)

| Country       | Group  | Spending (Billion USD) |
|--------------|--------|----------------------|
| United States | NATO   | 916                   |
| China         | Non-aligned | 296              |
| Russia        | Non-aligned | 109              |
| India         | Non-aligned | 83.6             |
| Saudi Arabia  | Non-aligned | 75.8             |
| United Kingdom| NATO   | 74.9                  |
| Germany       | NATO   | 66.8                  |
| France        | NATO   | 61.3                  |

Source: Stockholm International Peace Research Institute, 2024 Yearbook.
""",
                tier=AuthorityTier.PRIMARY,
            ),
        ],
    },
    # ── donut_breakdown ────────────────────────────────────────────
    {
        "template": "donut_breakdown",
        "topic": "Global Smartphone Market Share Q4 2024",
        "context": [
            _mock_source(
                url="https://www.idc.com/promo/smartphone-market-share",
                snippet="""
## Worldwide Smartphone Market Share Q4 2024

| Brand    | Market Share (%) |
|----------|-----------------|
| Samsung  | 19.4             |
| Apple    | 23.7             |
| Xiaomi   | 14.1             |
| OPPO     | 8.8              |
| vivo     | 7.6              |
| Others   | 26.4             |

Apple reclaimed the top spot globally in Q4 2024, driven by iPhone 16 series demand.
Samsung held steady at 19.4%. Chinese brands Xiaomi, OPPO, and vivo collectively
accounted for over 30% of the market. Source: IDC Quarterly Mobile Phone Tracker.
""",
                tier=AuthorityTier.PRIMARY,
            ),
        ],
    },
    # ── sort_card ──────────────────────────────────────────────────
    {
        "template": "sort_card",
        "topic": "Best Programming Languages 2024 Tier List",
        "context": [
            _mock_source(
                url="https://www.tiobe.com/tiobe-index/",
                snippet="""
## TIOBE Programming Community Index — January 2024

Based on search engine queries, job postings, and community activity:

- **S Tier**: Python — dominant in AI/ML, data science, web. #1 spot for 3 years straight.
- **S Tier**: JavaScript — backbone of the web, massive ecosystem.
- **A Tier**: Java — enterprise powerhouse, Android development.
- **A Tier**: C++ — systems programming, game engines, high performance.
- **B Tier**: C# — strong in game dev (Unity), enterprise .NET.
- **B Tier**: Go — cloud-native, microservices, DevOps tooling.
- **C Tier**: Rust — loved by devs but niche adoption, memory safety focus.

Source: TIOBE Software BV, January 2024 report.
""",
                tier=AuthorityTier.SECONDARY,
            ),
        ],
    },
    # ── vs_card ────────────────────────────────────────────────────
    {
        "template": "vs_card",
        "topic": "Tesla Model 3 vs BMW i4 2024",
        "context": [
            _mock_source(
                url="https://www.edmunds.com/car-comparisons/tesla-model-3-vs-bmw-i4.html",
                snippet="""
## Tesla Model 3 vs BMW i4 — Head-to-Head Comparison

| Metric          | Tesla Model 3   | BMW i4          | Winner     |
|----------------|----------------|-----------------|------------|
| Base Price      | $38,990         | $52,200         | Tesla      |
| Range (miles)   | 363             | 301             | Tesla      |
| 0-60 mph (sec)  | 5.8             | 5.5             | BMW        |
| Cargo (cu ft)   | 23              | 18              | Tesla      |
| Horsepower      | 271 hp          | 335 hp          | BMW        |
| Charging Speed  | 250 kW          | 200 kW          | Tesla      |

Tesla Model 3 wins on value and range, while the BMW i4 offers a sportier
driving experience with more horsepower and faster acceleration.
""",
                tier=AuthorityTier.SECONDARY,
            ),
        ],
    },
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_all_tests() -> None:
    """Execute all 7 template tests sequentially with rate limiting."""
    limiter = TokenBucketRateLimiter(rpm=settings.gemini_rpm_limit)

    passed = 0
    failed = 0
    results: dict[str, str] = {}

    print("\n" + "=" * 64)
    print("  AutoShorts -- Manual Data Generation Test")
    print(f"  Model: {settings.gemini_model}  |  RPM: {settings.gemini_rpm_limit}")
    print("=" * 64 + "\n")

    async with aiohttp.ClientSession() as session:
        for idx, case in enumerate(TEST_CASES, 1):
            template = case["template"]
            topic = case["topic"]
            context: list[SourceAudit] = case["context"]

            print(f"[{idx}/7] Testing: {template}")
            print(f"        Topic: {topic}")

            # Build the exact TemplateSpec the production pipeline would use
            spec = _build_template_spec(template)

            # Rate-limit before each Gemini call
            await limiter.acquire()

            try:
                dataset: TemplateDataset = await gemini_extract(
                    topic=topic,
                    context=context,
                    template_name=template,
                    template_spec=spec,
                    session=session,
                    log=log,
                )

                # If we got here, Pydantic validation already passed inside gemini_extract
                row_count = len(dataset.rows)
                cap = TEMPLATE_CAPACITIES[template]

                # Save to output
                out_path = OUTPUT_DIR / f"{template}_result.json"
                out_path.write_text(
                    json.dumps(dataset.model_dump(mode="json"), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

                print(f"        [PASS]  |  {row_count} rows (ideal={cap.ideal}, max={cap.max})")
                print(f"        Saved -> {out_path.relative_to(PROJECT_ROOT)}")
                results[template] = "PASS"
                passed += 1

            except Exception as e:
                print(f"        [FAIL]  |  {type(e).__name__}: {e}")
                results[template] = f"FAIL: {e}"
                failed += 1

            print()

    # Final report
    print("=" * 64)
    print("  RESULTS SUMMARY")
    print("=" * 64)
    for tmpl, status in results.items():
        icon = "[OK]" if status == "PASS" else "[XX]"
        print(f"  {icon}  {tmpl:<20s}  {status}")
    print(f"\n  Total: {passed} passed, {failed} failed out of {len(TEST_CASES)}")
    print("=" * 64)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
