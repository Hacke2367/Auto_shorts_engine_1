# src/sync/job_config.py
# Pydantic v2 schema for job.json.
# Used by main.py to validate job config at load time — surfaces missing
# or mistyped fields immediately instead of crashing deep inside the pipeline.
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AudioSegment(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    path: str


class AudioConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    segments: List[AudioSegment]
    order: List[str]

    @model_validator(mode="after")
    def _validate_alignment(self) -> "AudioConfig":
        """segments[].name and order must reference the exact same set of names."""
        seg_names = {s.name for s in self.segments}
        order_set = set(self.order)
        if seg_names != order_set:
            parts = []
            extra_in_segs = seg_names - order_set
            extra_in_order = order_set - seg_names
            if extra_in_segs:
                parts.append(f"in segments but not in order: {sorted(extra_in_segs)}")
            if extra_in_order:
                parts.append(f"in order but not in segments: {sorted(extra_in_order)}")
            raise ValueError(
                f"audio.segments and audio.order are misaligned — {'; '.join(parts)}"
            )
        return self


class GainsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    gain_voice: float = Field(default=1.0, description="Linear amplitude multiplier for voice track")
    gain_sfx: float = Field(default=1.0, description="Linear amplitude multiplier for SFX track")
    gain_bgm_db: float = Field(default=-20.0, description="BGM gain in dB (negative = quieter)")


class SfxConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    gain: float = 1.0


class BgmSegmentConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    path: str = ""
    gain_db: float = 0.0
    duck: bool = True
    duck_amount: Literal["strong", "moderate", "light"] = "strong"


class BgmConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    mode: str = "per_segment"
    library_dir: str = "audio/bgm"
    default: Optional[BgmSegmentConfig] = None
    segments: Dict[str, Any] = Field(default_factory=dict)
    crossfade: float = 0.25


class MixConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    preset: str = "punchy"
    duck_sfx: bool = False


class CaptionsStyleConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    preset: str = "modern_clean"
    safe_margin_px: int = 80
    max_lines: int = 2


class CaptionsRenderConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    format: str = "ass"
    burn_in: bool = False
    style: CaptionsStyleConfig = Field(default_factory=CaptionsStyleConfig)
    tracks: List[Dict[str, Any]] = Field(default_factory=list)


class CaptionsScriptConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    path: str = "script/script.json"
    source_lang: str = "en"
    target_langs: List[str] = Field(default_factory=lambda: ["en"])


class CaptionsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    script: CaptionsScriptConfig = Field(default_factory=CaptionsScriptConfig)
    render: CaptionsRenderConfig = Field(default_factory=CaptionsRenderConfig)


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    final_mp4: str = "output/final.mp4"
    subtitles_ass: str = "output/subtitles.ass"
    final_captioned_mp4: str = "output/final_captioned.mp4"


class PathsConfig(BaseModel):
    """Dynamic directory overrides. All values are relative to job_dir.
    Defaults reproduce the original hardcoded layout so existing jobs need no changes."""
    model_config = ConfigDict(extra="allow")
    output_dir: str = "output"
    media_dir: str = "media"
    sfx_marks: str = "output/sfx_marks.json"


class JobConfig(BaseModel):
    """Full job.json schema. extra='allow' keeps forward-compatibility with new keys."""
    model_config = ConfigDict(extra="allow")

    # Required fields — validation fails fast if these are missing
    template_id: str = Field(min_length=1)
    audio: AudioConfig

    # Optional with sensible defaults
    job_id: str = ""
    data_csv: str = "data/data.csv"
    video: Dict[str, Any] = Field(default_factory=lambda: {"w": 1080, "h": 1920})
    timeline: Dict[str, float] = Field(default_factory=dict)
    gains: GainsConfig = Field(default_factory=GainsConfig)
    sfx: SfxConfig = Field(default_factory=SfxConfig)
    bgm: BgmConfig = Field(default_factory=BgmConfig)
    mix: MixConfig = Field(default_factory=MixConfig)
    captions: CaptionsConfig = Field(default_factory=CaptionsConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    @model_validator(mode="after")
    def _validate_timeline_coverage(self) -> "JobConfig":
        """If timeline is explicitly provided, every segment in audio.order must have an entry.
        An empty timeline is valid — timeline_resolver falls back to ffprobe in that case."""
        if self.timeline:
            missing = set(self.audio.order) - set(self.timeline.keys())
            if missing:
                raise ValueError(
                    f"timeline is missing entries for segments: {sorted(missing)}. "
                    "Add the missing keys or remove the timeline block entirely "
                    "to use ffprobe durations."
                )
        return self
