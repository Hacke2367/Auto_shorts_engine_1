# src/captions/script_loader.py
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Any, List

_log = logging.getLogger(__name__)


def _normalize_text_map(seg: Dict[str, Any]) -> Dict[str, str]:
    """
    Extracts language-keyed text from a segment dict.
    Supported forms:
      - {"text": {"hi": "...", "en": "..."}}
      - {"texts": {"hi": "...", "en": "..."}}
      - {"text": "plain string"}  -> {"default": "..."}
      - {"default": "...", "hi": "...", "en": "..."}  (direct keys)
    Output: {"hi": "...", "en": "...", "default": "..."}
    """
    out: Dict[str, str] = {}

    # 1) Prefer "text"
    text = seg.get("text", None)
    if isinstance(text, str):
        out["default"] = text
        return {k: str(v) for k, v in out.items() if str(v).strip()}

    if isinstance(text, dict):
        for k, v in text.items():
            if v is None:
                continue
            out[str(k).strip()] = str(v)

    # 2) Also allow "texts"
    texts = seg.get("texts", None)
    if isinstance(texts, dict):
        for k, v in texts.items():
            if v is None:
                continue
            out[str(k).strip()] = str(v)

    # 3) "default" key on segment
    if "default" in seg and isinstance(seg.get("default"), str):
        out["default"] = str(seg.get("default"))

    # 4) Direct language keys e.g. {"hi": "...", "en": "..."}
    #    Fallback used when none of the above yielded anything
    if not out:
        for k, v in seg.items():
            if not isinstance(k, str):
                continue
            if k.lower() in ("name", "id", "segment", "keywords", "keyword", "meta", "text", "texts"):
                continue
            if isinstance(v, str) and v.strip():
                out[k.strip()] = v

    # Clean empties
    out = {k: str(v) for k, v in out.items() if k and str(v).strip()}
    return out


def _normalize_keywords(seg: Dict[str, Any]) -> List[str]:
    """Normalizes the keywords list from a segment dict."""
    kw = seg.get("keywords", [])
    if not isinstance(kw, list):
        return []
    out = []
    for x in kw:
        s = str(x).strip()
        if s:
            out.append(s)
    return out


def _segment_name_from_obj(s: Dict[str, Any]) -> str:
    """
    Picks the segment name from a segment dict.
    Priority: "name" > "id" > "segment"
    """
    for k in ("name", "id", "segment"):
        v = s.get(k, "")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def load_script_json(script_path: Path) -> Dict[str, Any]:
    """
    Loads script.json and returns:
      {
        "hook":   {"text": {"hi": "...", "en": "...", "default": "..."}, "keywords":[...]},
        "setup":  {...},
        ...
      }

    Supported script.json roots:
      A) {"segments": [ {name/id, text/texts/default/...}, ... ]}
      B) {"segments": { "hook": {...}, "setup": {...} }}
      C) { "hook": {...}, "setup": {...} }  (root map)
    """
    if not script_path.is_file():
        raise FileNotFoundError(f"script.json not found or is not a file: {script_path}")

    with script_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("script.json root must be a JSON object (dict).")

    out: Dict[str, Any] = {}

    # ---------- Case A/B: "segments" exists ----------
    if "segments" in data:
        segs = data.get("segments")

        # A) segments = list
        if isinstance(segs, list):
            for i, s in enumerate(segs):
                if not isinstance(s, dict):
                    continue
                name = _segment_name_from_obj(s)
                if not name:
                    _log.warning(
                        "script.json: skipping unnamed segment at index %d "
                        "(no 'name', 'id', or 'segment' key found)",
                        i,
                    )
                    continue

                text_map = _normalize_text_map(s)
                keywords = _normalize_keywords(s)

                out[name] = {
                    "text": text_map,
                    "keywords": keywords,
                }
            return out

        # B) segments = dict (map)
        if isinstance(segs, dict):
            for name, seg_data in segs.items():
                if not isinstance(name, str) or not name.strip():
                    continue
                name = name.strip()

                if isinstance(seg_data, str):
                    seg_obj = {"text": {"default": seg_data}}
                elif isinstance(seg_data, dict):
                    seg_obj = seg_data
                else:
                    seg_obj = {}

                text_map = _normalize_text_map(seg_obj)
                keywords = _normalize_keywords(seg_obj)

                out[name] = {
                    "text": text_map,
                    "keywords": keywords,
                }
            return out

        raise ValueError("script.json 'segments' must be a list or dict.")

    # ---------- Case C: root map ----------
    # root dict keys are segment names
    for name, seg_data in data.items():
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()

        if isinstance(seg_data, str):
            seg_obj = {"text": {"default": seg_data}}
        elif isinstance(seg_data, dict):
            seg_obj = seg_data
        else:
            continue

        text_map = _normalize_text_map(seg_obj)
        keywords = _normalize_keywords(seg_obj)

        out[name] = {
            "text": text_map,
            "keywords": keywords,
        }

    return out


def pick_text_for_lang(
    seg_data: Dict[str, Any],
    lang: str,
    fallback_lang: str = "default",
) -> str:
    """
    Picks text for the desired language with smart fallback:
      - exact match: "en"
      - region fallback: "en-US" -> "en"
      - fallback_lang: "default"
      - otherwise first available
    """
    text_map = seg_data.get("text", {})
    if not isinstance(text_map, dict):
        return ""

    lang = (lang or "").strip()
    fallback_lang = (fallback_lang or "default").strip()

    # exact
    if lang and lang in text_map:
        return str(text_map[lang])

    # region fallback: en-US -> en
    if lang and "-" in lang:
        base = lang.split("-", 1)[0].strip()
        if base and base in text_map:
            return str(text_map[base])

    # fallback lang
    if fallback_lang in text_map:
        return str(text_map[fallback_lang])

    # last fallback: first available
    for _, v in text_map.items():
        return str(v)

    return ""
