# Waiting on the owner

## H-1 (open) Turn on OpenAI billing
OpenAI returns `billing_not_active` on every call, so Phase 1 (topic/data) and Phase 2 (script)
cannot run. Blocks plan step 10. Fix at platform.openai.com -> Billing.

## H-2 (open) Gemini key is invalid
Returns "API key not valid". Renew it, or drop the Gemini A/B option.

## H-3 (open) Brand name and handle
Top-left still says "BIGDATA LEAK". Set `BRAND_NAME` / `BRAND_HANDLE` in `src/config.py`.

## H-4 (open) Check two historical prices before posting the Gold vs Bitcoin video
Nov 2016 and Nov 2021 gold/BTC prices in `jobs/vs_job/job_vs_card_2` came from model knowledge,
not a fetched source (`data/best_fit/sources_audit.json`). Red line #1.

## H-5 (open) India states map asset
`assets/svgs/world.svg` is a 21 KB single-outline map; zoomed to India it is a blob, and Indian
state data all pins to one point. Needs an India states map asset: pick the source and licence,
and confirm it shows the official Survey of India boundary (J&K, Ladakh, Arunachal) before any
India map is published. Blocks the rest of plan step 7.

