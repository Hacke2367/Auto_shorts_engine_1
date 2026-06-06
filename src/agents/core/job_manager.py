"""
AutoShorts Phase 0 — Job Manager & Idempotency Engine
======================================================
Creates and manages the ``jobs/{template}/{job_id}/`` directory tree.
Supports ``template_name="auto"`` for discovery-first flows.
Provides crash-safe pipeline state tracking via ``.pipeline_state.json``.

Design Principles:
  - Atomic state writes (temp file → ``os.replace``) survive mid-write crashes.
  - ``is_step_completed`` never raises — returns ``False`` on any corruption.
  - Auto-generates ``job_id`` from template + current UTC timestamp if omitted.
  - Validates ``template_name`` against the canonical template registry.
  - Integrates with ``logger.py`` for structured per-job logging.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agents.core.logger import setup_job_logger
from src.agents.core.models import VALID_TEMPLATES

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]  # → MANIM_VIDEOS_CODE_TEMPALTE/
_STATE_FILENAME: str = ".pipeline_state.json"
_SUBDIRS: tuple[str, ...] = ("data", "audio", "script", "output")
_AUTO_SUBDIRS: tuple[str, ...] = ("discovery", "attempts")
_AUTO_TEMPLATE: str = "auto"

# ---------------------------------------------------------------------------
# JobManager
# ---------------------------------------------------------------------------


class JobManager:
    """Creates and manages the lifecycle of a single pipeline job.

    Usage::

        jm = JobManager(template_name="vs_card")
        jm.initialize()

        if not jm.is_step_completed("phase1_discovery"):
            await run_discovery(jm)
            jm.mark_step_completed("phase1_discovery", {"rows": 6})
    """

    # -- Construction -------------------------------------------------------

    def __init__(
        self,
        template_name: str,
        job_id: str | None = None,
        *,
        jobs_root: Path | None = None,
    ) -> None:
        """Initialise a job manager.

        Args:
            template_name: Must match a key in ``VALID_TEMPLATES``.
            job_id: Unique identifier.  Generated if ``None``.
            jobs_root: Override the default ``{PROJECT_ROOT}/jobs`` directory.

        Raises:
            ValueError: If ``template_name`` is unknown and not ``"auto"``.
        """
        self._is_auto: bool = template_name == _AUTO_TEMPLATE
        if not self._is_auto and template_name not in VALID_TEMPLATES:
            raise ValueError(
                f"Unknown template '{template_name}'. "
                f"Valid: {sorted(VALID_TEMPLATES)} + ['auto']"
            )

        self._template_name: str = template_name
        self._jobs_root: Path = (jobs_root or PROJECT_ROOT / "jobs").resolve()
        self._job_id: str = job_id or self._generate_job_id(template_name, self._jobs_root)

        # Derived paths
        self._job_dir: Path = self._jobs_root / template_name / self._job_id
        self._state_file: Path = self._job_dir / _STATE_FILENAME

        # Lazily-initialised logger
        self._logger: logging.Logger | None = None

    # -- Public properties --------------------------------------------------

    @property
    def template_name(self) -> str:
        return self._template_name

    @property
    def job_id(self) -> str:
        return self._job_id

    @property
    def job_dir(self) -> Path:
        return self._job_dir

    @property
    def data_dir(self) -> Path:
        return self._job_dir / "data"

    @property
    def audio_dir(self) -> Path:
        return self._job_dir / "audio"

    @property
    def script_dir(self) -> Path:
        return self._job_dir / "script"

    @property
    def output_dir(self) -> Path:
        return self._job_dir / "output"

    @property
    def is_auto_mode(self) -> bool:
        """True if this job was created in auto-discovery mode."""
        return self._is_auto

    @property
    def discovery_dir(self) -> Path:
        """Directory for discovery outputs (auto-mode only)."""
        return self._job_dir / "discovery"

    @property
    def attempts_dir(self) -> Path:
        """Directory for extraction attempt subfolders (auto-mode only)."""
        return self._job_dir / "attempts"

    # -- Directory Setup ----------------------------------------------------

    def initialize(self) -> Path:
        """Create the full job directory tree.  Idempotent.

        Returns:
            The ``job_dir`` path.
        """
        if self._is_auto:
            # Auto-mode: discovery + attempts layout
            for subdir in _AUTO_SUBDIRS:
                (self._job_dir / subdir).mkdir(parents=True, exist_ok=True)
        else:
            # Manual mode: standard layout
            for subdir in _SUBDIRS:
                (self._job_dir / subdir).mkdir(parents=True, exist_ok=True)

        # Seed the state file if it doesn't exist yet
        if not self._state_file.exists():
            seed_state: dict[str, Any] = {
                "job_id": self._job_id,
                "template": self._template_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "steps": {},
            }
            self._write_state(seed_state)

        self.get_logger().info(
            "Job directory initialised → %s", self._job_dir
        )
        return self._job_dir

    # -- Idempotency Engine -------------------------------------------------

    def is_step_completed(self, step_name: str) -> bool:
        """Check whether a pipeline step has already been completed.

        Returns ``False`` on missing, corrupt, or unreadable state files
        (never raises an exception).
        """
        state = self._read_state()
        if state is None:
            return False
        return step_name in state.get("steps", {})

    def mark_step_completed(
        self,
        step_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Mark a pipeline step as completed.

        Args:
            step_name: Logical step identifier (e.g. ``"phase1_discovery"``).
            metadata: Optional dict of extra context to persist alongside
                      the completion record.

        The write is **atomic** (temp file → ``os.replace``).
        """
        state = self._read_state() or {
            "job_id": self._job_id,
            "template": self._template_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "steps": {},
        }

        step_record: dict[str, Any] = {
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        if metadata:
            step_record["metadata"] = metadata

        state.setdefault("steps", {})[step_name] = step_record
        self._write_state(state)

        self.get_logger().info(
            "Step marked completed: '%s'",
            step_name,
            extra={"step_name": step_name, "data": metadata},
        )

    def get_step_metadata(self, step_name: str) -> dict[str, Any] | None:
        """Retrieve the metadata dict for a completed step, or ``None``."""
        state = self._read_state()
        if state is None:
            return None
        step = state.get("steps", {}).get(step_name)
        if step is None:
            return None
        return step.get("metadata")

    def get_completed_steps(self) -> list[str]:
        """Return a list of all completed step names."""
        state = self._read_state()
        if state is None:
            return []
        return list(state.get("steps", {}).keys())

    # -- Logging Integration ------------------------------------------------

    def get_logger(self) -> logging.Logger:
        """Return a structured logger bound to this job's directory.

        The logger is created on first call and cached for the lifetime
        of this ``JobManager`` instance.
        """
        if self._logger is None:
            self._job_dir.mkdir(parents=True, exist_ok=True)
            self._logger = setup_job_logger(self._job_dir, self._job_id)
        return self._logger

    # -- Internals ----------------------------------------------------------

    def set_template(self, template_name: str) -> None:
        """Update the template in metadata (auto-mode only).

        This does **not** move directories. It only updates the internal
        template reference and the state file metadata.
        """
        if not self._is_auto:
            raise RuntimeError("set_template() is only allowed in auto-mode.")

        if template_name not in VALID_TEMPLATES:
            raise ValueError(f"Unknown template '{template_name}'.")
        self._template_name = template_name

        for subdir in ("data", "audio", "script", "output"):
            (self._job_dir / subdir).mkdir(parents=True, exist_ok=True)

        state = self._read_state()
        if state is not None:
            state["template"] = template_name
            self._write_state(state)

        self.get_logger().info(
            "Template updated to '%s' (metadata only).", template_name
        )

    def get_attempt_dir(self, template_name: str, attempt_num: int) -> Path:
        """Return the path for an extraction attempt folder.

        Layout: ``jobs/auto/{job_id}/attempts/{NN}_{template_name}/``
        """
        if not self._is_auto:
            raise RuntimeError("get_attempt_dir() is only allowed in auto-mode.")

        safe_template = re.sub(r"[^a-zA-Z0-9_-]", "_", template_name)
        folder_name = f"{attempt_num:02d}_{safe_template}"
        attempt_dir = self.attempts_dir / folder_name
        attempt_dir.mkdir(parents=True, exist_ok=True)
        return attempt_dir

    @staticmethod
    def _generate_job_id(template_name: str, jobs_root: Path) -> str:
        """Generate a short sequential job ID: {template}_1, {template}_2, …

        Scans the existing job bucket directory and increments from the
        highest number found.  Thread-safe enough for single-user CLI use.
        """
        safe_template = re.sub(r"[^a-zA-Z0-9_-]", "_", template_name)
        bucket_dir = jobs_root / template_name
        pattern = re.compile(rf"^{re.escape(safe_template)}_(\d+)$")

        max_n = 0
        if bucket_dir.is_dir():
            for entry in bucket_dir.iterdir():
                m = pattern.match(entry.name)
                if m:
                    max_n = max(max_n, int(m.group(1)))

        return f"{safe_template}_{max_n + 1}"

    def _read_state(self) -> dict[str, Any] | None:
        """Read and parse the state file.  Returns ``None`` on any error."""
        try:
            raw = self._state_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                return None
            return data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    def _write_state(self, state: dict[str, Any]) -> None:
        """Atomically write the state dict to ``.pipeline_state.json``.

        Strategy: write to a temp file in the same directory, then
        ``os.replace`` to swap it in.  This guarantees that a crash
        mid-write leaves the **previous** valid state intact.
        """
        self._job_dir.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._job_dir),
            suffix=".tmp",
            prefix=".state_",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False, default=str)
            os.replace(tmp_path, str(self._state_file))
        except BaseException:
            # Clean up temp on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # -- Repr ---------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"JobManager(template={self._template_name!r}, "
            f"job_id={self._job_id!r}, "
            f"dir={self._job_dir})"
        )
