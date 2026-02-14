from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

from src.config import ASSETS_DIR

# All SFX live here (absolute or relative; both ok)
SFX_BASE_DIR = os.path.join(ASSETS_DIR, "sfx")

@dataclass(frozen=True)
class SfxDef:
    files: List[str]
    vol: float = 0.85  # linear multiplier

def resolve_rel_path(filename: str) -> str:
    # Use os.path.join for Windows safety
    return os.path.join(SFX_BASE_DIR, filename)

# ✅ Library that matches YOUR ACTUAL sfx folder filenames
SFX_LIBRARY: Dict[str, SfxDef] = {
    # --- UI / text ---
    "ui_click":   SfxDef(["ui_click_01.wav", "ui_click_02.wav"], vol=0.60),
    "ui_tick":    SfxDef(["ui_tick_01.wav", "ui_tick_02.wav"], vol=0.55),

    # --- scanning ---
    "scan_tick":  SfxDef(["scan_beep_01.wav", "scan_beep_02.wav"], vol=0.55),

    # --- glitch / intro ---
    "glitch":     SfxDef(["glitch_pop_01.wav"], vol=0.70),
    "riser":      SfxDef(["riser_short_01.wav"], vol=0.75),
    "hit_soft":   SfxDef(["impact_hit_soft_01.wav"], vol=0.75),

    # --- transitions / whoosh ---
    "sweep":      SfxDef(["ui_transition_sweep_01.wav"], vol=0.65),
    "whoosh_short": SfxDef(["ui_whoosh_short_01.wav", "ui_whoosh_short_02.wav"], vol=0.70),
    "whoosh_soft":  SfxDef(["ui_whoosh_soft_01.wav"], vol=0.70),

    # --- confirm / winner ---
    "success":    SfxDef(["success_chime_01.wav"], vol=0.80),

    # ======================================================
    # ✅ ALIASES: keys that appear in sfx_marks.json
    # (so you don't need to change template code)
    # ======================================================
    "ui_pop":       SfxDef(["ui_click_01.wav", "ui_click_02.wav"], vol=0.65),
    "intro_glitch": SfxDef(["glitch_pop_01.wav"], vol=0.75),
    "intro_rise":   SfxDef(["riser_short_01.wav"], vol=0.80),
    "intro_hit":    SfxDef(["impact_hit_soft_01.wav"], vol=0.80),
    "charge_up":    SfxDef(["ui_transition_sweep_01.wav"], vol=0.70),
    "impact_soft":  SfxDef(["impact_hit_soft_01.wav"], vol=0.80),
    "winner_rise":  SfxDef(["success_chime_01.wav"], vol=0.85),
}

def resolve(event: str, count_index: int = 0) -> Optional[dict]:
    """
    Returns {"rel_path": "...", "vol": ...} or None if not found.
    count_index cycles variants for repeatable variety.
    """
    d = SFX_LIBRARY.get(event)
    if not d or not d.files:
        return None
    chosen = d.files[count_index % len(d.files)]
    return {"rel_path": resolve_rel_path(chosen), "vol": float(d.vol)}

# Backward-compatible name used by some codebases
def pick_variant(event: str, count_index: int) -> Optional[dict]:
    return resolve(event, count_index)
