"""
Azure Voice Live behind a hexagonal VoicePort/adapter boundary.

Single file for readability; in the real project split as:
    domain/ports/voice.py        -> AudioFrame, VoicePort, VoiceEvents, AudioPort
    domain/conversation.py       -> ConversationService (pure)
    infra/voice/azure_voicelive.py -> AzureVoiceLiveAdapter
    infra/audio/pyaudio_device.py  -> PyAudioDevice
    tests/doubles/fake_voice.py    -> InMemoryVoiceAdapter

The point of the example: nothing below the "DOMAIN" banner imports azure.*,
mentions an event type, or touches base64.
"""

from __future__ import annotations

import asyncio
import base64
import json
import queue
from dataclasses import dataclass
from typing import Any, Callable, Protocol

# ---------------------------------------------------------------------------
# DOMAIN — ports and pure logic. No Azure, no PyAudio, no wire format.
# ---------------------------------------------------------------------------

SAMPLE_RATE_HZ = 24_000


@dataclass(frozen=True)
class AudioFrame:
    """Opaque carrier. The domain passes it around but never inspects it."""

    pcm16: bytes
    sample_rate: int = SAMPLE_RATE_HZ


class VoicePort(Protocol):
    """Driven port: what the domain asks a voice engine to do."""

    async def open_session(self, persona: str | None = None) -> None: ...
    async def send_audio(self, frame: AudioFrame) -> None: ...
    async def say(self, text: str) -> None: ...
    async def interrupt(self) -> None: ...
    async def answer_tool_call(self, call_id: str, result: Any) -> None: ...
    async def close(self) -> None: ...


class VoiceEvents(Protocol):
    """Driving port: what the adapter reports back into the domain."""

    async def on_session_ready(self) -> None: ...
    async def on_user_said(self, text: str) -> None: ...
    async def on_agent_said(self, text: str) -> None: ...
    async def on_user_interrupted(self) -> None: ...
    async def on_tool_requested(self, name: str, args: dict, call_id: str) -> None: ...
    async def on_turn_ended(self, usage: dict | None) -> None: ...
    async def on_failed(self, message: str) -> None: ...


class AudioPort(Protocol):
    """Driven port for the physical device. Owned by the adapter, not the domain."""

    def start_capture(self, on_frame: Callable[[AudioFrame], None]) -> None: ...
    def enqueue(self, frame: AudioFrame) -> None: ...
    def flush(self) -> None: ...
    def stop(self) -> None: ...


class ConversationService:
    """Pure domain logic. Testable with InMemoryVoiceAdapter, no I/O."""

    PERSONA = "Eres un asistente conciso y natural. Responde en espanol."

    def __init__(self, voice: VoicePort, bookings: "BookingUseCase") -> None:
        self._voice = voice
        self._bookings = bookings
        self.transcript: list[tuple[str, str]] = []
        self.interruptions = 0

    async def start(self) -> None:
        await self._voice.open_session(persona=self.PERSONA)

    # --- VoiceEvents implementation -------------------------------------
    async def on_session_ready(self) -> None:
        await self._voice.say("Hola, en que puedo ayudarte?")

    async def on_user_said(self, text: str) -> None:
        self.transcript.append(("user", text))

    async def on_agent_said(self, text: str) -> None:
        self.transcript.append(("agent", text))

    async def on_user_interrupted(self) -> None:
        # Domain-level meaning only. The audio flush already happened in the adapter.
        self.interruptions += 1

    async def on_tool_requested(self, name: str, args: dict, call_id: str) -> None:
        if name == "check_availability":
            result = await self._bookings.check_availability(**args)
        else:
            result = {"error": f"unknown tool {name}"}
        await self._voice.answer_tool_call(call_id, result)

    async def on_turn_ended(self, usage: dict | None) -> None:
        pass

    async def on_failed(self, message: str) -> None:
        self.transcript.append(("error", message))


class BookingUseCase:
    """A plain use case. It has no idea it is reachable by voice."""

    async def check_availability(self, date: str, party_size: int) -> dict:
        return {"date": date, "party_size": party_size, "slots": ["19:00", "21:30"]}


# ---------------------------------------------------------------------------
# ADAPTER — the only place that knows Azure exists.
# ---------------------------------------------------------------------------

try:
    from azure.ai.voicelive.aio import connect
    from azure.ai.voicelive.models import (
        AudioEchoCancellation,
        AudioInputTranscriptionOptions,
        AudioNoiseReduction,
        AzureSemanticVadMultilingual,
        AzureStandardVoice,
        InputAudioFormat,
        Modality,
        OutputAudioFormat,
        RequestSession,
        ServerEventType,
    )
