---
name: azure-voice-live
description: Use when building, wiring or debugging a real-time speech-to-speech voice agent on Azure AI Voice Live (WebSocket session, session.update, barge-in/interruption, audio deltas, function calling) or when placing such an agent behind a VoicePort/adapter boundary in a hexagonal architecture.
---

# Azure AI Voice Live

## Overview

Voice Live is a **single fully-managed WebSocket** that replaces the STT -> LLM -> TTS chain. You send PCM16 audio frames up; you get audio frames, transcripts, viseme/timestamp data and function calls down. No model deployment, no orchestration.

**Core principle for our codebase:** the WebSocket event stream is *transport detail*. The domain must never see `event.type`, base64 strings, or PCM bytes. All of that dies at the adapter boundary.

## When to Use

- Building a voice agent / hands-free assistant / contact-center bot on Azure.
- Debugging: agent talks over the user, audio cuts out, `session.updated` never arrives, 401 on the WS handshake.
- Deciding where voice concerns belong relative to the domain (VoicePort vs. adapter vs. infra).

**Not for:** batch transcription (use Speech-to-Text), pure TTS (use Speech Synthesis), or browser-direct low-latency streaming (use the **WebRTC** variant of Voice Live, not raw WebSocket).

## Connection

| Piece | Value |
|---|---|
| Endpoint (Foundry resource) | `wss://<resource>.services.ai.azure.com/voice-live/realtime?api-version=2026-04-10` |
| Endpoint (legacy resource) | `wss://<resource>.cognitiveservices.azure.com/voice-live/realtime?...` |
| Model mode | add `&model=gpt-realtime` (or `gpt-4.1`, `gpt-5`, `azure-realtime`, ...) |
| Agent mode | add `&agent_id=...&project_id=...` instead of `model` |
| Auth (preferred) | `Authorization: Bearer <token>`, scope `https://ai.azure.com/.default`, roles `Cognitive Services User` + `Foundry User` |
| Auth (fallback) | `api-key` header (not available in browsers) or `?api-key=` query param |

**Model vs. agent mode:** agent mode moves instructions/tools/flow into the Foundry agent, so client code only carries the agent id. Prefer it when conversational logic changes independently of the client. `instructions` in `session.update` is **rejected** when using a custom agent.

Python SDK (`azure-ai-voicelive[aiohttp]`) is **async-only since 1.0.0** — `from azure.ai.voicelive.aio import connect`.

## Session configuration

First message after connect is almost always `session.update`. The server confirms with `session.updated`.

```json
{
  "type": "session.update",
  "session": {
    "modalities": ["text", "audio"],
    "instructions": "Eres un asistente conciso y natural.",
    "voice": { "name": "es-ES-XimenaNeural", "type": "azure-standard", "rate": "1.0" },
    "input_audio_format": "pcm16",
    "output_audio_format": "pcm16",
    "input_audio_sampling_rate": 24000,
    "input_audio_transcription": { "model": "azure-speech", "language": "es" },
    "turn_detection": {
      "type": "azure_semantic_vad_multilingual",
      "threshold": 0.5,
      "prefix_padding_ms": 420,
      "silence_duration_ms": 500,
      "remove_filler_words": true,
      "interrupt_response": true
    },
    "input_audio_noise_reduction": { "type": "azure_deep_noise_suppression" },
    "input_audio_echo_cancellation": { "type": "server_echo_cancellation" }
  }
}
```

The Azure-only differentiators worth turning on: `azure_semantic_vad` / `azure_semantic_vad_multilingual` (semantic end-of-turn, not just volume), `azure_deep_noise_suppression`, `server_echo_cancellation`. Everything else matches the OpenAI Realtime API.

**Audio contract:** PCM16, mono, 24 kHz (16 kHz also allowed), 1200-byte chunks ~= 50 ms. Uploaded audio is base64; `response.audio.delta` arrives as raw bytes via the SDK.

## Event quick reference

**Client -> server**

| Event | Purpose |
|---|---|
| `session.update` | Configure/reconfigure the session |
| `input_audio_buffer.append` | Push a base64 PCM16 chunk |
| `input_audio_buffer.commit` / `.clear` | Force end-of-turn / discard buffer (manual VAD only) |
| `conversation.item.create` | Inject a message or a `function_call_output` |
| `conversation.item.truncate` | Tell the server how much audio the user actually heard after a barge-in |
| `response.create` / `response.cancel` | Trigger or abort generation |
| `session.avatar.connect` | Send the client SDP offer for avatar WebRTC |

**Server -> client**

