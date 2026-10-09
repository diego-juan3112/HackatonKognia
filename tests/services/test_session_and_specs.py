"""Signed session (R-28) and tool declarations in lock-step with the validated models (R-23)."""

from __future__ import annotations

import time

import pytest

from models.ips import TOOL_ARGS, TOOL_NAMES
from services.ips.tool_specs import TOOL_SPECS
from services.session_service import InvalidSession, RateLimiter, SessionService


def test_token_roundtrip_and_tampering():
    s = SessionService("x" * 32)
    token, expires = s.issue("es-CO")
    assert s.verify(token).locale == "es-CO" and expires.endswith("Z")
    claims, sig = token.split(".")
    with pytest.raises(InvalidSession):
        s.verify(claims + "." + sig[:-2] + "AA")
    with pytest.raises(InvalidSession):
        SessionService("y" * 32).verify(token)  # another key


def test_expired_token_is_rejected(monkeypatch):
    s = SessionService("x" * 32, ttl_hours=1)
    token, _ = s.issue()
    monkeypatch.setattr(time, "time", lambda: 10**12)
    with pytest.raises(InvalidSession):
        s.verify(token)


def test_missing_signing_key_fails_fast():
    with pytest.raises(ValueError):
        SessionService("")


def test_rate_limiter_window():
    rl = RateLimiter(2)
    assert rl.check("k") is None and rl.check("k") is None and rl.check("k") >= 1


def test_tool_specs_match_the_validated_models():
    assert [t.name for t in TOOL_SPECS] == list(TOOL_NAMES)
    for spec in TOOL_SPECS:
        declared = set(spec.parameters["properties"])
        model_fields = set(TOOL_ARGS[spec.name].model_fields)
        assert declared == model_fields, spec.name
        assert set(spec.parameters.get("required", [])) == {
            n for n, f in TOOL_ARGS[spec.name].model_fields.items() if f.is_required()}, spec.name
        text = str(spec.parameters)
        assert "anyOf" not in text and "$defs" not in text  # Gemini function declarations reject them
        _assert_string_enums(spec.parameters, spec.name)


def _assert_string_enums(schema: object, where: str) -> None:
    """Gemini only accepts string enums (smoke 2026-10-09: 400 on an integer enum)."""
    if isinstance(schema, dict):
        if "enum" in schema:
            assert all(isinstance(v, str) for v in schema["enum"]), where
        for v in schema.values():
            _assert_string_enums(v, where)
    elif isinstance(schema, list):
        for v in schema:
            _assert_string_enums(v, where)
