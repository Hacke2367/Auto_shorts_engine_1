# src/captions/styles.py
from __future__ import annotations
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

_log = logging.getLogger(__name__)


@dataclass
class AssStylePreset:
    name: str = "modern_clean"
    font: str = "Segoe UI"
    font_size: int = 54
    primary_color: str = "&H00FFFFFF"   # ASS format: &HAABBGGRR (AA=alpha)
    outline_color: str = "&H80000000"
    back_color: str = "&H80000000"
    bold: int = 1
    italic: int = 0
    border_style: int = 1
    outline: int = 3
    shadow: int = 1
    alignment: int = 2               # 2 = bottom center
    margin_l: int = 80
    margin_r: int = 80
    margin_v: int = 90


def _pick_font(candidates: list[str], default_font: str = "DejaVu Sans") -> str:
    """
    Pick the first available font from candidates.
    Uses a platform-aware strategy:
    - Windows: scans C:/Windows/Fonts/ for .ttf/.otf filenames
    - Linux/Mac: uses fc-list when available
    Falls back to candidates[0] if detection is inconclusive.
    """
    if not candidates:
        return default_font

    def _fonts_windows() -> set:
        """Return a lowercase set of font family hints from C:/Windows/Fonts/."""
        fonts_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        found: set = set()
        if fonts_dir.exists():
            for f in fonts_dir.iterdir():
                if f.suffix.lower() in {".ttf", ".otf"}:
                    # Stem like "Montserrat-Bold" -> "montserrat"
                    stem = f.stem.lower().split("-")[0].split("_")[0]
                    found.add(stem)
        return found

    def _fonts_fc_list() -> set:
        """Return a lowercase set of font family names from fc-list."""
        fc = shutil.which("fc-list")
        if not fc:
            return set()
        try:
            out = subprocess.check_output([fc, ":", "family"], text=True, stderr=subprocess.DEVNULL)
            return {line.strip().lower() for line in out.splitlines() if line.strip()}
        except Exception:
            return set()

    if sys.platform == "win32":
        catalog = _fonts_windows()
    else:
        catalog = _fonts_fc_list()

    if not catalog:
        return candidates[0]

    for font_name in candidates:
        if font_name.lower() in catalog:
            return font_name

    return default_font


def get_style_preset(preset_name: str, safe_margin_px: int = 80) -> Dict[str, Any]:
    """
    Returns a style config used by the ASS renderer.
    safe_margin_px controls left/right and bottom padding.
    """
    preset_name = (preset_name or "modern_clean").strip().lower()

    # Base "premium clean"
    base = AssStylePreset(
        name=preset_name,
        font="Segoe UI",
        font_size=54,
        outline=3,
        shadow=1,
        margin_l=safe_margin_px,
        margin_r=safe_margin_px,
        margin_v=max(60, safe_margin_px),
    )

    if preset_name == "modern_clean":
        return base.__dict__.copy()

    if preset_name == "modern_premium":
        font_candidates = ["Montserrat", "Segoe UI", "Liberation Sans", "DejaVu Sans"]
        premium = AssStylePreset(
            name=preset_name,
            font=_pick_font(font_candidates),
            font_size=52,
            outline=3,
            shadow=1,
            margin_l=safe_margin_px,
            margin_r=safe_margin_px,
            margin_v=max(60, safe_margin_px),
        )
        out = premium.__dict__.copy()
        out["font_candidates"] = font_candidates
        return out

    # Unknown preset — fall back to base and warn
    _log.warning(
        "get_style_preset: unknown preset '%s', falling back to 'modern_clean'",
        preset_name,
    )
    return base.__dict__.copy()
