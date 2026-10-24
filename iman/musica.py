"""Música de fondo hecha por Imán: varios estilos generados con matemáticas, con la duración exacta del reel.

Como los efectos de sonido, no sale de ninguna librería: es nuestra y se puede usar en reels comerciales.
Cada estilo tiene su tempo, sus acordes, su batería y sus instrumentos; la misma semilla da la misma canción.
"""

from __future__ import annotations

import math
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RATE = 44100
NOTES = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
         "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
QUALITY = {"": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "m7": (0, 3, 7, 10), "maj7": (0, 4, 7, 11),
           "sus2": (0, 2, 7), "add9": (0, 4, 7, 14)}


def _midi(name: str, octave: int) -> int:
    return 12 * (octave + 1) + NOTES[name]


def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _chord(sym: str, octave: int = 3) -> list[int]:
    root = sym[:2] if len(sym) > 1 and sym[1] in "#b" else sym[:1]
    return [_midi(root, octave) + i for i in QUALITY[sym[len(root):]]]


# ---- Instrumentos (todo vectorizado: un minuto de música se genera en un par de segundos) ----

def _t(sec: float) -> np.ndarray:
    return np.arange(int(sec * RATE)) / RATE


def _adsr(n: int, a: float, d: float, s: float, r: float) -> np.ndarray:
    t = np.arange(n) / RATE
    dur = n / RATE
    env = np.where(t < a, t / max(a, 1e-4), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-4)))
    rel = np.clip((dur - t) / max(r, 1e-4), 0, 1)
    return env * rel


def _tone(hz: float, sec: float, harmonics: list[float], detune: float = 0.0) -> np.ndarray:
    t = _t(sec)
    out = np.zeros_like(t)
    for k, amp in enumerate(harmonics, start=1):
        if hz * k > 16000:
            break
        out += amp * np.sin(2 * np.pi * hz * k * t)
        if detune:
            out += amp * 0.7 * np.sin(2 * np.pi * hz * k * (1 + detune) * t + 1.3)
    return out


SAW = [1 / k for k in range(1, 14)]
SOFT = [1.0, 0.35, 0.12, 0.05]
KEYS = [1.0, 0.5, 0.25, 0.12, 0.06, 0.03]
MARIMBA = [1.0, 0.0, 0.0, 0.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.08]


def pad(hz: float, sec: float) -> np.ndarray:
    return _tone(hz, sec, SAW[:7], detune=0.004) * _adsr(int(sec * RATE), 0.6, 2.0, 0.8, 0.5) * 0.10


def keys(hz: float, sec: float) -> np.ndarray:
    return _tone(hz, sec, KEYS) * _adsr(int(sec * RATE), 0.008, 0.6, 0.35, 0.15) * 0.16


def pluck(hz: float, sec: float) -> np.ndarray:
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    bright = sum((1 / k) * np.exp(-t * (6 + 5 * k)) * np.sin(2 * np.pi * hz * k * t) for k in range(1, 7))
    return bright * np.clip((sec - t) / 0.03, 0, 1) * 0.22


def marimba(hz: float, sec: float) -> np.ndarray:
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    return _tone(hz, sec, MARIMBA) * np.exp(-t * 9) * np.clip(t / 0.003, 0, 1) * 0.3


def strings(hz: float, sec: float) -> np.ndarray:
    """Cuerdas cortas (ostinato): ataque rápido y algo de vibrato, como un violonchelo marcado."""
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    vib = 1 + 0.003 * np.sin(2 * np.pi * 5.5 * t)
    x = sum((1 / k) * np.sin(2 * np.pi * hz * k * np.cumsum(vib) / RATE) for k in range(1, 9))
    return x * _adsr(n, 0.015, 0.15, 0.55, 0.04) * 0.13


