# src/captions/styles.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any


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


def get_style_preset(preset_name: str, safe_margin_px: int = 80) -> Dict[str, Any]:
    """
    Returns a style config used by the ASS renderer.
    safe_margin_px controls left/right and bottom padding.
    """
    preset_name = (preset_name or "modern_clean").strip().lower()

    # Base “premium clean”
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
        return base.__dict__

    # You can add more presets later (neon, minimal, etc.)
    return base.__dict__
