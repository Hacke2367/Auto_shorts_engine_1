"""
AutoShorts Phase 1B — API Clients (Tavily & Gemini)
==================================================
Strict asynchronous wrappers for external HTTP services.

Design Principles:
  - Uses aiohttp and tenacity (exponential backoff).
  - Emits telemetry via log_api_call.
  - Zero hallucinations — extracts structured JSON matching Pydantic.
  - Robust JSON parsing using a balanced-brace parser.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import aiohttp
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.agents.core.config import settings, APP_CONFIG
from src.agents.core.retry import standard_retry_policy
from src.agents.core.logger import log_api_call
from src.agents.core.cost_tracker import track_gemini_call, track_rate_limit_hit
from src.agents.core.models import (
    AuthorityTier,
    SourceAudit,
    TemplateDataset,
    TemplateSpec,
    TEMPLATE_META_KEYS,
    TEMPLATE_PRESENTATION_FIELDS,
    TEMPLATE_EXTRACTION_RULES,
)


def _get_retry_policy() -> AsyncRetrying:
    """Standard transient-error retry (config-driven, see APP_CONFIG.retry).

    Used by the Tavily search/extract calls, which are reliable.
    """
    return standard_retry_policy()


def _get_gemini_retry_policy() -> AsyncRetrying:
    """Patient retry for the heavy Phase 1B Gemini extract call.

    The whole topic's extraction hinges on this single call, so it gets the
    more patient ``extraction_*`` profile (mirrors ideation) to ride out the
    transient 503 bursts that the default 3-attempt profile could not survive.
    """
    rc = APP_CONFIG.retry
    return standard_retry_policy(
        min_wait=rc.extraction_min_wait,
        max_wait=rc.extraction_max_wait,
        max_attempts=rc.extraction_max_attempts,
    )


# ---------------------------------------------------------------------------
# Tavily Clients
# ---------------------------------------------------------------------------


async def tavily_search(
    query: str,
    session: aiohttp.ClientSession,
    log: logging.Logger,
    max_results: int = 5,
) -> list[str]:
    """Search for relevant web pages via Tavily."""
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": settings.tavily_api_key.get_secret_value(),
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "include_raw_content": False,
    }

    async for attempt in _get_retry_policy():
        with attempt:
            t0 = time.perf_counter()
            async with session.post(url, json=payload) as resp:
                elapsed = (time.perf_counter() - t0) * 1000
                log_api_call(
                    log,
                    service="tavily.search",
                    status_code=resp.status,
                    retry_count=attempt.retry_state.attempt_number - 1,
                    duration_ms=elapsed,
                )
                resp.raise_for_status()
                data = await resp.json()

                urls = [res.get("url") for res in data.get("results", []) if res.get("url")]
                log.info("Tavily search found %d URLs for: %s", len(urls), query)
                return urls

    raise RuntimeError(f"tavily_search exhausted retries for query: {query!r}")


async def tavily_extract(
    urls: list[str],
    session: aiohttp.ClientSession,
    log: logging.Logger,
) -> list[SourceAudit]:
    """Extract raw markdown content from a list of URLs."""
    if not urls:
        return []

    endpoint = "https://api.tavily.com/extract"
    payload = {
        "api_key": settings.tavily_api_key.get_secret_value(),
        "urls": urls,
    }

    async for attempt in _get_retry_policy():
        with attempt:
            t0 = time.perf_counter()
            async with session.post(endpoint, json=payload) as resp:
                elapsed = (time.perf_counter() - t0) * 1000
                log_api_call(
                    log,
                    service="tavily.extract",
                    status_code=resp.status,
                    retry_count=attempt.retry_state.attempt_number - 1,
                    duration_ms=elapsed,
                )
                resp.raise_for_status()
                data = await resp.json()

                audits: list[SourceAudit] = []
                for res in data.get("results", []):
                    u = res.get("url")
                    text = res.get("raw_content")
                    if not u or not text:
                        continue

                    # Heuristic for Authority Tier — suffix matching to avoid
                    # false positives (e.g. "gov" matching "government-agency.com")
                    parsed_url = urlparse(u)
                    netloc = parsed_url.netloc.lower()

                    tier = AuthorityTier.SECONDARY
                    if any(
                        netloc == d or netloc.endswith(f".{d}")
                        for d in APP_CONFIG.primary_authority_domains
                    ):
                        tier = AuthorityTier.PRIMARY
                    elif any(
                        netloc == d or netloc.endswith(f".{d}")
                        for d in APP_CONFIG.social_authority_domains
                    ):
                        tier = AuthorityTier.SOCIAL

                    audits.append(
                        SourceAudit(
                            url=u,
                            raw_snippet=text,
                            scraped_at=datetime.now(timezone.utc),
                            authority_tier=tier,
                            context="Tavily Extract",
                        )
                    )

                log.info("Tavily extract parsed %d documents.", len(audits))
                return audits

    raise RuntimeError(f"tavily_extract exhausted retries for {len(urls)} URLs")


# ---------------------------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------------------------


async def gemini_extract(
    topic: str,
    context: list[SourceAudit],
    template_name: str,
    template_spec: TemplateSpec,
    session: aiohttp.ClientSession,
    log: logging.Logger,
) -> TemplateDataset:
    """Use Gemini to map unstructured text into strictly typed JSON rows."""
    key = settings.gemini_api_key.get_secret_value()
    cfg = APP_CONFIG.llm.extraction
    model_name = cfg.model
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    _gemini_headers = {"x-goog-api-key": key, "Content-Type": "application/json"}

    minimum = template_spec.capacity.min
    ideal = template_spec.capacity.ideal
    maximum = template_spec.capacity.max

    meta_keys = TEMPLATE_META_KEYS.get(template_name, ["TITLE", "SUB"])

    # Does this template carry a row-level 'image' field specifically? Only such
    # templates (currently sort_card) get the slug + sourcing-guide instructions;
    # other templates may have non-image presentation fields (e.g. vs_card's
    # emoji/notes/category, excluded from the null-rate gate below) without
    # triggering image-slug prompt instructions that don't apply to their rows.
    presentation_fields = TEMPLATE_PRESENTATION_FIELDS.get(template_name, set())
    has_images = "image" in presentation_fields

    # ---------------- TEMPLATE-SPECIFIC EXAMPLES ----------------
    schema_examples: dict[str, str] = {
        "bar_chart": '{"name": "United States", "value": 28.78}',
        "butterfly_chart": '{"attribute": "Camera Quality", "p1_value": 85, "p2_value": 92}',
        "scan_race": '{"year": "2024", "entities": {"YouTube": 2.5, "TikTok": 1.7}}',
        "geo_universal": '{"country": "India", "group": "Asia", "value": 8.5}',
        "donut_breakdown": '{"category": "Smartphones", "value": 45.2}',
        "sort_card": '{"image": "apple_pay_logo.png", "category": 1, "reason": "Top performer"}',
        "vs_card": '{"metric": "Top Speed", "p1_value": "200 mph", "p2_value": "180 mph", "winner": 1}',
    }
    example_row = schema_examples.get(template_name, '{"key": "value"}')
    _META_EXAMPLES: dict[str, str] = {
        "TITLE": "Top 6 Nations",
        "SUB": "Ranked by personal savings rate.",
        "METRIC": "Personal Savings Rate",
        "UNIT": "% of disposable income",
        "P1": "iPhone 15 Pro",
        "P2": "Samsung S24",
        "P1_NAME": "Apple",
        "P2_NAME": "Samsung",
        "MODE": "choropleth",
    }
    example_meta = {k: _META_EXAMPLES.get(k, "Short descriptive text.") for k in meta_keys}

    # For image templates the LLM returns a THIRD top-level key alongside
    # meta/rows; for all others the payload shape is exactly meta + rows.
    if has_images:
        _guide_example = (
            ',\n  "image_sourcing_guide": '
            '{"apple_pay_logo.png": "The Apple Pay wordmark/logo on a dark background."}'
        )
        _keys_clause = "exactly three keys: 'meta', 'rows', and 'image_sourcing_guide'"
        _return_clause = (
            'Return purely a JSON object with "meta", "rows", and "image_sourcing_guide" keys.'
        )
        _image_clause = (
            "\nIMAGE ASSET RULE (CRITICAL): For each row's 'image' field, output a short, "
            "descriptive, lowercase slug FILENAME ending in '.png' that captures the item's "
            "visual identity (e.g. 'apple_pay_logo.png', 'tap_to_pay_terminal.png'). "
            "NEVER output a web URL, and NEVER leave it empty. "
            "Then add the top-level 'image_sourcing_guide' object mapping EACH image filename "
            "to a one-sentence human-readable visual description so an operator can source the "
            "real asset. Do NOT add any other new keys to the rows themselves.\n"
        )
    else:
        _guide_example = ""
        _keys_clause = "exactly two keys: 'meta' and 'rows'"
        _return_clause = 'Return purely a JSON object with "meta" and "rows" keys.'
        _image_clause = ""

    # Template-specific renderer-contract rules — semantic VALUE constraints the
    # bare schema example cannot convey (e.g. sort_card 'category' must be 1 or 2,
    # vs_card 'winner' must be 0/1/2). This is the instruction gap that produced
    # wrong-shaped data; the extraction quality gate also enforces these.
    _rules_clause = TEMPLATE_EXTRACTION_RULES.get(template_name, "")
    if _rules_clause:
        _rules_clause = (
            f"\nTEMPLATE-SPECIFIC RULES (MUST follow exactly):\n{_rules_clause}\n"
        )

    full_example_payload = f"""{{
  "meta": {json.dumps(example_meta)},
  "rows": [
    {example_row},
    {example_row}
  ]{_guide_example}
}}"""

    # ---------------- 10/10 PROMPT ----------------
    prompt = f"""You are a strict Data Extraction Agent for AutoShorts.
