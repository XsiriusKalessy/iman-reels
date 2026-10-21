"""Transcripción palabra a palabra.

- `local`: faster-whisper en tu ordenador (gratis; descarga el modelo la primera vez).
- `openai`: API de OpenAI (whisper-1), útil si tu ordenador va justo.
"""

from __future__ import annotations

from pathlib import Path

from .models import Word


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
    wm = WhisperModel(model, device="auto", compute_type="auto")
    segments, _ = wm.transcribe(
        str(audio), language=language, word_timestamps=True, vad_filter=False,
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
