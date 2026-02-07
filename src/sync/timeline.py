from __future__ import annotations
from dataclasses import dataclass
from typing import Dict

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def _f(x, fallback: float) -> float:
    try:
        return float(x)
    except Exception:
        return float(fallback)

@dataclass
class Timeline:
    """
    timeline = "segment budget" system
    total[seg] = total seconds for that seg
    left[seg]  = remaining seconds after you consume animations
    """
    total: Dict[str, float]
    left: Dict[str, float]

    @classmethod
    def from_dict(cls, d: Dict[str, float] | None, defaults: Dict[str, float] | None = None) -> "Timeline":
        d = d or {}
        defaults = defaults or {}
        total = {}
        for k, v in {**defaults, **d}.items():
            total[str(k)] = max(0.0, _f(v, 0.0))
        return cls(total=total, left=dict(total))

    def seg_total(self, seg: str, fallback: float = 0.0) -> float:
        return self.total.get(seg, fallback)

    def remaining(self, seg: str) -> float:
        return self.left.get(seg, 0.0)

    def consume(self, seg: str, seconds: float) -> float:
        seconds = max(0.0, float(seconds))
        cur = self.left.get(seg, 0.0)
        use = min(cur, seconds)
        self.left[seg] = max(0.0, cur - use)
        return use
