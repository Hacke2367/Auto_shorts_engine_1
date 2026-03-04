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

import aiohttp
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.agents.core.config import settings
from src.agents.core.logger import log_api_call
from src.agents.core.models import (
    AuthorityTier,
    SourceAudit,
    TemplateDataset,
    TemplateSpec,
)


def _get_retry_policy() -> AsyncRetrying:
    """Standard exponential backoff policy for all external HTTP calls."""
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
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

    return []


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

                    # Heuristic for Authority Tier
                    tier = AuthorityTier.SECONDARY
                    lower_url = u.lower()
                    if any(x in lower_url for x in settings.primary_authority_domains):
                        tier = AuthorityTier.PRIMARY
                    elif any(x in lower_url for x in settings.social_authority_domains):
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

    return []


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
    model_name = settings.gemini_model
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"

    ideal = template_spec.capacity.ideal
    maximum = template_spec.capacity.max

    # ---------------- TEMPLATE-SPECIFIC EXAMPLES ----------------
    schema_examples: dict[str, str] = {
        "bar_chart": '{"name": "United States", "value": 28.78}',
        "butterfly_chart": '{"attribute": "Camera Quality", "p1_value": 85, "p2_value": 92}',
        "scan_race": '{"year": "2024", "entities": {"YouTube": 2.5, "TikTok": 1.7}}',
        "geo_universal": '{"country": "India", "group": "Asia", "value": 8.5}',
        "donut_breakdown": '{"category": "Smartphones", "value": 45.2}',
        "sort_card": '{"image": "", "category": "S Tier", "reason": "Unmatched performance"}',
        "vs_card": '{"metric": "Top Speed", "p1_value": "200 mph", "p2_value": "180 mph", "winner": "p1"}',
    }
    example_row = schema_examples.get(template_name, '{"key": "value"}')

    # ---------------- 10/10 PROMPT ----------------
    prompt = f"""You are a strict Data Extraction Agent for AutoShorts.
We are building data for the visual template: {template_name}.
The topic is: "{topic}"

Try to extract {ideal} items safely without hallucinating. Do NOT exceed {maximum} items.

OUTPUT SCHEMA CONSTRAINTS (CRITICAL)
Your output MUST strictly be a JSON object containing a "template_name" and an array of "rows".
Each object in the "rows" array MUST strictly follow this exact JSON structure and data types:
{example_row}

Notice the data types in the example. If a value is a string, keep it a string. If it is a dictionary/object, keep it flat.
For example, in scan_race, 'entities' MUST be a flat key-value dict, NOT a list of objects.
For sort_card, if an image URL is missing in the text, return an empty string "".

Read the following sourced Markdown texts and extract the relevant numerical/statistical data:
"""
    # Track source authority constraints
    primary_count = 0
    secondary_count = 0
    social_count = 0

    for idx, src in enumerate(context, 1):
        if src.authority_tier == AuthorityTier.PRIMARY:
            primary_count += 1
        elif src.authority_tier == AuthorityTier.SECONDARY:
            secondary_count += 1
        else:
            social_count += 1

        prompt += f"\n--- SOURCE {idx} ({src.authority_tier.value}) ---\nURL: {src.url}\n{src.raw_snippet[:5000]}\n"

    # Surface lightweight conflict note/authority distribution info
    authority_distribution = f"{primary_count} Primary, {secondary_count} Secondary, {social_count} Social"
    log.info("Extraction context contains %s sources.", authority_distribution)

    # Emit lightweight consistency/conflict note if mixing high and low tiers
    if primary_count > 0 and (secondary_count > 0 or social_count > 0):
        log.warning(
            "Conflict Note: Context mixes Primary authoritative sources with lower-tier sources. "
            "Gemini is instructed to prefer Primary truth if metrics conflict."
        )
    elif secondary_count > 0 and social_count > 0:
        log.info(
            "Consistency Note: Context mixes Secondary and Social sources. "
            "Verify output for social-media bias."
        )

    prompt += f"""
Return purely a JSON object with "template_name": "{template_name}" and a "rows" array.
Each row MUST match the exact example structure shown above. Do NOT invent new keys.
DO NOT emit Markdown blocks like ```json ... ```, just emit the raw curly-brace JSON.

Do not hallucinate data. Only extract facts found in the texts. If sources disagree, prefer Primary sources over Secondary/Social.
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": settings.gemini_temperature,
        },
    }

    async for attempt in _get_retry_policy():
        with attempt:
            t0 = time.perf_counter()
            async with session.post(url, json=payload) as resp:
                elapsed = (time.perf_counter() - t0) * 1000
                log_api_call(
                    log,
                    service="gemini.extract",
                    status_code=resp.status,
                    retry_count=attempt.retry_state.attempt_number - 1,
                    duration_ms=elapsed,
                )
                resp.raise_for_status()
                data = await resp.json()

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

                try:
                    parsed = json.loads(json_str)
                except json.JSONDecodeError as err:
                    log.error("Failed to parse extracted JSON: %s\nRaw: %s", err, json_str[:500])
                    raise ValueError("parse_failure: JSON syntax error in Gemini output") from err

                try:
                    # Validate the raw dict using our Pydantic schema
                    dataset = TemplateDataset.model_validate(parsed)
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
