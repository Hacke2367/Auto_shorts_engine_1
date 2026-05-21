# src/captions/translator.py
from __future__ import annotations
import logging
from typing import Dict, Any, List

_log = logging.getLogger(__name__)


def translate_script_map(
    script_map: Dict[str, Any],
    source_lang: str,
    target_langs: List[str],
    enabled: bool = False,
) -> Dict[str, Any]:
    """
    Prototype v1:
    - enabled=False (default) -> no translation, returns input unchanged.
    Future:
    - Integrate your translation provider here and fill script_map[seg]['text'][lang]
    """
    if not enabled:
        if target_langs:
            _log.debug(
                "translate_script_map: translation disabled; target_langs=%s ignored",
                target_langs,
            )
        return script_map

    raise NotImplementedError(
        "Translation is not enabled in prototype v1. "
        "For now, put translated text directly in script.json."
    )
