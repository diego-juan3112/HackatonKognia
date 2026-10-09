"""Analyst graph and style policy (docs/10 section 6). Maps to A-14, A-20, A-21, A-22."""

from __future__ import annotations

import io
import math
import struct
import wave

from config import REPO_ROOT
from models.analysis import AffectHistoryItem, AffectLabels, StyleDecision, UtteranceAnalysisRequest
from services.analyst.graph import AnalystService
from services.analyst.prosody import measure
from services.analyst.style import StylePolicy
from tests.doubles.fake_voice import FakeAffectModel

POLICY = StylePolicy.load(REPO_ROOT / "config" / "style_policy.yaml")
NEG = AffectLabels(sentiment="negative", emotion="enojo", state_hint="frustración", cues=["exclamaciones"])
CALM = AffectLabels(sentiment="neutral", emotion="neutral", state_hint="desconocido", cues=["ritmo pausado"])


def _wav(seconds: float = 2.0, amp: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(amp * math.sin(i / 8))) for i in range(int(16000 * seconds))))
    return buf.getvalue()


def _req(text: str = "¿Cuántas IPS hay?", **kw) -> UtteranceAnalysisRequest:
    return UtteranceAnalysisRequest(turn_id="t1", text=text, **kw)


async def test_text_only_without_consent_never_sends_audio():  # R-26
    fast = FakeAffectModel("fast", NEG, supports_audio=True)
    res = await AnalystService([fast], fast, POLICY).analyze(_req(voice_consent=False), _wav())
    assert res.affect.method == "text" and fast.calls == [("¿Cuántas IPS hay?", False)]


async def test_voice_and_text_disagree_flags_discrepancy():  # A-21
    text = FakeAffectModel("fast", CALM)
    voice = FakeAffectModel("voice", NEG, supports_audio=True)
    res = await AnalystService([text], voice, POLICY).analyze(_req(voice_consent=True), _wav())
    a = res.affect
    assert a.method == "fused" and a.discrepancy is True
    assert a.text_estimate == CALM and a.voice_estimate == NEG and a.sentiment == "negative"
    assert a.confidence is None  # never an invented percentage


async def test_fallback_to_deep_profile_when_fast_fails():  # D-10 chain
    fast = FakeAffectModel("fast", fail=True)
    deep = FakeAffectModel("deep", NEG)
    res = await AnalystService([fast, deep], None, POLICY).analyze(_req(), None)
    assert res.affect.text_estimate == NEG and res.affect.state_hint == "frustración"


async def test_everything_fails_or_times_out_gives_uncertain():
    slow = FakeAffectModel("fast", NEG, delay_s=1.0)
    res = await AnalystService([slow], None, POLICY, deadline_s=0.3).analyze(_req(), None)
    assert res.affect.sentiment == "uncertain" and res.affect.emotion == "incierta" and res.ms < 900


async def test_short_audio_is_text_only():
    voice = FakeAffectModel("voice", NEG, supports_audio=True)
    res = await AnalystService([FakeAffectModel("fast", CALM)], voice, POLICY).analyze(
        _req(voice_consent=True), _wav(0.5))
    assert res.affect.method == "text" and voice.calls == []


async def test_explicit_preference_applies_immediately_and_persists():  # A-14, A-22
    svc = AnalystService([FakeAffectModel("fast", CALM)], None, POLICY)
    first = await svc.analyze(_req("me estás confundiendo, sé más directo", turn_index=3), None)
    assert first.style.style == "directo" and first.style.source == "preference"
    assert first.style.applies_from_turn == 4 and first.affect.state_hint == "confusión"  # explicit beats inference
    later = await svc.analyze(_req("gracias", current_style=first.style, turn_index=5), None)
    assert later.style == first.style


def test_inferred_style_needs_two_consecutive_signals():
    from models.analysis import AffectEstimate

    est = AffectEstimate(turn_id="t", observed_at="x", sentiment="negative", emotion="enojo",
                         state_hint="frustración", method="text")
    one = POLICY.decide(est, explicit_preference=None, history=[], current=None, turn_index=1)
    assert one.style == "neutro"
    hist = [AffectHistoryItem(sentiment="negative", emotion="enojo", state_hint="frustración")]
    two = POLICY.decide(est, explicit_preference=None, history=hist, current=one, turn_index=2)
    assert two.style == "directo" and two.source == "inferred" and "frustrado" in two.reason


def test_neutral_preference_from_ui_is_not_explicit():
    from models.analysis import AffectEstimate

    est = AffectEstimate(turn_id="t", observed_at="x", sentiment="neutral", emotion="neutral",
                         state_hint="desconocido", method="text")
    current = StyleDecision(style="directo", directives=["x"], reason="r", source="inferred")
    out = POLICY.decide(est, explicit_preference="neutral", history=[], current=current, turn_index=1)
    assert out.style == "directo"  # one neutral turn does not undo an inferred style (decay is 4 turns)


def test_prosody_measures_duration_and_loudness():
    p = measure(_wav(2.0), "uno dos tres cuatro")
    assert p and abs(p.duration_s - 2.0) < 0.01 and p.words_per_second == 2.0 and -30 < p.rms_dbfs < 0
    assert measure(b"not a wav") is None
