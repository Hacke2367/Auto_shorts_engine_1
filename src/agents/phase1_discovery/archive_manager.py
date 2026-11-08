"""
AutoShorts Phase 1A — Topic Archive Manager (v2)
=================================================
Implements the 5+15 Rule and Negative Hashing with proper state semantics.

Three distinct states:
  - **produced** — topic successfully became a video (60-day cooldown).
  - **rejected** — topic was explicitly rejected (14-day cooldown).
  - **saved_queue** — strong topic not selected this round (reusable).

Design Principles:
  - Timestamps on every entry for TTL enforcement.
  - Lazy expiry on duplicate checks.
  - Backward-compatible migration from old set/list-based archives.
  - Atomic writes (temp file → rename) — no corruption.
  - Defensive load (missing, corrupt, old-schema all handled safely).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.agents.core.models import ArchiveEntry, QueuedTopic

logger = logging.getLogger(__name__)

# TTL constants (from archive_policy.md v1.0)
PRODUCED_TTL_DAYS: int = 60
REJECTED_TTL_DAYS: int = 14


class ArchiveManager:
    """Manages produced, rejected, and queued topic states."""

    def __init__(self, archive_path: Path | None = None) -> None:
        from src.agents.core.job_manager import PROJECT_ROOT

        self._archive_path: Path = archive_path or (
            PROJECT_ROOT / "jobs" / "topic_archive.json"
        )
        self._archive_path.parent.mkdir(parents=True, exist_ok=True)

        self._produced: dict[str, ArchiveEntry] = {}
        self._rejected: dict[str, ArchiveEntry] = {}
        self._saved_queue: list[QueuedTopic] = []

        # Snapshots of {produced, rejected, saved_queue} as of the last
        # successful _load(). Used by _save() to detect local mutations
        # (additions/removals) that must survive the disk re-read it does
        # for cross-process safety. See _save() for details.
        self._produced_baseline: dict[str, ArchiveEntry] = {}
        self._rejected_baseline: dict[str, ArchiveEntry] = {}
        self._saved_queue_baseline: list[QueuedTopic] = []

        self._load()
        # NOTE: expire_stale_entries() is NOT called here.
        # Call it explicitly at session start via run_discovery or CLI.

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_duplicate(self, topic: str) -> bool:
        """Check if a topic is blocked by produced or rejected cooldowns.

        Side-effect: lazily expires stale entries encountered during check.
        """
        norm = self.normalize_topic(topic)
        now = datetime.now(timezone.utc)

        expired = False
        # Check produced
        entry = self._produced.get(norm)
        if entry is not None:
            if self._is_within_ttl(entry.created_at, PRODUCED_TTL_DAYS, now):
                return True
            # Expired — remove lazily
            del self._produced[norm]
            logger.debug("Lazily expired produced entry: '%s'", norm)
            expired = True

        # Check rejected
        entry = self._rejected.get(norm)
        if entry is not None:
            if self._is_within_ttl(entry.created_at, REJECTED_TTL_DAYS, now):
                return True
            del self._rejected[norm]
            logger.debug("Lazily expired rejected entry: '%s'", norm)
            expired = True

        if expired:
            self._save()

        return False

    def mark_produced(self, topic: str, reason: str | None = None) -> None:
        """Mark a topic as successfully produced into a video."""
        norm = self.normalize_topic(topic)

        # Reconcile states
        if norm in self._rejected:
            del self._rejected[norm]
        self._saved_queue = [q for q in self._saved_queue if q.normalized_topic != norm]
        if norm not in self._produced:
            self._produced[norm] = ArchiveEntry(
                topic=topic, normalized_topic=norm, reason=reason
            )
            self._save()
            logger.info("Marked produced: '%s'", topic)

    def mark_rejected(self, topic: str, reason: str | None = None) -> None:
        """Mark a topic as explicitly rejected."""
        norm = self.normalize_topic(topic)

        # Reconcile states
        self._saved_queue = [q for q in self._saved_queue if q.normalized_topic != norm]
        if norm in self._produced:  # ADDED: Remove from produced if rejecting later
            del self._produced[norm]

        if norm not in self._rejected:
            self._rejected[norm] = ArchiveEntry(
                topic=topic, normalized_topic=norm, reason=reason
            )
            self._save()
            logger.info("Marked rejected: '%s' (reason=%s)", topic, reason)

    def add_to_queue(self, queued_topic: QueuedTopic) -> None:
        """Add a strong topic to the saved queue (not rejected)."""
        # Dedupe by normalized_topic
        existing_norms = {q.normalized_topic for q in self._saved_queue}
        if queued_topic.normalized_topic not in existing_norms:
            self._saved_queue.append(queued_topic)
            self._save()
            logger.info("Queued topic: '%s'", queued_topic.topic)
        else:
            logger.debug(
                "Queue already contains '%s', skipping.",
                queued_topic.topic,
            )

    def get_queue(self) -> list[QueuedTopic]:
        """Return all queued topics (read-only snapshot)."""
        return list(self._saved_queue)

    def pop_queue(self, limit: int | None = None) -> list[QueuedTopic]:
        """Pop N topics from the front of the saved queue."""
        count = limit if limit is not None else len(self._saved_queue)
        popped = self._saved_queue[:count]
        self._saved_queue = self._saved_queue[count:]
        if popped:
            self._save()
        return popped

    def remove_from_queue(self, topic: str) -> None:
        """Remove a specific topic from the saved queue."""
        norm = self.normalize_topic(topic)
        before = len(self._saved_queue)
        self._saved_queue = [
            q for q in self._saved_queue if q.normalized_topic != norm
        ]
        if len(self._saved_queue) < before:
            self._save()
            logger.info("Removed '%s' from saved queue.", topic)

    def expire_stale_entries(self) -> None:
        """Explicitly purge all expired entries from produced and rejected."""
        now = datetime.now(timezone.utc)
        produced_before = len(self._produced)
        rejected_before = len(self._rejected)

        self._produced = {
            k: v
            for k, v in self._produced.items()
            if self._is_within_ttl(v.created_at, PRODUCED_TTL_DAYS, now)
        }
        self._rejected = {
            k: v
            for k, v in self._rejected.items()
            if self._is_within_ttl(v.created_at, REJECTED_TTL_DAYS, now)
        }

        removed_p = produced_before - len(self._produced)
        removed_r = rejected_before - len(self._rejected)
        if removed_p or removed_r:
            self._save()
            logger.info(
                "Expired %d produced, %d rejected entries.", removed_p, removed_r
            )

    @staticmethod
    def normalize_topic(topic: str) -> str:
        """Normalise a topic string for robust duplicate checking."""
        topic = topic.lower().strip()
        topic = re.sub(r"\s+", " ", topic)
        return topic

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _is_within_ttl(
        created_at: datetime, ttl_days: int, now: datetime
    ) -> bool:
        """Return True if the entry is still within its cooldown window."""
        # Ensure timezone-aware comparison
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return (now - created_at) < timedelta(days=ttl_days)

    def _load(self) -> None:
        """Load archive from disk with backward-compatible migration."""
        if not self._archive_path.exists():
            return

        try:
            raw = self._archive_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(
                "Failed to load topic archive: %s. Starting fresh.", e
            )
            return

        if not isinstance(data, dict):
            logger.warning("Archive root is not a dict. Starting fresh.")
            return

        # --- Backward migration: old format used lists/sets ---
        raw_produced = data.get("produced", {})
        raw_rejected = data.get("rejected", {})
        raw_queue = data.get("saved_queue", [])

        self._produced = self._migrate_entries(raw_produced, "produced")
        self._rejected = self._migrate_entries(raw_rejected, "rejected")
        self._saved_queue = self._migrate_queue(raw_queue)

        # Record this as the new baseline: the state-as-on-disk at this
        # moment, against which future local mutations will be diffed in
        # _save() (see _save() for why this is necessary).
        self._produced_baseline = dict(self._produced)
        self._rejected_baseline = dict(self._rejected)
        self._saved_queue_baseline = list(self._saved_queue)

        logger.debug(
            "Loaded archive: %d produced, %d rejected, %d queued",
            len(self._produced),
            len(self._rejected),
            len(self._saved_queue),
        )

    @staticmethod
    def _migrate_entries(
        raw: Any, label: str
    ) -> dict[str, ArchiveEntry]:
        """Migrate produced/rejected from any old format to timestamped dict."""
        entries: dict[str, ArchiveEntry] = {}

        if isinstance(raw, dict):
            for key, val in raw.items():
                try:
                    if isinstance(val, dict):
                        # New format: full ArchiveEntry dict
                        entries[key] = ArchiveEntry.model_validate(val)
                    elif isinstance(val, str):
                        # Old format v1.5: key -> ISO timestamp string
                        entries[key] = ArchiveEntry(
                            topic=key,
                            normalized_topic=key,
                            created_at=datetime.fromisoformat(val),
                        )
                    else:
                        logger.warning(
                            "Skipping invalid %s entry: %s=%r",
                            label, key, val,
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to migrate %s entry '%s': %s", label, key, e
                    )
        elif isinstance(raw, list):
            # Old format v1.0: plain list of topic strings
            for item in raw:
                if isinstance(item, str):
                    entries[item] = ArchiveEntry(
                        topic=item, normalized_topic=item
                    )
                else:
                    logger.warning(
                        "Skipping non-string in old %s list: %r", label, item
                    )
        else:
            logger.warning(
                "Unexpected %s type %s. Ignoring.", label, type(raw).__name__
            )

        return entries

    @staticmethod
    def _migrate_queue(raw: Any) -> list[QueuedTopic]:
        """Migrate saved_queue from any old format to QueuedTopic list."""
        queue: list[QueuedTopic] = []
        if not isinstance(raw, list):
            return queue

        for item in raw:
            if isinstance(item, dict):
                try:
                    queue.append(QueuedTopic.model_validate(item))
                except Exception as e:
                    logger.warning("Skipping invalid queue entry: %s", e)
            else:
                logger.warning(
                    "Skipping non-dict queue entry: %r", item
                )
        return queue

    def _merge_pending_into_disk_state(
        self,
        pending_produced: dict[str, ArchiveEntry],
        pending_rejected: dict[str, ArchiveEntry],
        pending_queue: list[QueuedTopic],
        base_produced_keys: set[str],
        base_rejected_keys: set[str],
        base_queue_norms: set[str],
    ) -> dict[str, Any]:
        """Combine the freshly-reloaded disk state (already in self._*) with
        the in-memory mutation that triggered this save.

        ``pending_*`` is the in-memory state right before the disk re-read —
        i.e. "disk state we last loaded, plus our local mutation".
        ``base_*`` is the state as of that last load — i.e. "disk state
        before our local mutation". The difference between ``pending`` and
        ``base`` is exactly our local mutation (additions and/or removals),
        which we replay on top of the just-reloaded ``self._*`` so that:
          - our own change is preserved (fixes entries silently vanishing), and
          - any concurrent additions picked up by the reload are kept too.
        """
        merged_produced = dict(self._produced)
        for key in base_produced_keys - pending_produced.keys():
            merged_produced.pop(key, None)  # locally removed -> stays removed
        merged_produced.update(pending_produced)  # locally added/kept -> present

        merged_rejected = dict(self._rejected)
        for key in base_rejected_keys - pending_rejected.keys():
            merged_rejected.pop(key, None)
        merged_rejected.update(pending_rejected)

        pending_queue_norms = {q.normalized_topic for q in pending_queue}
        removed_norms = base_queue_norms - pending_queue_norms
        merged_queue = [q for q in self._saved_queue if q.normalized_topic not in removed_norms]
        seen_norms = {q.normalized_topic for q in merged_queue}
        for q in pending_queue:
            if q.normalized_topic not in seen_norms:
                merged_queue.append(q)
                seen_norms.add(q.normalized_topic)

        self._produced = merged_produced
        self._rejected = merged_rejected
        self._saved_queue = merged_queue

        return {
            "produced": {k: v.model_dump(mode="json") for k, v in self._produced.items()},
            "rejected": {k: v.model_dump(mode="json") for k, v in self._rejected.items()},
            "saved_queue": [q.model_dump(mode="json") for q in self._saved_queue],
        }

    def _save(self) -> None:
        """Persist archive to disk using an atomic write with cross-process locking."""
        lock_path = self._archive_path.with_suffix(".lock")

        # Snapshot the in-memory state that triggered this save (i.e. the
        # baseline from the last _load(), plus whatever mutation the caller
        # just applied), BEFORE _load() re-reads disk and overwrites self._*.
        pending_produced = dict(self._produced)
        pending_rejected = dict(self._rejected)
        pending_queue = list(self._saved_queue)
        base_produced_keys = set(self._produced_baseline.keys())
        base_rejected_keys = set(self._rejected_baseline.keys())
        base_queue_norms = {q.normalized_topic for q in self._saved_queue_baseline}

        if sys.platform == "win32":
            import msvcrt

            # Acquire exclusive advisory lock via msvcrt on Windows
            lock_fd = open(lock_path, "wb")
            try:
                # Lock first byte of the lock file exclusively (blocking)
                msvcrt.locking(lock_fd.fileno(), msvcrt.LK_LOCK, 1)

                # Re-read from disk to pick up changes made by another process
                # while we were waiting for the lock
                self._load()

                payload: dict[str, Any] = self._merge_pending_into_disk_state(
                    pending_produced, pending_rejected, pending_queue,
                    base_produced_keys, base_rejected_keys, base_queue_norms,
                )

                fd, tmp_path = tempfile.mkstemp(
                    dir=str(self._archive_path.parent), suffix=".tmp", prefix=".archive_"
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(payload, f, indent=2, ensure_ascii=False)
                    os.replace(tmp_path, str(self._archive_path))
                except BaseException as e:
                    logger.error("Atomic save of archive failed: %s", e)
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise
            finally:
                try:
                    msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
                lock_fd.close()
        else:
            import fcntl

            lock_fd = open(lock_path, "w")
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)

                # Re-read from disk to pick up changes made by another process
                # while we were waiting for the lock
                self._load()

                payload = self._merge_pending_into_disk_state(
                    pending_produced, pending_rejected, pending_queue,
                    base_produced_keys, base_rejected_keys, base_queue_norms,
                )

                fd, tmp_path = tempfile.mkstemp(
                    dir=str(self._archive_path.parent), suffix=".tmp", prefix=".archive_"
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(payload, f, indent=2, ensure_ascii=False)
                    os.replace(tmp_path, str(self._archive_path))
                except BaseException as e:
                    logger.error("Atomic save of archive failed: %s", e)
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()

        # The just-persisted state becomes the new baseline for any
        # subsequent _save() calls on this instance.
        self._produced_baseline = dict(self._produced)
        self._rejected_baseline = dict(self._rejected)
        self._saved_queue_baseline = list(self._saved_queue)


if __name__ == "__main__":
    import shutil
    from datetime import datetime, timedelta, timezone
    from unittest.mock import patch
    from src.agents.core.job_manager import PROJECT_ROOT
    from src.agents.core.models import QueuedTopic

    print("🔥 Starting EXHAUSTIVE Archive Manager Test Suite...\n")
    test_path = PROJECT_ROOT / "jobs" / "exhaustive_test_archive.json"

    # Clean start
    if test_path.exists(): test_path.unlink()
    am = ArchiveManager(archive_path=test_path)

    try:
        # ---------------------------------------------------------
        # Scenario 1: Aggressive Normalization Edge Cases
        # ---------------------------------------------------------
        print("▶ Scenario 1: Normalization Edge Cases")
        assert am.normalize_topic("  AI   History  ") == "ai history", "Failed to strip extra spaces"
        assert am.normalize_topic("AI\nHistory") == "ai history", "Failed to handle newline characters"
        assert am.normalize_topic("ai history") == "ai history", "Failed lowercase handling"

        # ---------------------------------------------------------
        # Scenario 2: Time Travel & Lazy Expiration (TTL Check)
        # ---------------------------------------------------------
        print("▶ Scenario 2: Time Travel & Lazy Expiration")
        # We temporarily hijack python's 'datetime' to simulate time passing
        with patch('src.agents.phase1_discovery.archive_manager.datetime') as mock_dt:
            # Set time to Day 1
            mock_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
            mock_dt.now.return_value = mock_now

            am.mark_produced("Future Tech")
            assert am.is_duplicate("Future Tech") == True, "Should be blocked on Day 1"

            # Fast forward time by 61 days!
            mock_dt.now.return_value = mock_now + timedelta(days=61)

            # This should trigger the lazy expiration automatically
            assert am.is_duplicate("Future Tech") == False, "TTL Failed! The topic is still blocked after 61 days!"

        # ---------------------------------------------------------
        # Scenario 3: The State Conflict Battle (Flaw 1 Check)
        # ---------------------------------------------------------
        print("▶ Scenario 3: State Reconciliation")
        am.mark_produced("Rust vs C++")
        am.mark_rejected("Rust vs C++")  # User changed their mind

        # If you didn't apply the fix I gave you, this will crash here.
        assert "rust vs c++" not in am._produced, "❌ FLAW 1 NOT FIXED: Topic is still trapped in 'produced' list!"
        assert "rust vs c++" in am._rejected, "Topic should be in 'rejected' list."

        # ---------------------------------------------------------
        # Scenario 4: Queue Deduplication & Popping
        # ---------------------------------------------------------
        print("▶ Scenario 4: Queue Dedupe & Popping")
        qt1 = QueuedTopic(topic="Quantum Computing", normalized_topic="quantum computing",
                          best_fit_template="bar_chart", final_score=9.0)
        qt2 = QueuedTopic(topic="  Quantum   Computing ", normalized_topic="quantum computing",
                          best_fit_template="vs_card", final_score=8.0)

        am.add_to_queue(qt1)
        am.add_to_queue(qt2)  # Should be completely ignored

        queue = am.get_queue()
        assert len(queue) == 1, "❌ Queue allowed a duplicate entry!"

        popped = am.pop_queue(1)
        assert len(popped) == 1, "Pop didn't return the item"
        assert len(am.get_queue()) == 0, "Pop didn't remove the item from the queue!"

        print("\n✅ ALL EXHAUSTIVE TESTS PASSED. Your fixes worked perfectly. Your memory engine is solid.")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        print("Tumne fixes sahi se apply nahi kiye hain. Fix them before moving on.")

    finally:
        # Clean up the dummy file so we don't leave trash on your hard drive
        if test_path.exists(): test_path.unlink()