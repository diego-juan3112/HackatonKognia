"""The analyst graph and the ``AnalystPort`` implementation.

    prepare -> { text_affect || acoustic_affect } -> fuse -> style_policy -> END

The LLM only produces labels inside two nodes; every transition, the fusion
and the style are fixed code (R-04). It runs beside the answer, never in front
of it (R-24), within a 3 s deadline; what fails becomes ``uncertain``.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from langgraph.graph import END, START, StateGraph

from models.analysis import AnalysisResult, UtteranceAnalysisRequest
from models.ips import Deadline
from models.ports import AffectModelPort
from services.analyst.nodes.acoustic_affect import make_acoustic_affect
from services.analyst.nodes.fuse import fuse
from services.analyst.nodes.prepare import make_prepare
from services.analyst.nodes.style_policy import make_style_policy
from services.analyst.nodes.text_affect import make_text_affect
from services.analyst.state import AnalystState
from services.analyst.style import StylePolicy


def build_analyst_graph(text_chain: Sequence[AffectModelPort], voice_model: AffectModelPort | None,
                        policy: StylePolicy):
    g = StateGraph(AnalystState)
    g.add_node("prepare", make_prepare(policy))
    g.add_node("text_affect", make_text_affect(text_chain))
    g.add_node("acoustic_affect", make_acoustic_affect(voice_model))
    g.add_node("fuse", fuse)
    g.add_node("style_policy", make_style_policy(policy))
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "text_affect")
    g.add_edge("prepare", "acoustic_affect")
    g.add_edge(["text_affect", "acoustic_affect"], "fuse")
    g.add_edge("fuse", "style_policy")
    g.add_edge("style_policy", END)
    return g.compile()


class AnalystService:
    def __init__(self, text_chain: Sequence[AffectModelPort], voice_model: AffectModelPort | None,
                 policy: StylePolicy, *, deadline_s: float = 3.0) -> None:
        self._graph = build_analyst_graph(text_chain, voice_model, policy)
        self._deadline_s = deadline_s

    async def analyze(self, req: UtteranceAnalysisRequest, audio_wav: bytes | None) -> AnalysisResult:
        t0 = time.perf_counter()
        out = await self._graph.ainvoke({"req": req, "audio": audio_wav, "deadline": Deadline(self._deadline_s)})
        return AnalysisResult(affect=out["affect"], style=out["style"], ms=int((time.perf_counter() - t0) * 1000))
