"""In-memory double of ``DatasetPort`` (R-09). No network.

Tests register answers by a substring of the SoQL; every executed query is
recorded so tests can assert on what the backend *built* (R-23).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from models.ips import DatasetUnavailable, Deadline, QueryResult

Answer = list[dict[str, Any]] | Callable[[str], list[dict[str, Any]]] | Exception


class FakeDataset:
    engine = "soda3"

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.bypass: list[bool] = []
        self._answers: list[tuple[str, Answer]] = []
        self.cache_status = "live"

    def on(self, fragment: str, answer: Answer) -> FakeDataset:
        """Answer queries containing ``fragment`` (first registered match wins)."""
        self._answers.append((fragment, answer))
        return self

    async def query(self, soql: str, *, deadline: Deadline, bypass_cache: bool = False) -> QueryResult:
        self.queries.append(soql)
        self.bypass.append(bypass_cache)
        for fragment, answer in self._answers:
            if fragment in soql:
                if isinstance(answer, Exception):
                    raise answer
                rows = answer(soql) if callable(answer) else answer
                return QueryResult(rows=rows, soql=soql, ms=12, cache_status=self.cache_status,  # type: ignore[arg-type]
                                   fetched_at="2026-10-09T15:00:00Z")
        raise AssertionError(f"FakeDataset has no answer for: {soql}")


def unavailable(code: str = "TIMEOUT") -> DatasetUnavailable:
    return DatasetUnavailable(code, "simulated outage")
