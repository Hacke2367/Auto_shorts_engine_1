"""
AutoShorts Core — Async Rate Limiter
====================================
A production-grade token bucket with strict inter-request pacing
and a Global Circuit Breaker for 429 penalties.
"""

from __future__ import annotations
import asyncio
import time

class TokenBucketRateLimiter:
    """Async Token Bucket with inter-request pacing for strict RPM enforcement."""

    __slots__ = (
        "capacity", "tokens", "fill_rate",
        "min_interval", "last_update", "last_grant",
        "_lock", "pause_until",
    )

    def __init__(self, rpm: int) -> None:
        if rpm <= 0:
            raise ValueError(f"RPM must be positive, got {rpm}.")

        self.capacity: float = float(rpm)
        self.tokens: float = self.capacity  # START FULL: No artificial waiting  # Cold-start: only 1 token available
        self.fill_rate: float = self.capacity / 60.0
        self.min_interval: float = 60.0 / self.capacity
        self.last_update: float = time.monotonic()
        self.last_grant: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()
        self.pause_until: float = 0.0  # NEW: Global Circuit Breaker

    async def apply_penalty(self, seconds: float = 60.0) -> None:
        """Trigger a global pause for all requests."""
        async with self._lock:
            penalty_end = time.monotonic() + seconds
            if penalty_end > self.pause_until:
                self.pause_until = penalty_end

    async def acquire(self, tokens: int = 1) -> None:
        if tokens > self.capacity:
            raise ValueError(f"Cannot acquire {tokens} tokens.")

        while True:
            async with self._lock:
                now = time.monotonic()

                # --- NEW: CIRCUIT BREAKER CHECK ---
                if now < self.pause_until:
                    wait_time = self.pause_until - now
                else:
                    # --- NORMAL TOKEN MATH ---
                    elapsed_since_update = now - self.last_update
                    self.tokens = min(
                        self.capacity,
                        self.tokens + elapsed_since_update * self.fill_rate,
                    )
                    self.last_update = now

                    time_since_last_grant = now - self.last_grant if self.last_grant > 0 else float("inf")
                    interval_ok = time_since_last_grant >= self.min_interval

                    if self.tokens >= tokens and interval_ok:
                        self.tokens -= tokens
                        self.last_grant = now
                        return

                    token_wait = (tokens - self.tokens) / self.fill_rate if self.tokens < tokens else 0.0
                    interval_wait = (self.min_interval - time_since_last_grant) if not interval_ok else 0.0
                    wait_time = max(token_wait, interval_wait, 0.01)

            # Sleep OUTSIDE the lock
            await asyncio.sleep(wait_time)


if __name__ == "__main__":
    # --- ISOLATED MANUAL TESTING ---
    print("🚀 Starting Async Rate Limiter Test...\n")


    async def worker(worker_id: int, limiter: TokenBucketRateLimiter):
        print(f"[{time.strftime('%X')}] Worker {worker_id}: Requesting token...")
        await limiter.acquire(1)
        print(f"✅ [{time.strftime('%X')}] Worker {worker_id}: Token acquired! Firing API.")


    async def main():
        # 60 RPM = exactly 1 request allowed per second
        limiter = TokenBucketRateLimiter(rpm=60)

        # Test 1: Fire 5 workers at the exact same time
        print("Testing 1: 5 workers fighting for 60 RPM (1 req/sec)...")
        tasks = [asyncio.create_task(worker(i, limiter)) for i in range(5)]
        await asyncio.gather(*tasks)
        print("\nNotice how they are strictly paced exactly ~1 second apart.\n")

        # Test 2: Triggering the Circuit Breaker (The Flaw simulation)
        print("Testing 2: Triggering a 3-second global penalty...")
        await limiter.apply_penalty(3.0)

        tasks2 = [asyncio.create_task(worker(i + 5, limiter)) for i in range(3)]
        await asyncio.gather(*tasks2)
        print("\nNotice how all workers wait 3 seconds, then immediately fight for tokens.")


    # Run the async test
    asyncio.run(main())