"""fuse: deterministic fusion of the text and voice estimates (docs/10 section 6, "Fusión").

- both agree -> that label; they disagree -> ``fused`` + ``discrepancy`` and both are shown;
- only one available -> that one; none -> ``uncertain`` (never an old label);
- an explicit declaration ("estoy frustrado") beats the inference for ``state_hint``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from models.analysis import AffectEstimate, AffectLabels
from services.analyst.state import AnalystState


async def fuse(state: AnalystState) -> dict:
    req = state["req"]
    text, voice = state.get("text_labels"), state.get("voice_labels")
    discrepancy = False
    if text and voice:
        agree = text.sentiment == voice.sentiment and text.emotion == voice.emotion
        if agree:
            lead, method = text, "fused"
        else:
            # On disagreement the voice leads (tone carries what words omit), and the flag is raised.
            lead, method, discrepancy = voice, "fused", True
        cues = list(dict.fromkeys(text.cues + voice.cues))[:6]
    elif text:
        lead, method, cues = text, "text", text.cues
    elif voice:
        lead, method, cues = voice, "voice", voice.cues
    else:
        lead, method, cues = AffectLabels.uncertain(), "text", []
    state_hint = state.get("explicit_state") or lead.state_hint
    affect = AffectEstimate(
        turn_id=req.turn_id, state_version=req.state_version,
        observed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        sentiment=lead.sentiment, emotion=lead.emotion, state_hint=state_hint,  # type: ignore[arg-type]
        method=method, discrepancy=discrepancy,  # type: ignore[arg-type]
        text_estimate=text, voice_estimate=voice, cues=cues, confidence=None,
    )
    return {"affect": affect}
