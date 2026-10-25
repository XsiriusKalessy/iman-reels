"""Efectos de sonido sintetizados: whoosh, riser, impact, pop, clic, teclado y aire.

Los generamos nosotros con matemáticas (ruido filtrado, senos que barren), así que son nuestros y
se pueden usar en reels comerciales sin licencias. Se mezclan en una sola pista ("cama") con los
sonidos colocados en su instante, que luego ffmpeg suma a la voz.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

RATE = 48000
_rng = np.random.default_rng(7)  # misma semilla: el mismo reel suena igual cada vez


def _env(n: int, attack: float, release: float) -> np.ndarray:
    t = np.linspace(0, 1, n, endpoint=False)
    return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-np.maximum(0, t - attack) / max(release, 1e-4))


def _lowpass(x: np.ndarray, cutoff: np.ndarray | float) -> np.ndarray:
    """Filtro paso bajo de un polo; `cutoff` en Hz puede cambiar muestra a muestra (barrido)."""
    c = np.broadcast_to(np.asarray(cutoff, dtype=float), x.shape)
    a = 1 - np.exp(-2 * np.pi * c / RATE)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):  # corto: menos de un segundo
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def _noise(sec: float) -> np.ndarray:
    return _rng.uniform(-1, 1, int(sec * RATE))


def whoosh(sec: float = 0.55) -> np.ndarray:
    n = int(sec * RATE)
    t = np.linspace(0, 1, n, endpoint=False)
    swell = np.sin(np.pi * t) ** 1.6
    cutoff = 300 + 5200 * np.sin(np.pi * t) ** 2
    return _lowpass(_noise(sec), cutoff) * swell * 2.2


def riser(sec: float = 1.1) -> np.ndarray:
    n = int(sec * RATE)
    t = np.linspace(0, sec, n, endpoint=False)
    f = 180 * (8 ** (t / sec))  # sube tres octavas
    tone = np.sin(2 * np.pi * np.cumsum(f) / RATE) * 0.35
    air = _lowpass(_noise(sec), 400 + 6000 * (t / sec) ** 2) * 1.4
    return (tone + air) * (t / sec) ** 2


def impact(sec: float = 0.9) -> np.ndarray:
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    f = 40 + 70 * np.exp(-t * 18)  # golpe grave que cae
    boom = np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 4.5)
    hit = _lowpass(_noise(sec), 2500) * np.exp(-t * 40) * 1.5
    return (boom + hit) * 0.95


def metal(sec: float = 0.5) -> np.ndarray:
    """Textura metálica: parciales inarmónicos que se apagan rápido (como un golpe en una chapa)."""
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    base = _rng.uniform(380, 520)
    out = sum(np.sin(2 * np.pi * base * r * t + _rng.uniform(0, 6)) * np.exp(-t * d)
              for r, d in ((1.0, 9), (2.76, 12), (5.40, 16), (8.93, 22)))
    return out * 0.18


def _echo(x: np.ndarray, delay: float = 0.11, feedback: float = 0.42, taps: int = 4) -> np.ndarray:
    d = int(delay * RATE)
    out = np.concatenate([x, np.zeros(d * taps)])
    for k in range(1, taps + 1):
        out[d * k:d * k + len(x)] += _lowpass(x, 3500 / k) * feedback ** k
    return out


def hit(sec: float = 1.2) -> np.ndarray:
    """Impacto por capas: sub-bass + whoosh que llega + chapa + cola de eco. Cada uno sale distinto."""
    shift = _rng.uniform(0.85, 1.15)  # un poco de tono distinto en cada golpe
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    sub = np.sin(2 * np.pi * np.cumsum((32 + 50 * np.exp(-t * 14)) * shift) / RATE) * np.exp(-t * 3.2)
    lead = whoosh(0.3)[::-1] * 0.5  # el aire llega justo antes del golpe y se corta en él
    body = impact(0.5) * 0.7
    out = np.zeros(n + len(lead))
    i = len(lead)
    out[:len(lead)] += lead
    out[i:i + n] += sub
    out[i:i + len(body)] += body
    m = metal()
    out[i:i + len(m)] += m
    out = _echo(out)
    return out / max(1.0, float(np.max(np.abs(out)))) * 0.95


# El golpe por capas lleva el whoosh delante: suena antes, para que el golpe caiga en su instante.
LEAD = {"hit": 0.3}


def pop(sec: float = 0.09) -> np.ndarray:
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    f = 900 * np.exp(-t * 25) + 250
    return np.sin(2 * np.pi * np.cumsum(f) / RATE) * _env(n, 0.03, 0.35) * 0.8


def click(sec: float = 0.03) -> np.ndarray:
    n = int(sec * RATE)
    return (_noise(sec) * np.exp(-np.arange(n) / RATE * 300) + np.sin(2 * np.pi * 3200 * np.arange(n) / RATE)
            * np.exp(-np.arange(n) / RATE * 500) * 0.5) * 0.6


def keyboard(sec: float = 1.2) -> np.ndarray:
    out = np.zeros(int(sec * RATE))
    t = 0.0
    while t < sec - 0.05:
        c = click() * _rng.uniform(0.5, 1.0)
        i = int(t * RATE)
        out[i:i + len(c)] += c[: len(out) - i]
        t += _rng.uniform(0.06, 0.16)
    return out * 0.7


def air(sec: float = 0.4) -> np.ndarray:
    n = int(sec * RATE)
    t = np.linspace(0, 1, n, endpoint=False)
    return _lowpass(_noise(sec), 1500 + 2500 * t) * np.sin(np.pi * t) ** 2 * 1.2


SOUNDS = {"whoosh": whoosh, "riser": riser, "impact": impact, "pop": pop, "click": click, "keyboard": keyboard,
          "air": air, "metal": metal, "hit": hit}
# Cada vez que suenan, se generan de nuevo (con variación) en vez de repetir el mismo archivo.
VARIED = {"hit", "whoosh", "air"}

# Qué suena cuando aparece cada efecto.
FOR_EFFECT = {
    "palabra": "hit", "cifra": "hit", "color": "impact", "choque": "hit", "detras": "impact",
    "titular": "whoosh", "portada": "whoosh", "pagina": "whoosh", "fondo": "whoosh", "desenfoque": "air",
    "frase": "air", "fantasma": "air", "bruto": "whoosh", "contador": "riser",
    "ubicacion": "pop", "dato": "pop", "objeto": "pop", "plazas": "pop", "precio": "pop", "oferta": "pop",
    "testimonio": "pop", "comentario": "pop", "cta": "click", "aparece": "pop", "sube": "riser",
    "ruta": "whoosh", "viaje": "whoosh", "notificaciones": "pop", "foco": "riser", "anillo": "whoosh", "buscador": "keyboard", "chat": "pop", "grafico": "riser", "texto3d": "impact", "etiqueta": "pop", "tarjetas": "whoosh", "particulas": "riser", "bloques": "click", "pexels": "whoosh", "lluvia": "riser", "capitulo": "whoosh", "captura": "whoosh", "collage": "whoosh", "apoyo": "whoosh", "tecleo": "keyboard",
}


def bed(events: list[tuple[float, str, float]], duration: float, dst: Path) -> Path:
    """Pista con los sonidos en su sitio: `events` son (segundo, sonido, volumen de 0 a 1)."""
    out = np.zeros(int((duration + 0.05) * RATE))
    cache: dict[str, np.ndarray] = {}
    for at, name, gain in events:
        if name not in SOUNDS or at >= duration:
            continue
        snd = SOUNDS[name]() if name in VARIED else cache.setdefault(name, SOUNDS[name]())
        i = int((at - LEAD.get(name, 0.0)) * RATE)
        if i < 0:  # al principio del reel no hay sitio para la entrada: el golpe cae igual en su instante
            snd, i = snd[-i:], 0
        piece = snd[: len(out) - i] * gain
        out[i:i + len(piece)] += piece
    peak = float(np.max(np.abs(out))) or 1.0
    out = out / max(1.0, peak) * 0.9
    dst.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((out * 32767).astype("<i2").tobytes())
    return dst
