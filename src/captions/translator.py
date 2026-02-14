# src/captions/translator.py
from __future__ import annotations
from typing import Dict, Any, List


def translate_script_map(
    script_map: Dict[str, Any],
    source_lang: str,
    target_langs: List[str],
    enabled: bool = False,
) -> Dict[str, Any]:
    """
    Prototype v1:
    - By default enabled=False -> no translation, just return input.
    Future:
    - Integrate your translation provider here and fill script_map[seg]['text'][lang]
    """
    if not enabled:
        return script_map

    raise NotImplementedError(
        "Translation is not enabled in prototype v1. "
        "For now, put translated text directly in script.json."
    )
