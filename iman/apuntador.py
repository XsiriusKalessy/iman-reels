"""Teleprompter que sigue tu voz: oye los últimos segundos de lo que dices y dice por dónde vas del guion.

Todo en tu ordenador, con el mismo modelo que ya usa Imán para escucharte (faster-whisper): nada se manda fuera
ni cuesta nada. La app manda cada segundo y medio los últimos ~4 s de audio (PCM de 16 bits a 16 kHz) y recibe
lo que has dicho y la palabra del guion por la que vas; si no hay modelo, el guion avanza solo mientras hablas.
"""

from __future__ import annotations

import threading

from .models import normalize

RATE = 16000
MAX_SECONDS = 8
_model = None
_model_name = ""
_lock = threading.Lock()


def _get_model(name: str):
    global _model, _model_name
    with _lock:
        if _model is None or _model_name != name:
            from faster_whisper import WhisperModel

            _model = WhisperModel(name, device="cpu", compute_type="int8")
            _model_name = name
        return _model


def hear(pcm16: bytes, model: str = "small", language: str = "es", prompt: str = "") -> str:
    """Lo que se oye en el trozo (texto plano). `prompt`: el trozo de guion cercano, para que acierte las palabras."""
    import numpy as np

    audio = np.frombuffer(pcm16[: RATE * MAX_SECONDS * 2], dtype="<i2").astype(np.float32) / 32768.0
    if audio.size < RATE // 2 or float(np.abs(audio).max(initial=0.0)) < 0.01:
        return ""
    segs, _ = _get_model(model).transcribe(audio, language=language, beam_size=1, vad_filter=False,
                                           condition_on_previous_text=False, initial_prompt=prompt[:200] or None,
                                           without_timestamps=True)
    return " ".join(s.text.strip() for s in segs).strip()


def locate(script_words: list[str], heard: str, cursor: int, back: int = 8, ahead: int = 60) -> int | None:
    """Índice de la palabra del guion justo después de lo último que se ha oído, buscando cerca de `cursor`
    (un poco hacia atrás por si repites, más hacia delante). None si no casa nada con seguridad."""
    said = [normalize(w) for w in heard.split()]
    said = [w for w in said if w][-6:]
    if not said:
        return None
    norm = [normalize(w) for w in script_words]
    lo, hi = max(0, cursor - back), min(len(norm), cursor + ahead)
    best, best_score = None, 0.0
    for end in range(lo + 1, hi + 1):
        # Cuántas de las últimas palabras oídas coinciden, en orden, con las que acaban en `end`.
        score, j = 0.0, end - 1
        for k, w in enumerate(reversed(said)):
            window = norm[max(lo, j - 1): j + 1]
            if w in window:
                score += 1.0 / (1 + 0.15 * k)
                j = j - 1 - (window[::-1].index(w))
            if j < lo:
                break
        score -= 0.01 * abs(end - cursor) / 10  # a igualdad, lo más cerca de donde ibas
        if score > best_score:
            best, best_score = end, score
    need = 1.6 if len(said) >= 3 else 0.9
    return best if best is not None and best_score >= need else None
