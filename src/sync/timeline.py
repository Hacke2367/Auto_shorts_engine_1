# src/sync/timeline.py
from __future__ import annotations
import warnings
from dataclasses import dataclass, field
from typing import Dict, Any


def clamp(v: float, lo: float, hi: float) -> float:
    """
    Clamps v to the range [lo, hi].
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
                    warnings.warn(
                        f"Timeline.from_dict: skipping key '{k}' — value {v!r} "
                        "cannot be converted to float",
                        stacklevel=2,
                    )

        used = {k: 0.0 for k in totals.keys()}
        return cls(totals=totals, used=used)

    def seg_total(self, name: str, fallback: float = 0.0) -> float:
        return float(self.totals.get(name, fallback))

    def consume(self, name: str, seconds: float) -> float:
        """Consume time from a segment. Returns how much was actually consumed.
        Warns when the requested amount exceeds the remaining budget (>10ms tolerance)."""
        if name not in self.used:
            self.used[name] = 0.0
        total = self.seg_total(name, 0.0)
        s = max(0.0, float(seconds))
        remaining = max(0.0, total - self.used[name])
        actually_consumed = min(remaining, s)
        if s > remaining + 0.01:
            warnings.warn(
                f"Timeline.consume('{name}', {s:.3f}s): overrun by {s - remaining:.3f}s "
                f"(budget={total:.3f}s, used={self.used[name]:.3f}s)",
                stacklevel=2,
            )
        self.used[name] += actually_consumed
        return actually_consumed

    def remaining(self, name: str) -> float:
        total = self.seg_total(name, 0.0)
        used = float(self.used.get(name, 0.0))
        return max(0.0, total - used)

    def finish(self, name: str) -> float:
        rem = self.remaining(name)
        self.consume(name, rem)
        return rem
