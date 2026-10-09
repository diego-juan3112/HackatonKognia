# 05 — Acceptance scenarios and latency measurement

Status: specification only. Product tests and voice benchmarks were not run in
this planning task. Live read-only API research is separately recorded in [09](09_research_and_sources.md).

## Release gate

All P0 scenarios must pass on the public URL with actual providers, one browser
outside the development session, and persistent state. A failed capability is
recorded honestly; a text fallback does not pass the voice requirement.

| ID | Priority | Given / when | Required observable result |
|---|---|---|---|
| A-01 | P0 | New visitor opens HTTPS URL | No local setup, anonymous session, permission prompt after Start, useful error on mic refusal |
| A-02 | P0 | Visitor starts voice | Spanish spoken brief describes IPS data and historical cutoff, suggests 3–5 relevant questions |
| A-03 | P0 | Ask for public IPS in a specified municipality/department | Exact filters executed through source adapter, at most 3 spoken results, visible source |
| A-04 | P0 | Ask for “San José” without location | Clarifies location/site; never silently selects first match |
| A-05 | P0 | Ask total providers | Distinct provider aggregate, not 41,427 capacity rows; 9,320 only for the verified source version |
| A-06 | P0 | Compare Adultos beds in two resolved sites | Same capacity type/cutoff, source quantities and units; null/ambiguous data remains unknown |
| A-07 | P0 | Ask for an absent level/phone | Says field is not recorded; no hallucinated value |
| A-08 | P0 | Ask “¿Hay cama disponible hoy?” or nearest site | Explains missing live availability/geolocation; offers supported directory lookup |
| A-09 | P0 | Correct “Medellín” to “Melgar” | Original preserved, correction visible, old evidence invalidated, new query uses confirmed locality |
| A-10 | P0 | Say “la segunda” after results, then reconnect | Selected entity remains tied to those results; restored state doesn't select another site's index |
| A-11 | P0 | Interrupt while speech is playing | Playback stops, queued/late audio suppressed, new turn answers corrected task |
| A-12 | P0 | Simulate tool timeout or provider 429 using a controlled double | Bounded retry/fallback, visible source/cache status, no loop or duplicated spoken answer |
| A-13 | P0 | User and agent exchange three turns | Live transcript has role, timestamps, partial/final distinction and correction history |
| A-14 | P0 | User says “me estás confundiendo, sé más directo” | Concise repair next turn; sentiment shows an estimate; facts unchanged |
| A-15 | P0 | Execute benchmark protocol below | Actual p50/p95 and sample size published with provider, deployment and failures |
| A-16 | P0 | Primary model fails after a valid source result | One fallback or evidence template reuses context; no fabricated tool result |
| A-17 | P0 | Duplicate request ID, stale event, foreign session | Same turn reused; stale event discarded; foreign data inaccessible |
| A-18 | P0 | Data service unavailable with only partial cache | Explicit unavailable/partial status; no national aggregate from incomplete data |
| A-19 | P1 | Same meaning with colloquial name / ASR error | Lexical/vector candidate improves resolution; uncertain substitution confirmed |
| A-20 | P1 | Two observer providers disagree | One foreground answer; observations cannot overwrite facts or replay tools |

Tests for core data semantics must include repeated provider rows, multiple
site numbers, Mixta nature, missing levels, null quantities and cutoff changes.
Use synthetic fixtures/doubles offline; no real patient data or provider keys.
Full ingestion adds page exhaustion/count/version reconciliation before snapshot
promotion. Do not claim that two sampled pages prove complete ingestion.

## What “ultrafast” means here

These are engineering targets to validate, not promised provider performance.

| Metric | Definition | Target |
|---|---|---|
| Useful first audio | End of user speech to first audible task-relevant answer | Warm p50 ≤ 1.5 s; p95 ≤ 3.0 s |
| Direct-source first audio | Same metric for an uncached source query | Warm p95 ≤ 4.0 s; keep separate from cache hits |
| Interruption stop | Detected user speech to local playback stopped | p95 ≤ 200 ms |
| Visible partial transcript | Captured speech to rendered partial, where supported | p95 ≤ 500 ms |
| Foreground bound | Final transcript to completed/failed/clarifying turn | ≤ 6 s server work budget |

A generic “un momento” is an acknowledgement, not a useful answer. Record
acknowledgement latency separately. Deadline expiry returns a useful error or
clarification and cancels remaining publication; it does not mean source facts
were answered successfully.

Initial warm-turn budget hypothesis: endpoint detection 250 ms + final STT
200 ms + intent 350 ms + source 350 ms + validation/render 50 ms + first TTS
250 ms + playback scheduling 50 ms = 1,500 ms. Stages overlap in streaming
systems, but don't assume overlap until measured. Browser STT may exceed its
budget. Existing Azure TTS measurements concern TTS only, not this total.

## Benchmark protocol

Start with a 10-utterance smoke test for model selection; it is not release
evidence for percentiles. Release benchmark: at least 30 warm task turns,
including direct source queries, cache hits, ambiguous names, corrections and
empty results. Add 5 cold starts and 5 interruption attempts, reporting these
separately. Run the main test with one user and a small 3-session concurrency
check to expose shared-state or quota problems.

Use browser monotonic timings for user-perceived start/end and first playback.
Use server monotonic spans for STT/model/tool/TTS. Do not subtract unsynchronized
browser and server wall clocks. Correlate spans by turn ID.

Record model ID/revision, prompt/tool schema versions, region, transport,
browser, concurrency, cache status, tokens/cost if available, cold/warm and
outcome. Report failures, timeouts and worst cases rather than dropping them
from latency summaries. Include task success/grounding, entity accuracy,
correction success, duplicate execution count and tool schema error rate.

Use reviewed expected answers from actual source queries. An LLM observer may
suggest a mismatch; it does not define correctness. No provider is declared
“faster” or “better at reasoning” from brand reputation.

## SDD completion evidence

Each implementation task links F-ID → C-contract → A-scenario → commit → test
or demonstration evidence. Planned state is not implemented state; passing
doubles establishes contract behavior, not real voice quality. Run the chosen
baseline's existing tests after implementation, and only relevant new cases.
