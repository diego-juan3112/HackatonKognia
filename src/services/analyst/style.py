"""Deterministic style policy with smoothing (docs/10 section 6, config/style_policy.yaml).

The explicit preference applies immediately and persists; an inferred style
needs two consecutive signals (it must not oscillate) and decays to neutral
after ``decay_turns`` without signals. No LLM decides the style (R-04).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from models.analysis import AffectEstimate, AffectHistoryItem, StyleDecision
from services.ips.normalize import norm

_PREF_TO_STYLE = {"concise": "directo", "warm": "calido", "explain": "didactico"}


@dataclass
class StylePolicy:
    styles: dict[str, list[str]]
    rules: list[dict[str, Any]]
    min_signals: int
    decay_turns: int
    explicit_patterns: dict[str, list[str]]
    explicit_state: dict[str, list[str]]

    @classmethod
    def load(cls, path: Path) -> StylePolicy:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        smoothing = data.get("smoothing", {})
        return cls(
            styles={k: v.get("directives", []) for k, v in data["styles"].items()},
            rules=data["rules"],
            min_signals=int(smoothing.get("min_consecutive_signals", 2)),
            decay_turns=int(smoothing.get("decay_turns", 4)),
            explicit_patterns=data.get("explicit_patterns", {}),
            explicit_state=data.get("explicit_state", {}),
        )

    # -- explicit signals in the utterance ------------------------------------

    def detect_preference(self, text: str) -> str | None:
        n = norm(text)
        for pref, patterns in self.explicit_patterns.items():
            if any(p in n for p in patterns):
                return pref
        return None

    def detect_state(self, text: str) -> str | None:
        n = norm(text)
        for hint, patterns in self.explicit_state.items():
            if any(norm(p) in n for p in patterns):
                return hint
        return None

    # -- rules -------------------------------------------------------------------

    def _match(self, labels: dict[str, Any]) -> tuple[str, str]:
        for rule in self.rules:
            if "default" in rule:
                return rule["default"], rule.get("reason", "")
            when = rule["when"]
            if "explicit_preference" in when:
                continue  # handled before inference
            if all(labels.get(k) == v for k, v in when.items()):
                return rule["style"], rule.get("reason", "")
        return "neutro", ""

    def inferred_for(self, item: AffectHistoryItem | AffectEstimate) -> str:
        if isinstance(item, AffectHistoryItem) and item.inferred_style:
            return item.inferred_style
        return self._match({"sentiment": item.sentiment, "emotion": item.emotion,
                            "state_hint": item.state_hint})[0]

    def _decision(self, style: str, reason: str, source: str, turn_index: int) -> StyleDecision:
        return StyleDecision(style=style, directives=self.styles.get(style, []), reason=reason,  # type: ignore[arg-type]
                             source=source, applies_from_turn=turn_index + 1)  # type: ignore[arg-type]

    def decide(self, affect: AffectEstimate, *, explicit_preference: str | None,
               history: list[AffectHistoryItem], current: StyleDecision | None, turn_index: int) -> StyleDecision:
        # 1) An explicit preference wins and applies from the next turn.
        if explicit_preference in _PREF_TO_STYLE:
            style = _PREF_TO_STYLE[explicit_preference]
            reason = next((r.get("reason", "") for r in self.rules
                           if r.get("when", {}).get("explicit_preference") == explicit_preference), "")
            if current and current.source == "preference" and current.style == style:
                return current
            return self._decision(style, reason, "preference", turn_index)
        # 2) A previous explicit preference persists until the user changes it.
        if current and current.source == "preference":
            return current
        # 3) Inference with smoothing: two consecutive signals to change.
        candidate, reason = self._match({"sentiment": affect.sentiment, "emotion": affect.emotion,
                                         "state_hint": affect.state_hint})
        current_style = current.style if current else "neutro"
        if candidate == current_style:
            return current or self._decision("neutro", reason, "inferred", turn_index)
        previous = [self.inferred_for(h) for h in history]
        if candidate == "neutro":
            recent = previous[-(self.decay_turns - 1):] if self.decay_turns > 1 else []
            if len(recent) >= self.decay_turns - 1 and all(p == "neutro" for p in recent):
                return self._decision("neutro", reason, "inferred", turn_index)
            return current or self._decision("neutro", reason, "inferred", turn_index)
        streak = 1
        for p in reversed(previous):
            if p != candidate:
                break
            streak += 1
        if streak >= self.min_signals:
            return self._decision(candidate, reason, "inferred", turn_index)
        return current or self._decision("neutro", "Una sola señal: aún no cambio el estilo", "inferred", turn_index)
