# 03 — Proposed API and voice protocol

## C-API — Application API v1

These endpoints are to be implemented. Existing `/chat` and authentication
routes remain compatibility endpoints until the chosen baseline is integrated.

| Endpoint | Request | Response |
|---|---|---|
| `POST /v1/sessions` | locale; no national ID | 201 opaque session token, expiry, conversation ID, supported voice capabilities |
| `GET /v1/source` | session token | Dataset name, cutoff, measured coverage, 3–5 supported question examples |
| `POST /v1/turns` | conversation ID, client request UUID, expected state version, final transcript | 200 SSE stream; first event supplies turn ID; execute within this request, deduplicate request UUID |
| `GET /v1/turns/{id}/events?after={seq}` | session token | SSE ordered events, replay after cursor |
| `POST /v1/turns/{id}/cancel` | generation ID, last played chunk/offset | 200 cancelled (including repeated cancellation) |
| `POST /v1/turns/{id}/playback` | generation ID, last fully played segment and partial offset | 200 playback receipt, scoped to owning session; advance delivered history |
| `POST /v1/feedback` | target turn, expected version, kind, corrected text or preference | 200 new version; optional new turn ID for factual correction |
| `GET /health/live` | none | Process liveness without paid-provider calls |
| `GET /health/ready` | none | 200 ready or 503; DB, source access state and configured adapter readiness |

Header: `X-Session-Id` carries an unguessable server-generated token. Do not put
session tokens in query strings. Use `fetch` streaming for SSE if custom headers
are needed; native EventSource cannot set them. Resolve all conversation/turn
ownership server-side; a supplied ID is not authorization. Expiry: two hours
for the demo, configurable. Per-session rate and concurrency limits apply.

Use 401 invalid/expired session, 403 foreign conversation, 404 unknown turn,
409 stale state, 422 invalid input, 429 rate limit, 503 unavailable dependency.
Error JSON: `{"error":{"code":"STATE_CONFLICT","message":"...",
"retryable":false},"trace_id":"uuid"}`. Translate validation errors at the
v1 boundary; do not silently change legacy FastAPI 422 semantics.

The POST stream owns foreground execution; do not return 202 and rely on an
untracked background task surviving a serverless request. GET events replays
persisted text/state events. If the original invocation died, mark the turn
interrupted and let an explicit retry resume from its checkpoint. It does not
secretly launch a second graph run.

## C-VOICE — Events

Every event contains `schema_version`, `event_id`, monotonic `seq` per turn,
`conversation_id`, `turn_id`, `state_version`, `generation_id`, `type`,
`server_timestamp` and `payload`. Event IDs are stable on replay.

| Event | Essential payload |
|---|---|
| `transcript.partial` | role=user, text, capture-relative start/end milliseconds, final=false |
| `transcript.final` | utterance ID, role=user, original text, final=true |
| `transcript.corrected` | original utterance ID, corrected text, reason=user/confirmed_entity |
| `tool.started` | call ID, tool name, short user-facing activity |
| `tool.completed` | call ID, status, evidence refs |
| `answer.delta` | role=assistant, text fragment; grounded content only |
| `audio.chunk` | chunk ID, MIME, base64 bytes, sequence, duration if known, correlated text segment |
| `evidence.updated` | source URL, cutoff, exact filters, cached/live/stale label |
| `affect.updated` | C-AFFECT result; may arrive after foreground completion |
| `turn.completed` | answer text, evidence, measured timings, final state version |
| `turn.cancelled` | reason and last delivered text segment |
| `turn.failed` | typed error and allowed recovery action |

Store transcript and evidence before `turn.completed`. Persist optional affect
updates independently, so a serverless invocation ending does not silently lose
them. If no durable task mechanism is ready, include the small affect estimate
in the interpretation JSON and label it appropriately instead of starting an
unreliable background coroutine.

For the initial SSE transport, base64 audio chunks avoid temporary filesystem
URLs and an additional storage service. Account for encoding overhead in
measurements, cap queued audio at two seconds where streaming allows it, and
keep audio bytes out of persistent event replay. Replay only text/state metadata;
an explicit replay action synthesizes again. Binary transport is a later
optimization. The browser acknowledges playback so interrupted generated text
is not mistaken for text the user actually heard.

## Initial voice implementation

Reuse the existing browser recognition path for the first vertical slice; it
produces partial/final transcripts in `es-CO`. Keep microphone capture and
playback in a hydrated Astro island. Start audio only after user interaction.
Use cloud streaming STT when required for browser coverage or robust endpointing;
the public demo must name its supported browsers until that path is verified.

Use Azure Speech through the chosen adapter for the first audible response,
based on prior project measurements. Keep a warm reusable synthesizer per
controlled session/pool; don't create a connection for every sentence. Native
SDK dependencies must pass the deployment gate. If streaming chunks are not
ready, whole short sentences are an explicitly measured temporary compromise.

For cloud audio streaming, define a separate `/v1/voice` WebSocket transport:
first message negotiates codec/sample rate/channels; audio frames have sequence
numbers; normalized transcript events feed the same turn API. Native provider
event names stay inside the adapter. Do not send raw microphone buffers to a
text chat endpoint or force native speech-to-speech through the old STT/TTS port.

## Interruptions and reconnects

1. On user speech/start or Stop action, stop local playback immediately and
   clear queued chunks; post cancellation for the active generation.
2. Cancel in-flight work where supported; discard all later chunks/events for
   that cancelled generation even if upstream work still finishes.
3. Keep only spoken text in conversational delivered history. Keep full generated
   text in diagnostic history with a cancelled flag.
4. Start the new final transcript with the updated context version. One active
   foreground turn per conversation.
5. After reconnect, resume from last acknowledged `seq`; rebuild transcript and
   evidence. Replay audio only on explicit user request.

Acoustic echo cancellation and headphones reduce self-transcription; measure
interruptions with real audio. A Stop button is a fallback, not proof of working
speech barge-in.

## Frontend that supports the demo

One screen: Start/Stop, listening/thinking/speaking/error status, transcript with
user/assistant labels and timestamps, answer cards with evidence/cutoff, and a
small sentiment indicator. Include “Corregir lo que dije”, “Más directo” and
“Repetir”. Display the historical cutoff before a capacity answer. Present at
most three spoken matches and offer the rest on screen.

Do not show provider stack traces, chain-of-thought or keys in the product.
An optional developer panel may show provider/model, tool name and timing.

Deployment must verify exact allowed origins, HTTPS microphone permission,
audio MIME/browser decoding, external DB TLS and idle reconnect behavior.
