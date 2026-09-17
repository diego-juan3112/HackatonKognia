"""The declarative description of a business domain.

This is the seam that keeps AGENTS.md section 3 honest. The generic graph
nodes know *that* there is an intent catalogue and a field schema; they never
know what the intents or fields are. Swapping the toy FAQ domain for the real
challenge domain means writing a new YAML file, not editing a node.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FieldSpec(BaseModel):
    """A piece of data the agent must collect before it can act."""

    name: str
    prompt: str = Field(description="Question to ask the user when this field is missing.")
    required: bool = True


class IntentSpec(BaseModel):
    """One entry of the configurable intent catalogue."""

    name: str
    description: str = Field(description="Used by the classifier to choose this intent.")
    examples: list[str] = Field(default_factory=list)
    required_fields: list[FieldSpec] = Field(default_factory=list)
    escalate: bool = Field(
        default=False,
        description="When true, reaching this intent routes straight to a human.",
    )


class DomainSpec(BaseModel):
    """Everything domain-specific, in one loadable object."""

    name: str
    description: str = ""
    system_prompt: str = ""
    fallback_intent: str = "unknown"
    escalation_message: str = "Voy a pasarte con una persona del equipo."
    max_turns_before_escalation: int = 0
    intents: list[IntentSpec] = Field(default_factory=list)

    def intent(self, name: str | None) -> IntentSpec | None:
        if name is None:
            return None
        return next((i for i in self.intents if i.name == name), None)

    @property
    def intent_names(self) -> list[str]:
        return [i.name for i in self.intents]
