"""Composition root of the Reto 01 voice app.

Like ``api/dependencies.py`` for the generic base, this is the one module in
``api/`` allowed to import ``integrations/`` (R-01): its job is to assemble the
services with their adapters. Tests build a container from doubles instead.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from config import Settings
from models.ports import AnalystPort, DatasetPort, FeedbackPort
from services.analyst.graph import AnalystService
from services.analyst.style import StylePolicy
from services.ips.brief import BriefService
from services.ips.lexicon import Lexicon
from services.ips.tools import IpsToolService
from services.realtime_service import RealtimeService, load_instructions
from services.session_service import RateLimiter, SessionService

log = logging.getLogger(__name__)


@dataclass
class VoiceContainer:
    sessions: SessionService
    limiter: RateLimiter
    tools: IpsToolService
    brief: BriefService
    realtime: RealtimeService
    analyst: AnalystPort
    feedback: FeedbackPort
    dataset: DatasetPort
    info: dict[str, Any] = field(default_factory=dict)
    ip_limiter: RateLimiter | None = None
    closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def aclose(self) -> None:
        for close in self.closers:
            try:
                await close()
            except Exception:  # noqa: BLE001
                log.exception("error while closing an adapter")


def build_container(s: Settings) -> VoiceContainer:
    from integrations.datasets.socrata_client import SocrataClient
    from integrations.feedback.log_feedback import LogFeedback
    from integrations.llm.affect_models import GeminiAffectModel, OpenAIAffectModel
    from integrations.realtime.cartesia_session import CartesiaSpeechSession
    from integrations.realtime.gemini_session import GeminiLiveSession
    from integrations.realtime.openai_session import OpenAIRealtimeSession

    source_url = f"{s.dataset_base_url}/resource/{s.dataset_id}.json"
    dataset = SocrataClient(
        base_url=s.dataset_base_url, dataset_id=s.dataset_id, app_token=s.datos_gov_app_token,
        connect_timeout_s=s.dataset_connect_timeout_s, read_timeout_s=s.dataset_read_timeout_s,
        cache_fresh_s=s.dataset_cache_fresh_s, cache_stale_s=s.dataset_cache_stale_s,
    )
    lexicon = Lexicon.load(s.lexicon_path)
    instructions, version = load_instructions(s.reto01_domain_path)

    engines = {}
    if s.realtime_turn_detection == "semantic_vad":
        turn_detection = {"type": "semantic_vad", "eagerness": s.realtime_vad_eagerness}
    else:
        turn_detection = {"type": "server_vad", "threshold": s.realtime_vad_threshold,
                          "prefix_padding_ms": s.realtime_prefix_padding_ms,
                          "silence_duration_ms": s.realtime_silence_duration_ms}
    if s.openai_api_key:
        engines["openai"] = OpenAIRealtimeSession(
            api_key=s.openai_api_key, model=s.openai_realtime_model, voice=s.openai_realtime_voice,
            transcribe_model=s.openai_transcribe_model, ttl_s=s.realtime_credential_ttl_s,
            turn_detection=turn_detection)
    if s.gemini_api_key:
        engines["gemini"] = GeminiLiveSession(api_key=s.gemini_api_key, model=s.gemini_live_model,
                                              voice=s.gemini_live_voice,
                                              silence_duration_ms=s.realtime_silence_duration_ms,
                                              prefix_padding_ms=s.realtime_prefix_padding_ms)
    speech = CartesiaSpeechSession(api_key=s.cartesia_api_key, voice_id=s.cartesia_voice_id,
                                   model=s.cartesia_model, version=s.cartesia_version,
                                   voice_label=s.cartesia_voice_label, ttl_s=s.speech_token_ttl_s)

    fast = GeminiAffectModel(api_key=s.gemini_api_key, model=s.analyst_fast_model) if s.gemini_api_key else None
    deep = OpenAIAffectModel(api_key=s.openai_api_key, model=s.analyst_deep_model) if s.openai_api_key else None
    chain = [m for m in (fast, deep) if m is not None]
    analyst = AnalystService(chain, fast, StylePolicy.load(s.style_policy_path), deadline_s=s.analyst_deadline_s)

    closers: list[Callable[[], Awaitable[None]]] = [dataset.aclose]
    closers += [m.aclose for m in chain]
    return VoiceContainer(
        sessions=SessionService(s.session_signing_key, s.session_token_ttl_hours),
        limiter=RateLimiter(s.rate_limit_per_minute),
        ip_limiter=RateLimiter(s.rate_limit_per_ip_minute),
        tools=IpsToolService(dataset, lexicon, dataset_id=s.dataset_id, source_url=source_url,
                             cursor_key=s.session_signing_key.encode(), deadline_s=s.tool_deadline_s),
        brief=BriefService(dataset, source_url=source_url, cutoff_raw=lexicon.cutoff_raw),
        realtime=RealtimeService(engines, speech, instructions=instructions, instructions_version=version,
                                 speech_configured=speech.configured, default_voice_mode=s.voice_default_mode),
        analyst=analyst,
        feedback=LogFeedback(),
        dataset=dataset,
        info={
            "llm_profiles": {"fast": {"provider": "gemini", "model": s.analyst_fast_model, "configured": bool(fast)},
                             "deep": {"provider": "openai", "model": s.analyst_deep_model, "configured": bool(deep)}},
            "dataset": {"id": s.dataset_id, "token": bool(s.datos_gov_app_token)},
            "lexicon": {"built_at": lexicon.built_at, "cutoff_raw": lexicon.cutoff_raw},
        },
        closers=closers,
    )