We are building data for the visual template: {template_name}.
The topic is: "{topic}"

ITEM COUNT (IMPORTANT): Extract EVERY valid item the sources support — aim for {ideal}, and AT LEAST {minimum}, up to a hard cap of {maximum}. Do not stop early once you have a few; scan ALL sources for every qualifying item. But NEVER invent, pad, or duplicate rows to reach the target — only include items genuinely backed by the sources. If the sources truly support fewer than {minimum}, extract only what is real (never fabricate to fill the count).

OUTPUT SCHEMA CONSTRAINTS (CRITICAL)
You MUST return a single JSON object with {_keys_clause}. The 'meta' object must contain these exact keys: {meta_keys}. Generate highly accurate, punchy YouTube Shorts titles/subtitles based directly on the topic and extracted data. Keep titles under 4 words. The 'rows' key must contain the array of extracted data objects.
Your output MUST strictly follow this exact JSON structure and data types:
{full_example_payload}

Notice the data types in the example. If a value is a string, keep it a string. If it is a dictionary/object, keep it flat.
For example, in scan_race, 'entities' MUST be a flat key-value dict, NOT a list of objects.
{_image_clause}{_rules_clause}
Read the following sourced Markdown texts and extract the relevant numerical/statistical data:
"""
    for idx, src in enumerate(context, 1):
        prompt += f"\n--- SOURCE {idx} ({src.authority_tier.value}) ---\nURL: {src.url}\n{src.raw_snippet[:5000]}\n"

    prompt += f"""
{_return_clause}
Each row in the "rows" array MUST match the exact example structure shown above. Do NOT invent new keys.
DO NOT emit Markdown blocks like ```json ... ```, just emit the raw curly-brace JSON.

