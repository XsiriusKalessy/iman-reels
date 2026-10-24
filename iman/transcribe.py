"""Transcripción palabra a palabra.

- `local`: faster-whisper en tu ordenador (gratis; descarga el modelo la primera vez).
- `openai`: API de OpenAI (whisper-1), útil si tu ordenador va justo.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from .models import Word

SAMPLE_RATE = 16000
# Si la tarjeta gráfica ya falló una vez, no lo volvemos a intentar en cada vídeo.
_cpu_only = False


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
               openai_key: str | None = None, on_progress: Callable[[float], None] | None = None) -> list[Word]:
    """`on_progress` recibe de 0 a 1 cuánto audio lleva escuchado (solo en local)."""
    if engine == "openai":
        return _openai(audio, language, openai_key)
    return _local(audio, language, model, on_progress)


def _local(audio: Path, language: str | None, model: str,
           on_progress: Callable[[float], None] | None = None) -> list[Word]:
    global _cpu_only
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Falta faster-whisper: pip install faster-whisper") from e
    pcm = _pcm(audio)
    if not _cpu_only:
        try:
            return _whisper_words(WhisperModel(model, device="auto", compute_type="auto"), pcm, language, on_progress)
        except (RuntimeError, OSError) as e:
            # Con tarjeta NVIDIA, ctranslate2 elige CUDA, pero la app no lleva sus librerías
            # (cublas64_12.dll…). Entonces tiramos del procesador, que siempre está.
            if not _gpu_problem(e):
                raise
            _cpu_only = True
    cpu = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    return _whisper_words(cpu, pcm, language, on_progress)


def _gpu_problem(e: Exception) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in ("cublas", "cudnn", "cuda", "cudart", "nvrtc", "gpu"))


def _whisper_words(wm, pcm, language: str | None, on_progress: Callable[[float], None] | None = None) -> list[Word]:
    duration = max(len(pcm) / SAMPLE_RATE, 0.1)
    segments, _ = wm.transcribe(
        pcm, language=language, word_timestamps=True, vad_filter=False,
        # Sin VAD ni "condition_on_previous_text" para no perder muletillas ni tomas falsas.
        condition_on_previous_text=False,
        initial_prompt="Eh, em, o sea, bueno... Transcribe literalmente, con muletillas y repeticiones.",
    )
    words: list[Word] = []
    for seg in segments:
        if on_progress:
            on_progress(min(1.0, float(seg.end) / duration))
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