def braam(hz: float, sec: float) -> np.ndarray:
    """Metales graves que crecen ("braaam") para los momentos épicos."""
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    swell = np.clip(t / 0.35, 0, 1) * np.exp(-np.maximum(0, t - 0.6) * 0.9)
    x = _tone(hz, sec, SAW[:10], detune=0.006) + _tone(hz / 2, sec, SAW[:6], detune=0.004)
    return np.tanh(x * 1.6) * swell * 0.16


def piano(hz: float, sec: float) -> np.ndarray:
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    x = sum(a * np.exp(-t * (1.8 + 1.2 * k)) * np.sin(2 * np.pi * hz * k * 1.0005 ** k * t)
            for k, a in enumerate([1.0, 0.45, 0.22, 0.1, 0.05], start=1))
    return x * np.clip(t / 0.004, 0, 1) * np.clip((sec - t) / 0.08, 0, 1) * 0.2


def bass(hz: float, sec: float) -> np.ndarray:
    return _tone(hz, sec, [1.0, 0.45, 0.2, 0.08]) * _adsr(int(sec * RATE), 0.01, 0.4, 0.7, 0.06) * 0.35


def sub808(hz: float, sec: float, glide_from: float | None = None) -> np.ndarray:
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    f = hz if glide_from is None else hz + (glide_from - hz) * np.exp(-t * 18)
    x = np.sin(2 * np.pi * np.cumsum(np.broadcast_to(f, t.shape)) / RATE)
    return np.tanh(x * 2.2) * np.exp(-t * 1.6) * np.clip((sec - t) / 0.05, 0, 1) * 0.42


def cowbell(hz: float, sec: float) -> np.ndarray:
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    x = np.sign(np.sin(2 * np.pi * hz * t)) * 0.5 + np.sign(np.sin(2 * np.pi * hz * 1.48 * t)) * 0.5
    return x * np.exp(-t * 11) * 0.09


_rng = np.random.default_rng(11)


def kick(strength: float = 1.0) -> np.ndarray:
    t = _t(0.45)
    f = 48 + 110 * np.exp(-t * 32)
    return np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 7) * 0.9 * strength


def snare() -> np.ndarray:
    t = _t(0.25)
    noise = np.diff(_rng.uniform(-1, 1, len(t) + 1)) * 0.5
    return (noise * np.exp(-t * 18) * 0.5 + np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25) * 0.35)


def clap() -> np.ndarray:
    t = _t(0.22)
    noise = np.diff(_rng.uniform(-1, 1, len(t) + 1)) * 0.5
    bursts = sum(np.exp(-np.maximum(0, t - d) * 60) * (t >= d) for d in (0, 0.011, 0.022))
    return noise * bursts * np.exp(-t * 9) * 0.45


def hat(open_: bool = False) -> np.ndarray:
    t = _t(0.25 if open_ else 0.05)
    noise = np.diff(np.diff(_rng.uniform(-1, 1, len(t) + 2))) * 0.25  # dos derivadas: solo agudos
    return noise * np.exp(-t * (14 if open_ else 70)) * 0.35


def tom(hz: float = 90) -> np.ndarray:
    t = _t(0.8)
    f = hz + hz * 0.8 * np.exp(-t * 12)
    return np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 4) * 0.7


# ---- Estilos ----

@dataclass(frozen=True)
class Style:
    name: str
    label: str
    bpm: int
    chords: tuple[str, ...]
    kick: str  # 16 pasos por compás: "x" golpe
    snare: str
    hat: str
    lead: str = ""  # instrumento de la melodía o arpegio
    lead_steps: str = ""  # en qué pasos suena el arpegio
    chord_inst: str = "pad"
    bass_steps: str = "x......."
    swing: float = 0.0
    crackle: bool = False
    phonk: bool = False
    toms: bool = False
    ostinato: bool = False  # cuerdas en semicorcheas (épica)
    braam: bool = False  # metales graves cada dos compases
    drums_from: int = 1  # compás en el que entra la batería (para que la canción crezca)


