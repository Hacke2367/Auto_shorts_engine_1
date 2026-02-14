# src/sync/timeline.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any


def clamp(v: float, lo: float, hi: float) -> float:
    """
    clamp(v, lo, hi)
    v ko lo..hi ke beech lock kar deta hai.
    Example: clamp(0.2, 0.35, 0.85) => 0.35
             clamp(0.9, 0.35, 0.85) => 0.85
             clamp(0.7, 0.35, 0.85) => 0.7
    """
    try:
        v = float(v)
    except Exception:
        v = 0.0
    lo = float(lo)
    hi = float(hi)
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


@dataclass
class Timeline:
    totals: Dict[str, float] = field(default_factory=dict)  # segment -> total seconds
    used: Dict[str, float] = field(default_factory=dict)    # segment -> consumed seconds

    @classmethod
    def from_dict(cls, d: Dict[str, Any], defaults: Dict[str, float] | None = None) -> "Timeline":
        totals: Dict[str, float] = {}

        if defaults:
            for k, v in defaults.items():
                try:
                    totals[str(k)] = float(v)
                except Exception:
                    pass

        if isinstance(d, dict):
            for k, v in d.items():
                try:
                    totals[str(k)] = float(v)
                except Exception:
                    pass

        used = {k: 0.0 for k in totals.keys()}
        return cls(totals=totals, used=used)

    def seg_total(self, name: str, fallback: float = 0.0) -> float:
        return float(self.totals.get(name, fallback))

    def consume(self, name: str, seconds: float) -> None:
        if name not in self.used:
            self.used[name] = 0.0
        total = self.seg_total(name, 0.0)
        s = max(0.0, float(seconds))
        self.used[name] = min(total, self.used[name] + s)

    def remaining(self, name: str) -> float:
        total = self.seg_total(name, 0.0)
        used = float(self.used.get(name, 0.0))
        return max(0.0, total - used)

    def finish(self, name: str) -> float:
        rem = self.remaining(name)
        self.consume(name, rem)
        return rem
