"""Local, deterministic prosody measures from a PCM16 WAV clip (stdlib only, R-10).

G3 showed the audio model leaning on the words even when told to ignore them,
so the acoustic branch also gets numbers it cannot read from the transcript:
duration, loudness (RMS dBFS), loudness spread and speaking rate.
The clip lives only in memory for the request (R-26).
"""

from __future__ import annotations

import io
import math
import wave
from array import array
from dataclasses import dataclass


@dataclass(frozen=True)
class Prosody:
    duration_s: float
    rms_dbfs: float
    dynamic_db: float
    words_per_second: float | None

    def describe(self) -> str:
        wps = f", {self.words_per_second:.1f} palabras/s" if self.words_per_second else ""
        return f"duración {self.duration_s:.1f} s, volumen {self.rms_dbfs:.0f} dBFS, variación {self.dynamic_db:.0f} dB{wps}"


def _patch_streamed_header(data: bytes) -> bytes:
    """Some encoders stream WAV with 0xFFFFFFFF sizes; ``wave`` needs real ones."""
    if len(data) < 44 or data[:4] != b"RIFF":
        return data
    fixed = bytearray(data)
    fixed[4:8] = (len(data) - 8).to_bytes(4, "little")
    idx = data.find(b"data")
    if idx != -1:
        fixed[idx + 4: idx + 8] = (len(data) - idx - 8).to_bytes(4, "little")
    return bytes(fixed)


def measure(wav_bytes: bytes, text: str = "") -> Prosody | None:
    try:
        with wave.open(io.BytesIO(_patch_streamed_header(wav_bytes))) as w:
            if w.getsampwidth() != 2:
                return None
            rate, channels = w.getframerate(), w.getnchannels()
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError):
        return None
    samples = array("h")
    samples.frombytes(frames[: len(frames) - len(frames) % 2])
    if channels > 1:
        samples = samples[::channels]
    if not samples or not rate:
        return None
    duration = len(samples) / rate
    window = max(1, int(rate * 0.05))
    levels = []
    for i in range(0, len(samples) - window + 1, window):
        chunk = samples[i: i + window]
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk)) or 1.0
        levels.append(20 * math.log10(rms / 32768))
    voiced = [lv for lv in levels if lv > -50] or levels or [-90.0]
    voiced.sort()
    rms_db = sum(voiced) / len(voiced)
    spread = voiced[int(len(voiced) * 0.9) - 1 if len(voiced) > 1 else 0] - voiced[int(len(voiced) * 0.1)]
    words = len(text.split())
    return Prosody(duration, rms_db, spread, words / duration if words and duration > 0 else None)