except ImportError:  # pip install "azure-ai-voicelive[aiohttp]" azure-identity
    # Deliberate: the domain demo at the bottom must run without the SDK.
    # That it does is the proof the boundary holds.
    connect = RequestSession = ServerEventType = None
    AudioEchoCancellation = AudioInputTranscriptionOptions = None
    AudioNoiseReduction = AzureSemanticVadMultilingual = AzureStandardVoice = None
    InputAudioFormat = Modality = OutputAudioFormat = None


@dataclass(frozen=True)
class VoiceLiveConfig:
    """Infrastructure knobs. Never domain concerns."""

    endpoint: str
    model: str | None = "gpt-realtime"
    agent_id: str | None = None          # agent mode: set this instead of model
    project_name: str | None = None
    voice_name: str = "es-ES-XimenaNeural"
    api_version: str = "2026-04-10"


TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "check_availability",
        "description": "Consulta mesas disponibles para una fecha.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "party_size": {"type": "integer"},
            },
            "required": ["date", "party_size"],
        },
    }
]


class AzureVoiceLiveAdapter(VoicePort):
    def __init__(self, cfg: VoiceLiveConfig, credential, audio: AudioPort) -> None:
        self._cfg = cfg
        self._credential = credential
        self._audio = audio
        self._conn = None
        self._events: VoiceEvents | None = None
        self._pump: asyncio.Task | None = None
        self._ctx: Any = None

    def bind(self, events: VoiceEvents) -> None:
        self._events = events

    # --- VoicePort ------------------------------------------------------
    async def open_session(self, persona: str | None = None) -> None:
        kwargs: dict[str, Any] = {
            "endpoint": self._cfg.endpoint,
            "credential": self._credential,
            "api_version": self._cfg.api_version,
        }
        if self._cfg.agent_id:
            # Agent mode: instructions live in Foundry, NOT in session.update.
            kwargs["agent_config"] = {
                "agent_name": self._cfg.agent_id,
                "project_name": self._cfg.project_name,
            }
            persona = None
        else:
            kwargs["model"] = self._cfg.model

        self._ctx = connect(**kwargs)
        self._conn = await self._ctx.__aenter__()

        session = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            input_audio_format=InputAudioFormat.PCM16,
            output_audio_format=OutputAudioFormat.PCM16,
            voice=AzureStandardVoice(name=self._cfg.voice_name, type="azure-standard"),
            input_audio_transcription=AudioInputTranscriptionOptions(model="azure-speech"),
            # Azure differentiators: semantic end-of-turn + barge-in.
            turn_detection=AzureSemanticVadMultilingual(
                threshold=0.5,
                prefix_padding_ms=420,
                silence_duration_ms=500,
                remove_filler_words=True,
                interrupt_response=True,
            ),
            input_audio_noise_reduction=AudioNoiseReduction(type="azure_deep_noise_suppression"),
            input_audio_echo_cancellation=AudioEchoCancellation(),
            tools=TOOL_SCHEMAS,
            **({"instructions": persona} if persona else {}),
        )
        await self._conn.session.update(session=session)

        self._audio.start_playback() if hasattr(self._audio, "start_playback") else None
        self._pump = asyncio.create_task(self._run_event_pump())

    async def send_audio(self, frame: AudioFrame) -> None:
        # base64 lives here and nowhere else.
        payload = base64.b64encode(frame.pcm16).decode("utf-8")
        await self._conn.input_audio_buffer.append(audio=payload)

    async def say(self, text: str) -> None:
        await self._conn.conversation.item.create(
            item={
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
            }
        )
        await self._conn.response.create()

    async def interrupt(self) -> None:
        self._audio.flush()
        await self._conn.response.cancel()

    async def answer_tool_call(self, call_id: str, result: Any) -> None:
        await self._conn.conversation.item.create(
            item={
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result),
            }
        )
        await self._conn.response.create()

    async def close(self) -> None:
        if self._pump:
            self._pump.cancel()
        self._audio.stop()
        if self._ctx:
            await self._ctx.__aexit__(None, None, None)

    # --- translation layer ---------------------------------------------
    async def _run_event_pump(self) -> None:
        """The ONLY place server event names appear."""
        pending_tool_args: dict[str, str] = {}

        async for ev in self._conn:
            t = ev.type

            if t == ServerEventType.SESSION_UPDATED:
                # Capture starts only after the server confirms configuration.
                self._audio.start_capture(self._on_mic_frame)
                await self._events.on_session_ready()

            elif t == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                # RULE 3: flush first, synchronously — do not await before this.
                self._audio.flush()
                await self._events.on_user_interrupted()

            elif t == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                await self._events.on_user_said(ev.transcript)

            elif t == ServerEventType.RESPONSE_AUDIO_DELTA:
                # Audio never reaches the domain; it goes straight to the device.
                self._audio.enqueue(AudioFrame(ev.delta))

            elif t == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
                await self._events.on_agent_said(ev.transcript)

            elif t == ServerEventType.RESPONSE_FUNCTION_CALL_ARGUMENTS_DELTA:
                pending_tool_args[ev.call_id] = pending_tool_args.get(ev.call_id, "") + ev.delta

            elif t == ServerEventType.RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE:
                raw = getattr(ev, "arguments", None) or pending_tool_args.pop(ev.call_id, "{}")
                await self._events.on_tool_requested(ev.name, json.loads(raw), ev.call_id)

            elif t == ServerEventType.RESPONSE_DONE:
                await self._events.on_turn_ended(getattr(ev.response, "usage", None))

            elif t == ServerEventType.ERROR:
                await self._events.on_failed(ev.error.message)

    def _on_mic_frame(self, frame: AudioFrame) -> None:
        # Called from the device thread — hop back onto the loop.
        asyncio.run_coroutine_threadsafe(self.send_audio(frame), self._loop)

    @property
    def _loop(self) -> asyncio.AbstractEventLoop:
        return asyncio.get_event_loop()


