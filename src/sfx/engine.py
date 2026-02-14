# src/sfx/engine.py
from __future__ import annotations
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from src.sfx.registry import pick_variant

@dataclass
class SfxMark:
    t: float
    event: str
    rel_path: str
    vol: float

class SFXEngine:
    """
    Template-side marker engine.
    - Use: sfx.mark("scan_tick")
    - Writes marks to: <job_dir>/output/sfx_marks.json
    """
    def __init__(self, scene, job_dir: str, enabled: bool = True):
        self.scene = scene
        self.job_dir = job_dir
        self.enabled = enabled
        self._marks: List[Dict[str, Any]] = []
        self._counts: Dict[str, int] = {}

    def now(self) -> float:
        # Manim keeps scene.time as current timeline time (seconds)
        try:
            return float(self.scene.time)
        except Exception:
            return 0.0

    def mark(self, event: str, offset: float = 0.0, vol: Optional[float] = None):
        """
        Record an SFX event at current time (+ offset).
        vol override optional.
        """
        if not self.enabled:
            return

        idx = self._counts.get(event, 0)
        self._counts[event] = idx + 1

        picked = pick_variant(event, idx)
        if not picked:
            # Unknown event -> ignore silently (or print if you want)
            return

        t = max(0.0, self.now() + float(offset))
        out_vol = float(vol) if vol is not None else float(picked["vol"])
        rel_path = str(picked["rel_path"])

        self._marks.append({
            "t": t,
            "event": event,
            "rel_path": rel_path,
            "vol": out_vol,
        })

    def flush(self, filename: str = "sfx_marks.json") -> str:
        """
        Write marks into job_dir/output/filename.
        Returns written file path.
        """
        out_dir = os.path.join(self.job_dir, "output")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, filename)

        # sort by time (safe)
        self._marks.sort(key=lambda x: float(x.get("t", 0.0)))

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self._marks, f, indent=2)

        return out_path
