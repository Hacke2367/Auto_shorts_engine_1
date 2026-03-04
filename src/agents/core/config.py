"""
AutoShorts — Secure Configuration Management
============================================
Loads top-level API credentials.
Ensures zero hallucination/blind-spots by crashing early if keys are missing.
"""

import os
from pathlib import Path
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ensure we map from the project root's .env file
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class SystemSettings(BaseSettings):
    """Global secure configuration loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    tavily_api_key: SecretStr = Field(
        ...,
        description="API key for Tavily search & extraction.",
        validation_alias="TAVILY_API_KEY",
    )
    gemini_api_key: SecretStr = Field(
        ...,
        description="API key for Google Gemini.",
        validation_alias="GEMINI_API_KEY",
    )
    
    # --- Dynamic Job Settings with Defaults ---
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Google Gemini model identifier to use for extraction.",
        validation_alias="GEMINI_MODEL",
    )
    gemini_rpm_limit: int = Field(
        default=15,
        description="Maximum Requests Per Minute for Gemini API.",
        validation_alias="GEMINI_RPM_LIMIT",
    )
    gemini_temperature: float = Field(
        default=0.1,
        description="Temperature for Gemini extraction (lower is better for JSON).",
        validation_alias="GEMINI_TEMPERATURE",
    )
    api_timeout_seconds: float = Field(
        default=60.0,
        description="Global timeout in seconds for API calls (excluding retry backoff).",
        validation_alias="API_TIMEOUT_SECONDS",
    )

    # --- Authority Domains for SourceAuditing ---
    primary_authority_domains: list[str] = Field(
        default=["bloomberg.com", "un.org", "gov", "wsj.com", "socialblade.com", "youtube.com"],
        description="Domains considered purely authoritative.",
    )
    social_authority_domains: list[str] = Field(
        default=["reddit.com", "twitter.com", "x.com", "tiktok.com", "instagram.com"],
        description="Domains representing social/forum signals.",
    )


# Instantiate globally. Will raise ValidationError immediately if keys are missing.
settings = SystemSettings()