STYLES: dict[str, Style] = {
    "tranquila": Style("tranquila", "Tranquila (lo-fi)", 80, ("Am7", "Dm7", "G7", "Cmaj7"),
                       "x.....x...x.....", "....x.......x...", "x.x.x.x.x.x.x.x.", lead="keys",
                       chord_inst="keys", bass_steps="x.....x.", swing=0.18, crackle=True),
    "alegre": Style("alegre", "Pop alegre", 118, ("C", "G", "Am", "F"),
                    "x...x...x...x...", "....x.......x...", "..x...x...x...x.", lead="pluck",
                    lead_steps="x.xx.x.xx.x.x.xx", bass_steps="x.x.x.x."),
    "cinematica": Style("cinematica", "Cinemática", 70, ("Dm", "Bb", "F", "C"),
                        "x...............", "................", "................", lead="keys",
                        lead_steps="x...x...x...x...", bass_steps="x.......", toms=True),
    "tropical": Style("tropical", "Tropical house", 105, ("F", "C", "Dm", "Bb"),
                      "x...x...x...x...", "....x.......x...", "..x...x...x...x.", lead="marimba",
                      lead_steps="..x..x.x..x..x.x", bass_steps="x..x..x."),
    "phonk": Style("phonk", "Enérgica (phonk)", 140, ("Cm", "Cm", "Ab", "G"),
                   "x.........x.....", "........x.......", "x.xxx.x.x.xxx.xx", lead="cowbell",
                   lead_steps="x..x..x...x..x..", chord_inst="", bass_steps="x.........x.....", phonk=True),
    "corporativa": Style("corporativa", "Corporativa", 100, ("C", "Am", "F", "G"),
                         "x.......x.......", "....x.......x...", "x.x.x.x.x.x.x.x.", lead="keys",
                         lead_steps="x.x.x.x.x.x.x.x.", bass_steps="x...x..."),
}

STYLES.update({
    "epica": Style("epica", "Épica (cine)", 90, ("Dm", "Bb", "F", "C"),
                   "x.......x.......", "................", "................", chord_inst="pad",
                   bass_steps="x.......", toms=True, ostinato=True, braam=True, drums_from=2),
    "emotiva": Style("emotiva", "Emotiva", 68, ("C", "G", "Am", "F"),
                     "................", "................", "................", lead="piano",
                     lead_steps="x.x.x.x.x.x.x.x.", chord_inst="pad", bass_steps="x......."),
    "inspiracional": Style("inspiracional", "Inspiracional", 96, ("F", "C", "G", "Am"),
                           "x...x...x...x...", "....x.......x...", "................", lead="piano",
                           lead_steps="x.x.x.x.x.x.x.x.", chord_inst="pad", bass_steps="x...x...", drums_from=4),
    "suspense": Style("suspense", "Suspense", 85, ("Am", "F", "Dm", "E"),
                      "x.......x.......", "................", "..x...x...x...x.", lead="piano",
                      lead_steps="x.......x.......", chord_inst="pad", bass_steps="x.x.x.x.", drums_from=2),
    "acustica": Style("acustica", "Acústica", 92, ("G", "D", "Em", "C"),
                      "x.......x.......", "....x.......x...", "x.x.x.x.x.x.x.x.", lead="pluck",
                      lead_steps="x.xx.xx.x.xx.xx.", chord_inst="", bass_steps="x...x...", swing=0.08),
    "romantica": Style("romantica", "Romántica", 72, ("Fmaj7", "Em7", "Dm7", "Cmaj7"),
                       "x.........x.....", "....x.......x...", "x...x...x...x...", lead="piano",
                       lead_steps="x..x..x.x..x..x.", chord_inst="keys", bass_steps="x.....x.", swing=0.12),
})

LEADS = {"keys": keys, "pluck": pluck, "marimba": marimba, "cowbell": cowbell, "piano": piano}


def _place(buf: np.ndarray, snd: np.ndarray, at: float, gain: float = 1.0) -> None:
    i = int(at * RATE)
    if i >= len(buf):
        return
    piece = snd[: len(buf) - i] * gain
    buf[i:i + len(piece)] += piece


