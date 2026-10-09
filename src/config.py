"""Centralised configuration, read from environment variables / .env.

The only module that reads the environment (rule R-05). Any layer may read the
settings, but only ``integrations/`` uses the credential fields.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"

    # -- Credentials (used only by integrations/) ------------------------------
    gemini_api_key: str = ""
    openai_api_key: str = ""
    # datos.gov.co application token (optional). Validated at startup: a 403
    # drops it and the client continues anonymously (docs/09 section 2).
    datos_gov_app_token: str = ""
    # HMAC key for the anonymous session token (R-28). 32 random bytes.
    session_signing_key: str = ""
    session_token_ttl_hours: int = 2
    # Comma-separated origins allowed by CORS (only needed when web and API live on
    # different origins; with Vercel Services both share one domain).
    allowed_origins: str = "http://localhost:4321"
    # Vercel Services routes /api/* to this service WITH the prefix (docs: "the service
    # receives the original request path"). It is stripped before routing, so the same
    # app answers /health locally and /api/health on Vercel. "" disables it.
    api_path_prefix: str = "/api"
    # In-memory rate limit per session token and per IP (R-28).
    rate_limit_per_minute: int = 120          # per anonymous session
    rate_limit_per_ip_minute: int = 1500      # per IP: evaluators share the venue's public IP

    # -- Dataset (docs/09) --------------------------------------------------
    dataset_base_url: str = "https://www.datos.gov.co"
    dataset_id: str = "s2ru-bqt6"
    # G3 measured 0.8-2.7 s for a cold TLS connect from Colombia: 2 s failed.
    dataset_connect_timeout_s: float = 4.0
    dataset_read_timeout_s: float = 4.0
    dataset_cache_fresh_s: int = 60
    dataset_cache_stale_s: int = 24 * 3600
    tool_deadline_s: float = 6.0  # common foreground deadline (R-25)
    lexicon_path: Path = REPO_ROOT / "data" / "lexicon.json"
    reto01_domain_path: Path = REPO_ROOT / "config" / "domains" / "reto01_ips.yaml"
    style_policy_path: Path = REPO_ROOT / "config" / "style_policy.yaml"

    # -- Voice engines (D-11, verified in G2) --------------------------------
    # VOICE_OPENAI_MODEL: gpt-realtime-2.1 (spoke the acknowledgement on its own in G2)
    # or gpt-realtime (0.9-1.3 s faster in G2, no acknowledgement by itself).
    openai_realtime_model: str = Field(
        default="gpt-realtime-2.1", validation_alias=AliasChoices("VOICE_OPENAI_MODEL", "OPENAI_REALTIME_MODEL"))
    openai_realtime_voice: str = "marin"
    # End-of-speech detection (latency vs cutting off people who pause). Measured with
    # scripts/bench_models.py before changing the defaults (docs/00 section 6).
    realtime_turn_detection: str = "server_vad"   # server_vad | semantic_vad
    realtime_silence_duration_ms: int = 500
    realtime_prefix_padding_ms: int = 300
    # 0.65 (was 0.5): ambient noise was cutting the agent off (team report, 2026-10-09).
    realtime_vad_threshold: float = 0.65
    realtime_vad_eagerness: str = "high"          # semantic_vad only: low | medium | high | auto
    # False: the server does NOT cut the agent on any sound; the browser interrupts only after
    # >= 1 s of continuous user speech (docs/08 section 6). True restores provider barge-in.
    realtime_interrupt_response: bool = False
    realtime_noise_reduction: str = "near_field"  # near_field | far_field | "" (off)
    gemini_start_sensitivity: str = "START_SENSITIVITY_LOW"
    openai_transcribe_model: str = "gpt-4o-mini-transcribe"
    gemini_live_model: str = "gemini-3.8-live"
    gemini_live_voice: str = "Kore"
    realtime_credential_ttl_s: int = 600

    # -- Cloned voice (D-20). Optional: without the key /health only offers
    # the engine voice and /speech/session answers 503 SYNTH_UNAVAILABLE.
    cartesia_api_key: str = ""
    cartesia_voice_id: str = ""
    cartesia_model: str = "sonic-3.6"
    cartesia_version: str = "2026-08-14"
    cartesia_voice_label: str = "Voz clonada del equipo"
    # Team decision 2026-10-09: the cloned voice is the default when it is configured
    # (OpenAI only; Gemini Live rejects text-only output). "engine" turns it off.
    voice_default_mode: str = "cloned"
    speech_token_ttl_s: int = 600

    # -- Analyst profiles (D-10, verified in G3) -----------------------------
    # fast: text 1.1 s p50, audio 1.4-2.2 s p50, schema 3/3. deep: text 1.3 s.
    # OpenAI audio models reject json_schema, so the acoustic branch is Gemini only.
    analyst_fast_model: str = "gemini-3.5-flash-lite"
    analyst_deep_model: str = "gpt-5.4-mini"
    analyst_deadline_s: float = 3.0

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
