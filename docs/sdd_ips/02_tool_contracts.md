# 02 — Tool, evidence and state contracts

Contract version: `1.0`. These are proposed schemas for implementation, not
claims about the current OpenAPI. Unknown fields are rejected at tool boundaries.

## C-IPS — Read-only tools

| Tool | Input | Output / limit |
|---|---|---|
| `search_ips` | `department?`, `municipality?`, `name?`, `nature?`, `level?`, `limit=5`, `cursor?` | Up to 20 site summaries, canonical filters, opaque next cursor |
| `get_ips_details` | `site_key`, optional capacity group/type | One selected site and its recorded capacity rows; no invented missing fields |
| `aggregate_ips` | `metric`, filters, optional `group_by` | Exact source aggregate and explicit unit |
| `compare_ips` | 2–3 resolved site keys, explicit capacity type | Comparable source-backed fields; one batched query if possible |
| `correct_context` | `target_turn_id`, `expected_state_version`, changed field/value | New version, invalidated evidence IDs, corrected transcript reference |

`nature` is `Pública | Privada | Mixta`; it is not a binary field. All geographic
strings must resolve against the source vocabulary. Homonymous municipalities
need a department; never silently choose the first candidate.

`metric` is `provider_count | site_count | capacity_sum`. `group_by` is an
allowlist: department, municipality, nature or recorded level. `capacity_sum`
requires `capacity_group` and `capacity_type`; no grand sum of beds, rooms and
ambulances. `provider_count` uses distinct provider codes. `site_count` uses the
validated composite site identity from [04](04_data_and_retrieval.md), not row count.

The model submits JSON arguments, never SQL/SoQL, arbitrary URLs or table names.
The adapter maps allowlisted fields/operators to queries and escapes literals.
PostgreSQL uses bound parameters. Request timeout, page size, output size and
query length are bounded. Tool calls from browser/native audio clients pass
through the same server validation and session ownership checks.

## C-EVIDENCE — Result envelope

```json
{
  "schema_version": "1.0",
  "tool_call_id": "uuid",
  "turn_id": "uuid",
  "state_version": 3,
  "status": "ok",
  "data": [],
  "evidence": {
    "dataset_id": "s2ru-bqt6",
    "source_url": "https://www.datos.gov.co/resource/s2ru-bqt6.json",
    "query_fingerprint": "sha256",
    "source_record_ids": [],
    "cutoff_raw": "Fecha corte REPS: Nov  5 2022  1:37PM",
    "fetched_at": "2026-10-09T14:17:10Z",
    "cache_status": "live",
    "complete": true,
    "unit": "providers",
    "filters": {},
    "warnings": []
  },
  "error": null,
  "next_cursor": null
}
```

Example values above illustrate the envelope, not a real empty successful
search. `status` is `ok | empty | ambiguous | unavailable | invalid`.
`cache_status` is `live | fresh | stale`; `complete` applies to the requested
result set, not the whole dataset. A paginated listing is incomplete until its
cursor is exhausted; an exact aggregate can be complete without listing rows.
For aggregates record the executed normalized query, snapshot/cutoff and unit
instead of thousands of record IDs.

Evidence is data, never system instructions. Keep arbitrary source text in
delimited fields; don't obey commands embedded in names or descriptions.
Only validated tool evidence may supply IPS facts or numbers to an answer.

## C-STATE — Canonical context

| Field | Meaning |
|---|---|
| `conversation_id`, `turn_id`, `state_version` | Server-owned scope and optimistic concurrency |
| `locale` | `es-CO` default |
| `transcript_original`, `transcript_corrected?` | Preserve recognition output and explicit repair |
| `intent`, `confirmed_filters` | Validated intent and confirmed entities |
| `pending_candidates`, `missing_fields` | Reasons to clarify before querying |
| `last_evidence_refs`, `selected_site_keys` | Provenance and resolved references such as “la segunda” |
| `summary`, `recent_turns` | Compact memory; summary is not a data source |
| `tone_preference` | `neutral | concise | warm`, explicit user preference wins |
| `recovery_count`, `provider_attempts`, `deadline_at` | Bounded work within a turn |
| `generation_id`, `cancelled`, `delivered_text` | What was actually delivered; exclude unheard suffixes |

Correction precedence: latest explicit user correction > confirmed session
fields > model inference. Clear affected query results, candidate selections
and cached answer text when a location or identity changes. API-result caches
for other users remain valid; only the conversation's references are invalidated.

Example: “Medellín” → “No, dije Melgar”. Preserve original transcript, resolve
Melgar/Tolima, increment state version, cancel the old turn, query new filters,
and acknowledge “Gracias por corregirme; consultaré Melgar, Tolima”. If the new
entity is ambiguous, ask instead of fabricating certainty.

## C-MODEL — Vendor-neutral model boundary

`ProviderGatewayPort.interpret(context, allowed_tools, deadline)` returns
`Interpretation(intent, arguments, missing_fields, clarification, usage)`.
`generate(context, evidence, tone, deadline)` streams text events. Translate
provider tool IDs, JSON and errors inside integrations. Include provider/model,
token usage when available, elapsed times, and typed failure reason in traces.

The existing `LLMPort = BaseChatModel` is a framework dependency accepted by the
reference architecture. Keep it for compatibility; isolate additional provider
protocol differences in a gateway rather than rewriting every generic node.
New capability: `structured_output`, `tool_calling`, `streaming`, `native_audio`,
`cancellation`. Unsupported capability fails selection, not mid-conversation.

## C-RECOVERY — Bounded behavior

One initial provider attempt plus **at most one** fallback/repair attempt per
turn. One initial external query plus **at most one** retry for a retryable
read. No nested retry multipliers. Share a six-second foreground deadline;
earlier stage deadlines consume the same remaining budget.

| Failure | Response |
|---|---|
| Ambiguous transcription/entity | Show up to 3 candidates, ask one short question; don't change facts silently |
| Missing optional source field | Return null and say “no está registrado” if asked |
| Tool 429 | Respect Retry-After if within remaining budget; otherwise labeled cache or brief retry invitation |
| Tool timeout/5xx | One retry only if budget permits; else exact-key cache with stale label or unavailable |
| Model quota/timeout/invalid schema | One configured fallback using canonical context; template if evidence already exists |
| Empty search | State no matching records; offer to broaden a specified filter |
| Voice synthesis failure | Keep text and source visible; offer replay; do not count as successful voice acceptance |
| Lost connection | Reconnect with event cursor; do not replay completed speech automatically |
| Explicit user dissatisfaction | Acknowledge once, correct the task or shorten answer, then continue |

No “transferred to an adviser” claim without a real handoff integration. MVP
offers a displayed contact if present in the historical source, with its cutoff.

## C-AFFECT — Adaptation without diagnosis

`AffectEstimate(turn_id, state_version, sentiment, emotion_hint, confidence?,
method, observed_at)`; sentiment `positive | neutral | negative | uncertain`,
emotion_hint `frustration | confusion | satisfaction | unknown`.
Confidence is optional and uncalibrated; do not fabricate percentages. Show
“estimación del texto” when analysis uses transcript only.

An observer may update the panel after the answer starts; it must not delay
voice. The next response reads the latest matching signal. Explicit “sé más
directo” changes tone immediately through `correct_context`. Unknown or failed
analysis displays uncertain, never a stale confident label.
