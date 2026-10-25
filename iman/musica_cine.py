"""Música de cine y de festival hecha por Imán: tráiler épico, aventura, híbrida, documental, drop EDM y misterio.

Cada pieza tiene estructura de tráiler: entrada suave (zumbido grave, cuerdas, pulsos), subida (riser, redoble
de taikos, platillo al revés), un silencio de un instante y el golpe (impacto, «braaam» de metales, taikos,
cuerdas en ostinato, coro). El golpe cae justo donde acaba el gancho del reel (`drop_at`).

Igual que el resto de la música de Imán, no sale de ninguna librería: se calcula aquí, así que es nuestra y se
puede usar en reels comerciales. Los instrumentos usan tablas de onda (rápido: un minuto en pocos segundos).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

RATE = 44100
TABLE = 4096


@dataclass(frozen=True)
class Cine:
    minor: bool = True
    ostinato: bool = True  # cuerdas en semicorcheas a partir del golpe
    taiko: bool = True
    braam: bool = True
    choir: bool = True
    horns: bool = False  # melodía de trompas (aventura)
    piano: bool = False  # notas de piano en la entrada (documental)
    pulse: bool = False  # pulsos de sintetizador (híbrida)
    tick: bool = False  # reloj (misterio)
    festival: bool = False  # bombo a negras, supersaw con bombeo y sub (EDM)
    room: float = 0.55


PRESETS = {
    "trailer": Cine(),
    "aventura": Cine(minor=False, horns=True, choir=False, room=0.5),
    "hibrida": Cine(pulse=True, choir=False, room=0.45),
    "documental": Cine(minor=False, ostinato=False, taiko=False, braam=False, piano=True, room=0.6),
    "festival": Cine(minor=False, ostinato=False, taiko=False, braam=False, choir=False, festival=True, room=0.3),
    "misterio": Cine(tick=True, choir=False, ostinato=False, room=0.6),
}


# ---- Tablas de onda ----

@lru_cache(maxsize=None)
def _table(kind: str) -> np.ndarray:
    ph = np.arange(TABLE) / TABLE
    out = np.zeros(TABLE)
    if kind.startswith("saw"):  # sierra con N armónicos (más armónicos = más brillo)
        n = int(kind[3:])
        for k in range(1, n + 1):
            out += np.sin(2 * np.pi * k * ph) / k
    elif kind == "aah":  # coro: sierra con formantes de la vocal «a»
        for k in range(1, 40):
            f = 220 * k
            amp = sum(g * math.exp(-((f - c) / w) ** 2) for c, w, g in ((750, 180, 1.0), (1200, 220, 0.6),
                                                                       (2600, 400, 0.25)))
            out += (0.15 / k + amp / k ** 0.5) * np.sin(2 * np.pi * k * ph)
    elif kind == "brass":
        for k in range(1, 18):
            out += np.sin(2 * np.pi * k * ph) / k ** 0.85
    elif kind == "square":
        for k in range(1, 24, 2):
            out += np.sin(2 * np.pi * k * ph) / k
    return out / np.max(np.abs(out))


def _osc(kind: str, hz, n: int, phase: float = 0.0) -> np.ndarray:
    f = np.broadcast_to(np.asarray(hz, float), (n,))
    ph = (phase + np.cumsum(f) / RATE) % 1.0
    return _table(kind)[(ph * TABLE).astype(np.int32) % TABLE]


def _env(n: int, a: float, r: float, hold_decay: float = 0.0) -> np.ndarray:
    t = np.arange(n) / RATE
    dur = n / RATE
    e = np.clip(t / max(a, 1e-4), 0, 1)
    if hold_decay:
        e = e * np.exp(-np.maximum(0, t - a) * hold_decay)
    return e * np.clip((dur - t) / max(r, 1e-4), 0, 1)


def _hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


@lru_cache(maxsize=512)
def ensemble(m: int, sec: float, bright: int = 12, voices: int = 5, a: float = 0.5) -> np.ndarray:
    """Cuerdas (o supersaw): varias sierras desafinadas que crecen poco a poco."""
    n = int(sec * RATE)
    hz = _hz(m)
    out = np.zeros(n)
    spread = np.linspace(-1, 1, voices)
    rng = np.random.default_rng(m)
    t = np.arange(n) / RATE
    for k, s in enumerate(spread):
        vib = 1 + 0.0025 * np.sin(2 * np.pi * (5 + 0.4 * k) * t + k)
        harm = max(3, min(bright, int(14000 / hz)))
        out += _osc(f"saw{harm}", hz * (1 + 0.007 * s) * vib, n, rng.random())
    return out / voices * _env(n, a, 0.35)


@lru_cache(maxsize=256)
def choir(m: int, sec: float) -> np.ndarray:
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    out = sum(_osc("aah", _hz(m) * (1 + 0.005 * s) * (1 + 0.004 * np.sin(2 * np.pi * 5.2 * t + s)), n, 0.3 * s)
              for s in (-1, 0, 1))
    return out / 3 * _env(n, 0.8, 0.6)


def staccato(m: int, sec: float) -> np.ndarray:
    n = int(sec * RATE)
    x = _osc(f"saw{max(3, min(14, int(12000 / _hz(m))))}", _hz(m), n) + 0.6 * _osc("saw8", _hz(m) * 1.004, n, 0.4)
    return x * _env(n, 0.008, 0.03, hold_decay=9)


def horn(m: int, sec: float) -> np.ndarray:
    """Trompas: el brillo sube con el ataque, como un metal de verdad."""
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    hz = _hz(m) * (1 + 0.003 * np.sin(2 * np.pi * 5 * t) * np.clip(t - 0.3, 0, 1))
    dark, bright = _osc("saw4", hz, n), _osc("brass", hz, n)
    e = _env(n, 0.12, 0.25)
    return (dark * (1 - e * 0.7) + bright * e * 0.7) * e


def braam(m: int, sec: float) -> np.ndarray:
    """«Braaam»: metales graves (raíz, quinta y octava) que se abren y saturan."""
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    swell = np.clip(t / 0.25, 0, 1) * np.exp(-np.maximum(0, t - 0.5) * 0.8)
    x = sum(g * (_osc("brass", _hz(m + i) * (1 + d), n) + _osc("brass", _hz(m + i) * (1 - d), n, 0.5))
            for i, g, d in ((0, 1.0, 0.004), (7, 0.6, 0.005), (12, 0.5, 0.003), (-12, 0.8, 0.002)))
    sub = np.sin(2 * np.pi * _hz(m - 12) * t) * 0.8
    return np.tanh((x * 0.5 + sub) * 1.8) * swell * 0.55


def piano_note(m: int, sec: float, vel: float = 0.7) -> np.ndarray:
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    hz = _hz(m)
    x = sum((vel ** (k - 1)) / k * np.exp(-t * (1.2 + 0.7 * k)) * np.sin(2 * np.pi * hz * k * (1 + 0.0002 * k * k) * t)
            for k in range(1, 9))
    return x * np.clip(t / 0.002, 0, 1) * np.clip((sec - t) / 0.2, 0, 1) * 0.5


def taiko(rng, strength: float = 1.0) -> np.ndarray:
    """Tambor taiko: parche grave que baja de tono, golpe de la maza y cuerpo."""
    n = int(1.4 * RATE)
    t = np.arange(n) / RATE
    f = 52 + 70 * np.exp(-t * 18)
    body = np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 3.2)
    skin = np.convolve(rng.normal(0, 1, n), np.ones(30) / 30, mode="same") * np.exp(-t * 22) * 0.9
    return np.tanh((body + skin) * 1.4) * strength


def impact(rng) -> np.ndarray:
    """El golpe del tráiler: boom subgrave, crujido y cola larga."""
    n = int(4.0 * RATE)
    t = np.arange(n) / RATE
    f = 30 + 60 * np.exp(-t * 6)
    boom = np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 1.1)
    crack = rng.normal(0, 1, n) * np.exp(-t * 16) * 0.6
    metal = sum(np.sin(2 * np.pi * h * t) for h in (311, 467, 733, 1171)) * np.exp(-t * 2.5) * 0.08
    return np.tanh((boom * 1.5 + crack + metal) * 1.2)


def _stft_filter(x: np.ndarray, gains) -> np.ndarray:
    """Filtro que cambia con el tiempo: `gains(frame, freqs)` da la ganancia de cada frecuencia en cada trozo."""
    win, hop = 2048, 512
    w = np.hanning(win)
    pad = np.concatenate([np.zeros(win), x, np.zeros(win)])
    out = np.zeros_like(pad)
    norm = np.zeros_like(pad)
    freqs = np.fft.rfftfreq(win, 1 / RATE)
    frames = (len(pad) - win) // hop
    for i in range(frames):
        s = i * hop
        spec = np.fft.rfft(pad[s:s + win] * w) * gains(i / max(1, frames - 1), freqs)
        out[s:s + win] += np.fft.irfft(spec, win) * w
        norm[s:s + win] += w ** 2
    return (out / np.maximum(norm, 1e-6))[win:win + len(x)]


def riser(sec: float, rng) -> np.ndarray:
    """Subida: ruido con un filtro que se abre y un tono que sube una octava; acaba en seco."""
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    noise = _stft_filter(rng.normal(0, 1, n),
                         lambda p, f: np.exp(-0.5 * ((f - (300 + 9000 * p ** 2)) / (400 + 2500 * p)) ** 2))
    tone = _osc("saw10", 110 * 2 ** (2 * t / sec), n) * 0.25
    return (noise / max(1e-6, np.max(np.abs(noise))) * 0.7 + tone) * (t / sec) ** 2.2


def reverse_cymbal(sec: float, rng) -> np.ndarray:
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    hiss = np.diff(np.diff(rng.normal(0, 1, n + 2)))
    return hiss / max(1e-6, np.max(np.abs(hiss))) * np.exp((t - sec) * 3.2) * 0.5


def cymbal(rng) -> np.ndarray:
    return reverse_cymbal(2.5, rng)[::-1].copy()


def tick(rng) -> np.ndarray:
    n = int(0.03 * RATE)
    t = np.arange(n) / RATE
    return np.diff(rng.normal(0, 1, n + 1)) * np.exp(-t * 300) * 0.4 + np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 200) * 0.2


def kick(rng) -> np.ndarray:
    n = int(0.4 * RATE)
    t = np.arange(n) / RATE
    f = 45 + 120 * np.exp(-t * 35)
    return np.tanh(np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 6) * 2.0) * 0.9


def clap(rng) -> np.ndarray:
    n = int(0.25 * RATE)
    t = np.arange(n) / RATE
    noise = np.diff(rng.normal(0, 1, n + 1))
    bursts = sum(np.exp(-np.maximum(0, t - d) * 55) * (t >= d) for d in (0, 0.01, 0.021))
    return noise / 4 * bursts * np.exp(-t * 8)


def _reverb(x: np.ndarray, amount: float, rng, seconds: float = 3.2) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    ir = rng.normal(0, 1, n) * np.exp(-t * 6.9 / seconds)
    ir = np.convolve(ir, np.ones(8) / 8, mode="same")
    ir[: int(0.02 * RATE)] = 0
    ir /= np.sqrt(np.sum(ir ** 2))
    size = 1 << int(len(x) + n).bit_length()
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)] * amount


def _put(buf: np.ndarray, snd: np.ndarray, at: float, gain: float = 1.0) -> None:
    i = int(at * RATE)
    if i < 0 or i >= len(buf):
        return
    piece = snd[: len(buf) - i] * gain
    buf[i:i + len(piece)] += piece


QUAL = {"m": (0, 3, 7), "": (0, 4, 7)}
ROOTS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11, "Bb": 10, "Eb": 3, "Ab": 8}


def _chord(sym: str) -> tuple[int, list[int]]:
    root = sym[:2] if len(sym) > 1 and sym[1] == "b" else sym[:1]
    r = 48 + ROOTS[root]
    return r, [r + i for i in QUAL["m" if sym.endswith("m") else ""]]


def render(preset: str, bpm: int, chords: tuple[str, ...], duration: float, seed: int = 0,
           drop_at: float | None = None) -> np.ndarray:
    """Estéreo (n, 2) en [-1, 1]: la pieza entera, con el golpe en `drop_at` (o hacia el 30 % si no se pide)."""
    c = PRESETS[preset]
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    bar = beat * 4
    step = beat / 4
    offset = 0.0
    if drop_at and drop_at > 0:
        drop_bar = max(1, math.ceil(drop_at / bar))
        offset = drop_bar * bar - drop_at
    else:
        drop_bar = None
    bars = max(4, math.ceil((duration + offset + 0.5) / bar))
    if drop_bar is None:
        drop_bar = max(2, round(bars * 0.3))
    total = bars * bar + 4.5
    dry = np.zeros(int(total * RATE))
    wet = np.zeros_like(dry)  # lo que va a la sala grande
    drop_t = drop_bar * bar
    melody = [0, 2, 4, 7, 4, 2, 0, -1] if not c.minor else [0, 3, 2, 0, 7, 5, 3, 2]
    for b in range(bars):
        t0 = b * bar
        root, notes = _chord(chords[b % len(chords)])
        before = b < drop_bar
        last_bar = b == bars - 1
        # Zumbido grave y cuerdas largas todo el rato; en la entrada, más bajo.
        level = 0.45 if before else 1.0
        if not c.festival:
            _put(dry, np.sin(2 * np.pi * _hz(root - 12) * np.arange(int((bar + 0.5) * RATE)) / RATE)
                 * _env(int((bar + 0.5) * RATE), 0.4, 0.4) * 0.25, t0, level)
            for m in notes:
                _put(wet, ensemble(m + 12, round(bar + 0.6, 3), 10 if before else 14), t0, 0.16 * level)
        if c.choir and not before:
            for m in notes:
                _put(wet, choir(m + 24, round(bar + 0.6, 3)), t0, 0.13)
        if c.piano and (before or b % 2 == 0):
            for k, s in enumerate((0, 1.5, 2.5) if before else (0, 2)):
                m = notes[(k + b) % 3] + 24
                _put(wet, piano_note(m, beat * 3, 0.6), t0 + s * beat, 0.4)
        if c.pulse:
            open_ = min(1.0, (b + 1) / drop_bar) if before else 1.0
            harm = 2 + int(14 * open_)
            for s in range(8):
                n = int(beat / 2 * 0.8 * RATE)
                _put(dry, _osc(f"saw{harm}", _hz(root - (0 if s % 2 else 12)), n) * _env(n, 0.005, 0.05, 6),
                     t0 + s * beat / 2, 0.22)
        if c.tick:
            for s in range(8):
                _put(dry, tick(rng), t0 + s * beat / 2, 0.8 if s % 2 == 0 else 0.5)
            if before:  # latido
                _put(dry, kick(rng), t0, 0.5)
                _put(dry, kick(rng), t0 + beat * 0.6, 0.35)
        if c.festival:
            hpf = before
            for s in range(4):
                if not before:
                    _put(dry, kick(rng), t0 + s * beat, 1.0)
                for m in notes:  # acordes a contratiempo
                    snd = ensemble(m + 24, round(beat * 0.45, 3), 6 if hpf else 18, 7, 0.005)
                    _put(wet if hpf else dry, snd, t0 + s * beat + beat / 2, 0.3 if hpf else 0.12)
            if not before:
                _put(dry, clap(rng), t0 + beat, 0.9)
                _put(dry, clap(rng), t0 + 3 * beat, 0.9)
                for s in range(4):
                    n = int(beat * 0.9 * RATE)
                    tt = np.arange(n) / RATE
                    sub = np.tanh(np.sin(2 * np.pi * _hz(root - 12) * tt) * 1.5) * np.clip((tt - 0.06) / 0.1, 0, 1)
                    _put(dry, sub * _env(n, 0.005, 0.05), t0 + s * beat, 0.5)
        if not before:
            if c.ostinato:
                pat = [0, 0, 12, 0, 7, 0, 12, 0, 0, 0, 12, 0, 7, 0, 3 if c.minor else 4, 0]
                for s, i in enumerate(pat):
                    _put(dry, staccato(root + i, step * 0.95), t0 + s * step, 0.13 if s % 4 else 0.18)
            if c.taiko:
                for s, g in ((0, 1.0), (6, 0.6), (8, 0.9), (11, 0.5), (12, 0.8), (14, 0.6)):
                    _put(dry, taiko(rng, g), t0 + s * step + rng.normal(0, 0.004), 0.55)
                if (b - drop_bar) % 4 == 0:
                    _put(wet, cymbal(rng), t0, 0.35)
            if c.braam and (b - drop_bar) % 2 == 0:
                _put(wet, braam(root - 12, bar * 1.8), t0, 0.5)
            if c.horns:
                for k in range(4):
                    deg = melody[(k + 4 * b) % len(melody)]
                    scale = [0, 2, 4, 5, 7, 9, 11, 12] if not c.minor else [0, 2, 3, 5, 7, 8, 10, 12]
                    m = root + 12 + (scale[deg % 7] + 12 * (deg // 7) if deg >= 0 else -1)
                    _put(wet, horn(m, beat * 1.1), t0 + k * beat, 0.22)
        # La subida: riser y redoble en los dos compases antes del golpe, y un silencio de un instante.
        if b == drop_bar - 2 or (drop_bar == 1 and b == 0):
            length = drop_t - t0 - 0.12
            _put(wet, riser(length, rng), t0, 0.35)
            _put(wet, reverse_cymbal(min(length, 2.5), rng), drop_t - 0.12 - min(length, 2.5), 0.5)
            hits = 24
            for k in range(hits):  # redoble que acelera
                at = t0 + length * (1 - (1 - k / hits) ** 1.6)
                drum = taiko(rng, 0.25 + 0.6 * k / hits) if not c.festival else clap(rng) * (0.3 + 0.7 * k / hits)
                _put(dry, drum, at, 0.45)
        if last_bar:
            _put(dry, impact(rng), t0 + bar - beat, 0.6)
    # Silencio de un instante justo antes del golpe y el golpe en `drop_t`.
    gap = slice(int((drop_t - 0.12) * RATE), int(drop_t * RATE))
    dry[gap] *= np.linspace(1, 0.05, gap.stop - gap.start)
    wet[gap] *= np.linspace(1, 0.05, gap.stop - gap.start)
    hit = impact(rng)
    _put(dry, hit, drop_t, 0.9)
    _put(wet, hit, drop_t, 0.5)
    if c.festival:  # bombeo: todo lo melódico se agacha en cada bombo tras el golpe
        t = (np.arange(len(dry)) / RATE - drop_t) % beat
        pump = np.where(np.arange(len(dry)) / RATE >= drop_t, 0.25 + 0.75 * np.clip(t / (beat * 0.55), 0, 1), 1.0)
        wet *= pump
    left = dry + wet + _reverb(wet, c.room, rng) + _reverb(dry, 0.1, rng, 1.6)
    right = dry + wet + _reverb(wet, c.room, rng) + _reverb(dry, 0.1, rng, 1.6)
    out = np.stack([left, right], axis=1)
    n_end = int((bars * bar + 2.5) * RATE)
    out = out[int(offset * RATE):n_end]
    fade = int(1.5 * RATE)
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    out[: int(0.05 * RATE)] *= np.linspace(0, 1, int(0.05 * RATE))[:, None]
    return np.tanh(out / max(1e-6, float(np.max(np.abs(out)))) * 1.6) * 0.85