# ---------------------------------------------------------------------------
# DEVICE ADAPTER — PyAudio. Swappable for WebRTC or a telephony bridge.
# ---------------------------------------------------------------------------

try:
    import pyaudio
except ImportError:  # pip install pyaudio
    pyaudio = None

CHUNK_BYTES = 1200  # 50 ms at 24 kHz mono PCM16


class PyAudioDevice(AudioPort):
    def __init__(self) -> None:
        self._pa = pyaudio.PyAudio()
        self._in = None
        self._out = None
        self._queue: queue.Queue[bytes | None] = queue.Queue()

    def start_capture(self, on_frame: Callable[[AudioFrame], None]) -> None:
        def cb(in_data, frame_count, time_info, status):
            on_frame(AudioFrame(in_data))
            return (None, pyaudio.paContinue)

        self._in = self._pa.open(
            format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE_HZ,
            input=True, frames_per_buffer=CHUNK_BYTES, stream_callback=cb,
        )

    def start_playback(self) -> None:
        leftover = b""

        def cb(in_data, frame_count, time_info, status):
            nonlocal leftover
            needed = frame_count * pyaudio.get_sample_size(pyaudio.paInt16)
            out, leftover = leftover[:needed], leftover[needed:]
            while len(out) < needed:
                try:
                    chunk = self._queue.get_nowait()
                except queue.Empty:
                    out += bytes(needed - len(out))  # pad with silence
                    break
                if chunk is None:
                    break
                out += chunk
            if len(out) > needed:
                leftover, out = out[needed:], out[:needed]
            return (out, pyaudio.paContinue)

        self._out = self._pa.open(
            format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE_HZ,
            output=True, frames_per_buffer=CHUNK_BYTES, stream_callback=cb,
        )

    def enqueue(self, frame: AudioFrame) -> None:
        self._queue.put(frame.pcm16)

    def flush(self) -> None:
        """Barge-in: drop everything not yet played."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def stop(self) -> None:
        for stream in (self._in, self._out):
            if stream:
                stream.stop_stream()
                stream.close()
        self._pa.terminate()


# ---------------------------------------------------------------------------
# TEST DOUBLE — the payoff of the boundary: domain tests with zero I/O.
# ---------------------------------------------------------------------------


class InMemoryVoiceAdapter(VoicePort):
    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.tool_answers: list[tuple[str, Any]] = []
        self.interrupted = False
        self.events: VoiceEvents | None = None

    def bind(self, events: VoiceEvents) -> None:
        self.events = events

    async def open_session(self, persona: str | None = None) -> None:
        await self.events.on_session_ready()

    async def send_audio(self, frame: AudioFrame) -> None: ...
    async def say(self, text: str) -> None: self.spoken.append(text)
    async def interrupt(self) -> None: self.interrupted = True
    async def answer_tool_call(self, call_id: str, result: Any) -> None:
        self.tool_answers.append((call_id, result))
    async def close(self) -> None: ...

    # Scripting helpers a test uses to drive the domain.
    async def user_says(self, text: str) -> None:
        await self.events.on_user_said(text)

    async def model_calls(self, name: str, args: dict, call_id: str = "c1") -> None:
        await self.events.on_tool_requested(name, args, call_id)


async def _example_test() -> None:
    voice = InMemoryVoiceAdapter()
    convo = ConversationService(voice, BookingUseCase())
    voice.bind(convo)

    await convo.start()
    assert voice.spoken == ["Hola, en que puedo ayudarte?"]

    await voice.user_says("Mesa para dos el viernes")
    await voice.model_calls("check_availability", {"date": "2026-09-18", "party_size": 2})

    call_id, result = voice.tool_answers[0]
    assert result["slots"] == ["19:00", "21:30"]
    assert convo.transcript[0] == ("user", "Mesa para dos el viernes")


if __name__ == "__main__":
    asyncio.run(_example_test())
    print("domain verified without Azure, WebSocket or a microphone")
