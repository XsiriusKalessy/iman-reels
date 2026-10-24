"""Transcripción palabra a palabra.

- `local`: faster-whisper en tu ordenador (gratis; descarga el modelo la primera vez).
- `openai`: API de OpenAI (whisper-1), útil si tu ordenador va justo.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .models import Word

SAMPLE_RATE = 16000


def _pcm(audio: Path):
    """El audio a 16 kHz mono con nuestro ffmpeg. Así no dependemos de PyAV, que cambia
    su API entre versiones (p. ej. «metadata_errors» desapareció en av 19)."""
    import numpy as np

    from .media import FFMPEG

    res = subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-i", str(audio), "-vn", "-ac", "1",
                          "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"], capture_output=True)
    if res.returncode != 0:
        raise RuntimeError("No he podido leer el audio del vídeo: " + res.stderr.decode(errors="replace")[-300:])
    return np.frombuffer(res.stdout, dtype=np.float32)


def transcribe(audio: Path, engine: str = "local", language: str | None = "es", model: str = "small",
               openai_key: str | None = None) -> list[Word]:
    if engine == "openai":
        return _openai(audio, language, openai_key)
    return _local(audio, language, model)


def _local(audio: Path, language: str | None, model: str) -> list[Word]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Falta faster-whisper: pip install faster-whisper") from e
    pcm = _pcm(audio)
    try:
        return _whisper_words(WhisperModel(model, device="auto", compute_type="auto"), pcm, language)
    except (RuntimeError, OSError) as e:
        # Con tarjeta NVIDIA, ctranslate2 elige CUDA, pero la app no lleva sus librerías
        # (cublas64_12.dll…). Entonces tiramos del procesador, que siempre está.
        if not _gpu_problem(e):
            raise
        return _whisper_words(WhisperModel(model, device="cpu", compute_type="int8"), pcm, language)


def _gpu_problem(e: Exception) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in ("cublas", "cudnn", "cuda", "cudart", "nvrtc", "gpu"))


def _whisper_words(wm, pcm, language: str | None) -> list[Word]:
    segments, _ = wm.transcribe(
        pcm, language=language, word_timestamps=True, vad_filter=False,
        # Sin VAD ni "condition_on_previous_text" para no perder muletillas ni tomas falsas.
        condition_on_previous_text=False,
        initial_prompt="Eh, em, o sea, bueno... Transcribe literalmente, con muletillas y repeticiones.",
    )
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(text, float(w.start), float(w.end)))
    return words


def _openai(audio: Path, language: str | None, key: str | None) -> list[Word]:
    from openai import OpenAI

    client = OpenAI(api_key=key) if key else OpenAI()
    with open(audio, "rb") as f:
        res = client.audio.transcriptions.create(
            model="whisper-1", file=f, language=language or None,
            response_format="verbose_json", timestamp_granularities=["word"],
        )
    return [Word(w.word.strip(), float(w.start), float(w.end)) for w in (res.words or []) if w.word.strip()]
