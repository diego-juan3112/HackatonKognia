"""Feedback sink (docs/10 section 5): structured log line, no database.

LangSmith is the planned destination (docs/10 section 8); without a run id per
turn there is nothing to attach feedback to yet, so this adapter logs a
structured event that the LangSmith adapter can replace without touching
services/ (R-03). No audio and no personal data are logged (R-26).
"""

from __future__ import annotations

import json
import logging

from models.voice import FeedbackEvent

log = logging.getLogger("kognia.feedback")


class LogFeedback:
    async def record(self, event: FeedbackEvent) -> None:
        payload = event.model_dump()
        if payload.get("text"):
            payload["text"] = payload["text"][:200]
        log.info("feedback %s", json.dumps(payload, ensure_ascii=False))
