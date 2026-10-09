"""Contract of the IPS tools and the evidence envelope (docs/09 sections 4-5, D-13).

The model sends JSON matching these schemas -- never SoQL (R-23). Unknown fields
are rejected (``extra="forbid"``). Every figure the agent may say comes from an
``ToolEnvelope`` whose ``evidence`` records the live query (R-22).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1"

ToolName = Literal["search_ips", "get_ips_details", "aggregate_ips", "compare_ips", "correct_context"]
TOOL_NAMES: tuple[str, ...] = ("search_ips", "get_ips_details", "aggregate_ips", "compare_ips", "correct_context")

Nature = Literal["Pública", "Privada", "Mixta"]
Level = Literal[1, 2, 3]
Status = Literal["ok", "empty", "ambiguous", "unavailable", "invalid"]
CacheStatus = Literal["live", "fresh", "stale"]
Metric = Literal["provider_count", "site_count", "capacity_sum"]
GroupBy = Literal["department", "municipality", "nature", "level"]

SITE_KEY_PATTERN = r"^[0-9A-Za-z]+:[0-9A-Za-z]+:[0-9A-Za-z]+$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Tool arguments (what the voice engine sends)
# ---------------------------------------------------------------------------


class SearchIpsArgs(_Strict):
    department: str | None = None
    municipality: str | None = None
    name: str | None = None
    nature: Nature | None = None
    level: Level | None = None
    limit: int = Field(default=5, ge=1, le=20)
    cursor: str | None = None


class GetIpsDetailsArgs(_Strict):
    site_key: str = Field(pattern=SITE_KEY_PATTERN)
    capacity_group: str | None = None
    capacity_type: str | None = None
    include_contact: bool = False


class AggregateFilters(_Strict):
    department: str | None = None
    municipality: str | None = None
    name: str | None = None
    nature: Nature | None = None
    level: Level | None = None
    capacity_group: str | None = None
    capacity_type: str | None = None


class AggregateIpsArgs(_Strict):
    metric: Metric
    filters: AggregateFilters = Field(default_factory=AggregateFilters)
    group_by: GroupBy | None = None
    order: Literal["desc", "asc"] = "desc"
    top_n: int | None = Field(default=None, ge=1, le=10)


class CompareIpsArgs(_Strict):
    site_keys: list[str] = Field(min_length=2, max_length=3)
    capacity_group: str
    capacity_type: str | None = None


class CorrectContextArgs(_Strict):
    # Optional (eval 2026-10-09): the engine never knows these internal ids and asked the
    # user for them. When absent they come from the canonical context the browser sends.
    target_turn_id: str | None = None
    expected_state_version: int | None = Field(default=None, ge=0)
    field: Literal["department", "municipality", "name", "nature", "level", "site_key"]
    value: str = Field(min_length=1, max_length=200)


TOOL_ARGS: dict[str, type[BaseModel]] = {
    "search_ips": SearchIpsArgs,
    "get_ips_details": GetIpsDetailsArgs,
    "aggregate_ips": AggregateIpsArgs,
    "compare_ips": CompareIpsArgs,
    "correct_context": CorrectContextArgs,
}


# ---------------------------------------------------------------------------
# Request: canonical state travels with every call (docs/10 section 4)
# ---------------------------------------------------------------------------


class CanonicalContext(BaseModel):
    """The subset of the browser's canonical state the backend reads.

    The browser owns the full object; unknown fields are ignored, not rejected.
    """

    model_config = ConfigDict(extra="ignore")

    conversation_id: str | None = None
    turn_id: str | None = None
    state_version: int = Field(default=0, ge=0)
    confirmed_filters: dict[str, Any] = Field(default_factory=dict)
    selected_site_keys: list[str] = Field(default_factory=list)
    bypass_cache: bool = False  # "Reconsultar" and the first query of a session


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: str = Field(min_length=1, max_length=128)
    turn_id: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    context: CanonicalContext = Field(default_factory=CanonicalContext)
    # "Reconsultar" / first query of a session (docs/09 section 6). The web client
    # sends it top-level (web/src/voice/api.ts); context.bypass_cache also works.
    force_live: bool = False

    @property
    def bypass_cache(self) -> bool:
        return self.force_live or self.context.bypass_cache


# ---------------------------------------------------------------------------
# Result: the evidence envelope (C-EVIDENCE)
# ---------------------------------------------------------------------------


class Trace(BaseModel):
    engine: str = "soda3"
    soql: str | None = None
    ms: int = 0
    rows: int = 0
    cache_status: CacheStatus | None = None


class Evidence(BaseModel):
    dataset_id: str
    source_url: str
    query_fingerprint: str | None = None
    cutoff_raw: str | None = None
    fetched_at: str | None = None
    cache_status: CacheStatus | None = None
    complete: bool = True
    unit: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ToolError(BaseModel):
    code: str
    message: str
    hint: str | None = None
    retryable: bool = False


class ToolEnvelope(BaseModel):
    schema_version: str = SCHEMA_VERSION
    tool_call_id: str
    turn_id: str | None = None
    state_version: int = 0
    status: Status
    data: dict[str, Any] = Field(default_factory=dict)
    # Always present, even for invalid/ambiguous answers: the client keys its
    # evidence store by evidence.query_fingerprint.
    evidence: Evidence
    # One object, as docs/09 section 5 shows; tools with two queries combine them
    # here (soql joined, ms of the slowest, rows summed) and list each in `traces`.
    trace: Trace
    traces: list[Trace] = Field(default_factory=list)
    error: ToolError | None = None
    next_cursor: str | None = None
    context_patch: dict[str, Any] = Field(default_factory=dict)
    # Grounded text the engine receives as the function output (services/ips/for_model.py).
    for_model: str = ""


# ---------------------------------------------------------------------------
# What the dataset port returns (the adapter only executes and measures)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryResult:
    rows: list[dict[str, Any]]
    soql: str
    ms: int
    cache_status: CacheStatus
    fetched_at: str
    engine: str = "soda3"


class DatasetUnavailable(Exception):
    """The source could not answer within the deadline (timeout, 5xx, 429...)."""

    def __init__(self, code: str, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after_s = retry_after_s


@dataclass
class Deadline:
    """A monotonic foreground budget shared by every attempt of a turn (R-25)."""

    seconds: float
    started: float = field(default_factory=time.monotonic)

    def remaining(self) -> float:
        return max(0.0, self.seconds - (time.monotonic() - self.started))

    def expired(self) -> bool:
        return self.remaining() <= 0.0