def render(style_key: str, duration: float, dst: Path, seed: int = 0) -> Path:
    """Escribe en `dst` (WAV) una pieza del estilo pedido que dura al menos `duration` segundos."""
    st = STYLES[style_key]
    rng = np.random.default_rng(seed)
    beat = 60 / st.bpm
    step = beat / 4
    bar = beat * 4
    bars = max(2, math.ceil((duration + 0.5) / bar))
    total = bars * bar + 2.0
    buf = np.zeros(int(total * RATE))
    for b in range(bars):
        t0 = b * bar
        sym = st.chords[b % len(st.chords)]
        notes = _chord(sym, 3)
        root = notes[0]
        intro = b < st.drums_from and bars > st.drums_from + 2  # la batería entra más tarde: la canción crece
        if st.chord_inst == "pad":
            for m in notes:
                _place(buf, pad(_hz(m + 12), bar + 0.4), t0)
        elif st.chord_inst == "keys":
            for k, m in enumerate(notes):
                for hit in (0, 2.5 if st.swing else 2):
                    _place(buf, keys(_hz(m + 12), beat * 1.4), t0 + hit * beat + k * 0.012)
        if st.toms and b % 2 == 0:
            _place(buf, tom(70), t0, 0.9)
            _place(buf, tom(55), t0 + bar - beat, 0.6)
        if st.ostinato:
            pattern = [root, root, root + 7, root, root + 12, root, root + 7, root + 3] * 2
            for s16, m in enumerate(pattern):
                _place(buf, strings(_hz(m), step * 0.9), t0 + s16 * step, 0.9 if s16 % 4 == 0 else 0.6)
        if st.braam and b % 2 == 0 and not intro:
            _place(buf, braam(_hz(root - 12), bar * 1.6), t0)
        lead = LEADS.get(st.lead)
        if lead and st.lead_steps and (not intro or st.lead == "piano"):
            arp = notes + [notes[0] + 12, notes[1] + 12]
            for s, c in enumerate(st.lead_steps):
                if c == "x":
                    m = arp[(s + b) % len(arp)] + (24 if st.phonk else 12)
                    length = step * (6 if st.lead == "piano" else 3 if st.lead == "keys" else 2)
                    _place(buf, lead(_hz(m), length), t0 + s * step, 0.8)
        for s in range(16):
            at = t0 + s * step + (step * st.swing if s % 2 == 1 else 0)
            if intro:
                continue
            if st.kick[s] == "x":
                _place(buf, kick(1.1 if st.phonk else 1.0), at)
            if st.snare[s] == "x":
                _place(buf, clap() if st.name in ("alegre", "tropical", "phonk") else snare(), at, 0.8)
            if st.hat[s] == "x":
                _place(buf, hat(open_=st.name == "tropical" and s % 4 == 2), at, rng.uniform(0.5, 0.9))
        for s, c in enumerate(st.bass_steps):
            if c != "x":
                continue
            at = t0 + s * (bar / len(st.bass_steps))
            length = bar / len(st.bass_steps) * (3 if st.phonk else 0.95)
            if st.phonk:
                _place(buf, sub808(_hz(root - 12), length, glide_from=_hz(root - 5) if s else None), at)
            else:
                _place(buf, bass(_hz(root - 12), length), at)
    if st.crackle:
        crackle = (rng.random(len(buf)) > 0.9994) * rng.uniform(-0.25, 0.25, len(buf))
        buf += crackle + rng.normal(0, 0.004, len(buf))
    # Fundido final y normalizado.
    n_end = int((bars * bar) * RATE)
    fade = int(1.5 * RATE)
    buf[max(0, n_end - fade):n_end] *= np.linspace(1, 0, min(fade, n_end))
    buf[n_end:] = 0
    buf = np.tanh(buf / max(1e-6, float(np.max(np.abs(buf)))) * 1.3) * 0.8
    dst.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((buf[:n_end] * 32767).astype("<i2").tobytes())
    return dst
