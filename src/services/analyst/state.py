"""State that travels between the analyst's nodes. The server keeps none of it (R-26)."""

from __future__ import annotations

from typing import TypedDict

from models.analysis import AffectEstimate, AffectLabels, StyleDecision, UtteranceAnalysisRequest
from models.ips import Deadline


class AnalystState(TypedDict, total=False):
    req: UtteranceAnalysisRequest
    audio: bytes | None
    deadline: Deadline
    prosody: str | None
    explicit_preference: str | None
    explicit_state: str | None
    text_labels: AffectLabels | None
    text_model: str | None
    voice_labels: AffectLabels | None
    voice_model: str | None
    affect: AffectEstimate
    style: StyleDecision