| Event | Meaning / action |
|---|---|
| `session.created`, `session.updated` | Handshake done -> **now** start mic capture |
| `input_audio_buffer.speech_started` | User began talking -> **flush playback queue immediately** |
| `input_audio_buffer.speech_stopped` | End of user turn |
| `conversation.item.input_audio_transcription.completed` | Final user transcript (`.failed` on error) |
| `response.created` | Generation started |
| `response.audio.delta` / `.done` | Audio chunk to play / end of speech |
| `response.audio_transcript.delta` / `.done` | Agent transcript, streaming / final |
| `response.function_call_arguments.delta` / `.done` | Tool call — args complete on `.done` |
| `response.done` | Whole turn finished (contains usage) |
| `response.audio_timestamp.*`, `response.animation_viseme.*` | Azure extras for lip-sync/captions |
| `rate_limits.updated`, `error` | Throttling info; `error.error.message` |

## The barge-in rule

This is the #1 bug in voice agents and it is **not** solved by the service:

> On `input_audio_buffer.speech_started`, the client must discard its *local* playback queue **synchronously**, before awaiting anything.

The service stops generating, but audio already buffered in your speaker queue keeps playing — the agent talks over the user. Also send `conversation.item.truncate` with the milliseconds actually played so the model's context matches what the user heard.

## Mapping to our hexagonal architecture

Two ports, opposite directions. Do not collapse them into one interface.

```
          domain (use cases, ConversationPolicy)
                ^                      |
  VoiceEvents   |  (driving)           |  VoicePort (driven)
                |                      v
          AzureVoiceLiveAdapter  --ws-->  Voice Live API
                |
                +-- AudioPort (mic/speaker: PyAudio, WebRTC, telephony)
```

| Port | Direction | Methods (domain vocabulary only) |
|---|---|---|
| `VoicePort` | domain -> adapter | `open_session(persona)`, `send_audio(frame)`, `say(text)`, `interrupt()`, `answer_tool_call(call_id, result)`, `close()` |
| `VoiceEvents` | adapter -> domain | `on_user_said(text)`, `on_agent_said(text)`, `on_user_interrupted()`, `on_tool_requested(name, args, call_id)`, `on_turn_ended(usage)`, `on_failed(error)` |
| `AudioPort` | adapter -> device | `start_capture(cb)`, `enqueue(frame)`, `flush()`, `stop()` |

**Translation rules the adapter owns:**

1. **Event names never leave the adapter.** `ServerEventType.RESPONSE_AUDIO_DELTA` becomes `AudioPort.enqueue(bytes)`. The domain is never told an "audio delta" exists.
2. **Base64 and PCM never enter the domain.** An `AudioFrame` value object (bytes + sample rate) is the widest thing the port accepts; the domain works in transcripts and intents.
3. **Barge-in is handled twice, at two altitudes.** The adapter flushes `AudioPort` *first* (latency-critical, no `await`), then notifies `on_user_interrupted()` so the domain can update conversation state.
4. **Function calls are the seam to your use cases.** `response.function_call_arguments.done` -> adapter parses JSON -> invokes the domain use case -> sends `conversation.item.create` (`function_call_output`) + `response.create`. Tool *schemas* are adapter-side translations of use-case signatures; the use case itself knows nothing about Voice Live.
5. **Session config is infrastructure; persona is domain.** Voice name, VAD thresholds, noise suppression -> adapter config/env. The persona/instructions string is domain policy passed through `open_session(persona)`. In agent mode it lives in Foundry and `open_session` takes no persona.
6. **The event loop lives in the adapter**, not in a use case. `async for event in connection` is a driving-side pump; give it its own task and let it fan out into `VoiceEvents`.

A testable consequence: the domain can be exercised with an `InMemoryVoiceAdapter` that feeds scripted transcripts — no Azure, no microphone, no WebSocket.

See `adapter-example.py` in this skill directory for a complete adapter that follows all six rules.

## Common mistakes

| Mistake | Consequence / fix |
|---|---|
| Starting mic capture before `session.updated` | Audio dropped or session config raced. Capture starts in the `session.updated` handler. |
| Only cancelling the response on barge-in | Agent keeps talking from the local buffer. Flush the playback queue too. |
| Leaking `event.type` into use cases | Domain now depends on Azure's wire format; adapter is no longer swappable. |
| Sending `instructions` in agent mode | Rejected by the service. Instructions belong to the Foundry agent. |
| Sync SDK usage | Removed in `azure-ai-voicelive` 1.0.0. Use `azure.ai.voicelive.aio`. |
| `asyncio` call from the PyAudio callback thread | Callbacks run on another thread — use `asyncio.run_coroutine_threadsafe(coro, loop)` with a loop captured at start-up. |
| Mismatched sample rates | Chipmunk/slow audio. Device, `input_audio_sampling_rate` and playback must all agree (24000). |
| Delaying playback > 2 s with server echo cancellation | Echo cancellation degrades. Either play immediately, or use Live-Reference AEC (`reference_source: "client"`, `channels: 2`, interleaved mic+playback stereo). |

## Sources

- Module: [Develop an Azure Speech Voice Live Agent in Microsoft Foundry](https://learn.microsoft.com/en-us/training/modules/develop-voice-live-agent/)
- [How to use the Voice Live API](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live-how-to)
- [Voice Live API overview](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live)
- [Voice Live quickstart](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live-quickstart)