Do not hallucinate data. Only extract facts found in the texts. If sources disagree, prefer Primary sources.
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": cfg.temperature,
        },
    }

    async for attempt in _get_gemini_retry_policy():
        with attempt:
            t0 = time.perf_counter()
            async with session.post(url, json=payload, headers=_gemini_headers) as resp:
                elapsed = (time.perf_counter() - t0) * 1000
                log_api_call(
                    log,
                    service="gemini.extract",
                    status_code=resp.status,
                    retry_count=attempt.retry_state.attempt_number - 1,
                    duration_ms=elapsed,
                )
                if resp.status == 429:
                    track_rate_limit_hit()
                resp.raise_for_status()
                data = await resp.json()

                usage = data.get("usageMetadata", {})
                track_gemini_call(
                    phase="extraction",
                    model=model_name,
                    prompt_tokens=usage.get("promptTokenCount", 0),
                    output_tokens=usage.get("candidatesTokenCount", 0),
                )

                try:
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError) as err:
                    raise ValueError(f"Malformed Gemini API response format: {data}") from err

                # Robust JSON object extraction
                start_idx = raw_text.find("{")
                if start_idx == -1:
                    raise ValueError(f"No JSON object found in response: {raw_text[:200]}")

                json_str = raw_text.strip()
                brace_count = 0
                in_string = False
                escape = False

                for i in range(start_idx, len(raw_text)):
                    char = raw_text[i]
                    if escape:
                        escape = False
                        continue
                    if char == '\\':
                        escape = True
                        continue
                    if char == '"':
                        in_string = not in_string
                        continue

                    if not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                json_str = raw_text[start_idx:i + 1]
                                break

                if brace_count != 0:
                    raise ValueError(
                        f"parse_failure: Unbalanced JSON braces in Gemini response "
                        f"(open={brace_count}). First 200 chars: {raw_text[:200]!r}"
                    )

                try:
                    parsed = json.loads(json_str)
                except json.JSONDecodeError as err:
                    log.error("Failed to parse extracted JSON: %s\nRaw: %s", err, json_str[:500])
                    raise ValueError("parse_failure: JSON syntax error in Gemini output") from err

                # Defensively coerce the optional sourcing guide. It is decorative
                # operator metadata, so a malformed value must NEVER fail extraction
                # (no new failure surface) — anything non-dict degrades to empty.
                _guide_raw = parsed.get("image_sourcing_guide", {})
                if isinstance(_guide_raw, dict):
                    image_sourcing_guide = {str(k): str(v) for k, v in _guide_raw.items()}
                else:
                    image_sourcing_guide = {}

                # The renderer-contract integer fields ('category' tier, 'winner')
                # are stored as STRINGS by the row models, but the LLM may emit them
                # as JSON numbers. Coerce numeric scalars -> str so model_validate
                # accepts them however they were emitted. VALUE validity (must be
                # 1/2 or 0/1/2) is enforced later by validate_template_semantics.
                _rows = parsed.get("rows", [])
                if isinstance(_rows, list):
                    for _row in _rows:
                        if not isinstance(_row, dict):
                            continue
                        for _k in ("category", "winner"):
                            _v = _row.get(_k)
                            if isinstance(_v, bool):
                                continue
                            if isinstance(_v, int):
                                _row[_k] = str(_v)
                            elif isinstance(_v, float):
                                _row[_k] = str(int(_v)) if _v.is_integer() else str(_v)

                try:
                    # Validate the raw dict using our Pydantic schema
                    dataset = TemplateDataset.model_validate({
                        "template_name": template_name,
                        "meta": parsed.get("meta", {}),
                        "rows": _rows,
                        "image_sourcing_guide": image_sourcing_guide,
                    })
                except Exception as err:
                    log.error("Schema validation failed for %s: %s", template_name, err)
                    raise ValueError(f"schema_failure: Extracted data violates {template_name} schema") from err

                log.info(
                    "Gemini successfully extracted %d %s rows.",
                    len(dataset.rows),
                    template_name,
                )
                return dataset

    raise RuntimeError("Exhausted retries connecting to Gemini.")
