from __future__ import annotations

"""AutoShorts Phase 3 Audio Engine — Packager
============================================
Strict Python-only payload assembly to prepare identical outputs for
the Manim video rendering hooks. NEVER ask LLMs to structure JSON here.
"""

import copy
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from src.agents.phase3_audio.contracts import AudioSegment, PayloadAssemblyError

logger = logging.getLogger(__name__)


def atomic_write_json(path: Path | str, data: dict[str, Any]) -> None:
    """Safely write a JSON payload atomically.

    Writes to a temp file in the same directory, fsyncs, then replaces the target.
    Ensures temp files are cleaned on failures.
    """
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=str(path_obj.parent), delete=False, encoding="utf-8"
        ) as tmp:
            tmp_name = tmp.name
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path_obj)
    except Exception as e:
        try:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass
        raise PayloadAssemblyError(f"Failed to atomically persist JSON at {path_obj}: {e}") from e


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    """Safely write binary data atomically.

    Writes to a temp file in the same directory, fsyncs, then replaces the target.
    Ensures temp files are cleaned up on failure.
    """
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path_obj.parent), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path_obj)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def update_script_with_audio(
    script_payload: dict[str, Any], audio_segments: list[AudioSegment]
) -> dict[str, Any]:
    """Update Phase 2 script payload with audio paths and physical durations.

    Preserves existing segment fields; only adds audio_relpath/duration_ms/duration_sec
    for tags that exist in audio_segments.
    """
    out = copy.deepcopy(script_payload)
    out_segments = out.get("segments", [])

    audio_map = {seg.tag: seg for seg in audio_segments}

    updated_segs: list[dict[str, Any]] = []
    for s_dict in out_segments:
        tag = s_dict.get("tag")
        s_copy = dict(s_dict)

        audio_data = audio_map.get(tag)
        if audio_data:
            s_copy["audio_relpath"] = audio_data.audio_relpath
            s_copy["duration_ms"] = audio_data.duration_ms
            s_copy["duration_sec"] = audio_data.duration_sec
        else:
            # A missing audio segment produces a corrupt script.json that Phase 4
            # cannot render. Fail hard here rather than silently writing an incomplete payload.
            raise ValueError(
                f"Audio synthesis missing for segment '{tag}'. "
                f"Synthesized tags: {sorted(audio_map.keys())}. "
                "Phase 4 cannot render without complete audio coverage."
            )

        updated_segs.append(s_copy)

    out["segments"] = updated_segs
    return out


def build_job_json(
    job_id: str,
    template_name: str,
    script_relpath: str,
    audio_dir_relpath: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct minimal job.json payload for Phase 4 renderer."""
    payload: dict[str, Any] = {
        "job_id": job_id,
        "template_name": template_name,
        "script_path": script_relpath,
        "audio_dir": audio_dir_relpath,
    }
    if extra:
        payload.update(extra)
    return payload
