"""Efectos que reaccionan a tus manos: la palabra que sube con tu dedo, el choque y lo que dices aparece.

Las manos se buscan en la toma original (hands.py); aquí se pasan a tiempos y posiciones del reel
ya cortado y encuadrado, se proponen efectos donde señalas y se dibujan en ASS. Si no se ven las
manos (o no está el modelo), cada efecto sale igual con una animación por defecto.
"""

from __future__ import annotations

import re

from . import media, textfit
from .captions import H, W, Style, _esc, _ts
from .effects import Window, WordClock, _accent, _dim, _span
from .hands import Gesture, gestures, near  # noqa: F401  (gestures se usa desde pipeline)
from .models import Span, Word
from .rhythm import is_filler

HAND_TYPES = ("sube", "choque", "aparece")
CHOQUE_FONT = "Montserrat Black"


def _to_reel(u: float, v: float, zoomed: bool, info: media.MediaInfo, fit: str) -> tuple[float, float]:
    """Punto 0-1 de la toma → punto 0-1 del reel vertical (mismo encuadre que media.build_filtergraph)."""
    if zoomed:
        u, v = .5 + (u - .5) * media.ZOOM, .5 + (v - .5) * media.ZOOM
    w0, h0 = info.width, info.height
    s = max(W / w0, H / h0) if fit != "fondo" else min(W / w0, H / h0)
    sw, sh = w0 * s, h0 * s
    return (u * sw + (W - sw) / 2) / W, (v * sh + (H - sh) / 2) / H


def reel_frames(frames: list[dict], spans: list[Span], zooms: list[bool], info: media.MediaInfo,
                fit: str = "recortar") -> list[dict]:
    """Las manos de cada fotograma que sobrevive al corte, con el tiempo y la posición del reel."""
    starts, acc = [], 0.0
    for sp in spans:
        starts.append(acc)
        acc += sp.duration
    out = []
    for f in frames:
        for k, sp in enumerate(spans):
            if sp.start <= f["t"] < sp.end:
                hands = [[list(_to_reel(u, v, zooms[k], info, fit)) for u, v in hand] for hand in f["hands"]]
                out.append({"t": round(starts[k] + f["t"] - sp.start, 3), "hands": hands})
                break
    return sorted(out, key=lambda f: f["t"])


_NUM = re.compile(r"\d")
_UNITS = {"euros", "€", "%", "por", "días", "dias", "horas", "minutos", "noches", "personas", "veces", "kilos", "mil"}


def key_text(words: list[Word]) -> str:
    """Lo que merece salir en pantalla de lo que dices mientras haces el gesto: una cifra o la palabra fuerte."""
    clean = [w.text.strip(".,;:!?¡¿\"'«»") for w in words]
    for k, t in enumerate(clean):
        if _NUM.search(t):
            nxt = clean[k + 1] if k + 1 < len(clean) else ""
            return f"{t} {nxt}".strip() if nxt.lower() in _UNITS else t
    best = max((t for i, t in enumerate(clean) if len(t) >= 4 and not is_filler(words, i)), key=len, default="")
    return best


def auto_effects(effects: list[dict], found: list[Gesture], clock: WordClock, limit: int = 3) -> list[dict]:
    """Propone "sube" o "aparece" donde señalas, si la IA no ha puesto ya algo en ese momento."""
    taken = [t for t in (clock.at(int(fx.get("word", -1))) for fx in effects if not fx.get("off")) if t is not None]
    out, added = list(effects), 0
    for g in found:
        if added >= limit or any(g.start - 1.2 <= t <= g.end + 0.6 for t in taken):
            continue
        said = [(w, i) for w, i in zip(clock.kept, clock.kept_idx) if g.start - 0.3 <= w.start <= g.end + 0.3]
        text = key_text([w for w, _ in said])
        if not said or not text:
            continue
        out.append({"type": "sube" if g.kind == "sube" else "aparece", "word": said[0][1], "text": text,
                    "until_word": said[-1][1], "auto": True})
        taken.append(g.start)
        added += 1
    return out


def attach(effects: list[dict], found: list[Gesture], frames: list[dict], clock: WordClock) -> None:
    """Engancha a cada efecto de manos el gesto o el toque que le corresponde (en píxeles del reel)."""
    for fx in effects:
        kind = fx.get("type")
        if kind not in HAND_TYPES:
            continue
        start = clock.at(int(fx.get("word", -1)))
        if start is None:
            continue
        if kind == "choque":
            hit = near(frames, start + 0.3, start + 2.4, (0.08, 0.34, 0.92, 0.52))
            if hit is not None:
                hx = next((h[8][0] for f in frames if f["t"] == hit for h in f["hands"]), 0.5)
                fx["_hit"], fx["_hit_x"] = hit, hx * W
            continue
        g = next((g for g in found if g.start - 0.6 <= start <= g.end + 0.3
                  and (kind == "aparece" or g.kind == "sube")), None)
        if g is None:
            continue
        fx["_path"] = [(t, x * W, y * H) for t, x, y in g.path]
        fx["_dir"] = g.direction


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _text(effect: dict, style: Style) -> str:
    t = str(effect.get("text", "")).strip()
    return _esc(t.upper() if style.uppercase else t)


def sube_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """La palabra sale de la yema del índice y sube con ella."""
    span = _span(effect, clock, duration, 2.0, 1.0)
    text = _text(effect, style)
    if not span or not text:
        return [], None
    start, end = span
    fs = 112 if len(text) <= 8 else 84 if len(text) <= 14 else 64
    look = f"\\an2\\fs{fs}\\bord6\\shad0\\c{_accent(style)}&"
    path = [(t, _clamp(x, 140, W - 140), _clamp(y - 60, 260, H - 300)) for t, x, y in effect.get("_path", [])
            if start - 0.6 <= t <= end + 0.3]
    if len(path) >= 2:
        start, end = path[0][0], min(duration, path[-1][0] + 0.5)
        lines = []
        for k, ((ta, xa, ya), (tb, xb, yb)) in enumerate(zip(path, path[1:])):
            intro = "\\fad(120,0)\\fscx40\\fscy40\\t(0,140,\\fscx100\\fscy100)" if k == 0 else ""
            lines.append(f"Dialogue: 7,{_ts(ta)},{_ts(tb)},Sub,,0,0,0,,"
                         f"{{{look}\\move({xa:.0f},{ya:.0f},{xb:.0f},{yb:.0f}){intro}}}{text}")
        _, xl, yl = path[-1]
        lines.append(f"Dialogue: 7,{_ts(path[-1][0])},{_ts(end)},Sub,,0,0,0,,{{{look}\\pos({xl:.0f},{yl:.0f})\\fad(0,200)}}{text}")
        return lines, Window(start, end)
    # Sin manos a la vista: sube desde abajo hasta el centro.
    ms = int((end - start) * 800)
    return [f"Dialogue: 7,{_ts(start)},{_ts(end)},Sub,,0,0,0,,"
            f"{{{look}\\move(540,1460,540,700,0,{ms})\\fad(150,200)\\fscx50\\fscy50\\t(0,160,\\fscx100\\fscy100)}}{text}"], \
        Window(start, end)


def aparece_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Lo que nombras aparece en una etiqueta justo donde señalas."""
    span = _span(effect, clock, duration, 1.8, 1.0)
    text = _text(effect, style)
    if not span or not text:
        return [], None
    start, end = span
    fs = 84 if len(text) <= 10 else 64 if len(text) <= 16 else 50
    tw = textfit.width(text, style.font, fs) + 56
    th = fs + 34
    path = effect.get("_path") or []
    if path:
        _, x, y = path[0]
        dx, dy = effect.get("_dir", (0.0, -1.0))
        cx, cy = x + dx * 190, y + dy * 190
    else:
        cx, cy = 540, 760
    cx = _clamp(cx, tw / 2 + 40, W - tw / 2 - 40)
    top = 700 if start < 3.0 else 260  # al principio arriba está el gancho: no lo tapamos
    cy = _clamp(cy, top + th / 2, H - 420)
    x0, y0 = cx - tw / 2, cy - th / 2
    pop = "\\fscx30\\fscy30\\t(0,140,\\fscx110\\fscy110)\\t(140,230,\\fscx100\\fscy100)\\fad(0,180)"
    from .effects import _rect

    return [
        f"Dialogue: 7,{_ts(start)},{_ts(end)},Sub,,0,0,0,,{{\\an7\\pos({x0:.0f},{y0:.0f})\\org({cx:.0f},{cy:.0f})"
        f"\\bord0\\shad0\\1c{_accent(style)}&{pop}\\p1}}{_rect(0, 0, tw, th, th / 2)}",
        f"Dialogue: 8,{_ts(start)},{_ts(end)},Sub,,0,0,0,,{{\\an5\\pos({cx:.0f},{cy + 2:.0f})\\fs{fs}\\bord0\\shad0"
        f"\\c&H141518&{pop}}}{text}",
    ], None


def _wobble(k: int) -> float:
    """Pseudoaleatorio estable por letra (el mismo reel sale siempre igual)."""
    return ((k * 7919) % 97) / 96.0


def choque_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Una palabra enorme que salta en pedazos cuando la mano la golpea (o al final, si no la toca)."""
    span = _span(effect, clock, duration, 2.2, 1.2)
    word = str(effect.get("text", "")).strip().upper()
    if not span or not word:
        return [], None
    start, end = span
    hit = float(effect.get("_hit") or (start + 0.65 * (end - start)))
    hit = _clamp(hit, start + 0.3, end)
    hx = float(effect.get("_hit_x") or 540)
    fs = 220 if len(word) <= 6 else 160 if len(word) <= 9 else 112
    widths = [textfit.width(ch, CHOQUE_FONT, fs) for ch in word]
    x, y = 540 - sum(widths) / 2, 830
    fly = 0.6
    look = f"\\an5\\fn{CHOQUE_FONT}\\fs{fs}\\bord7\\shad0\\c&HFFFFFF&\\3c{_accent(style)}&"
    lines = [_dim(start, hit + fly, "55")]
    for k, (ch, w) in enumerate(zip(word, widths)):
        cx = x + w / 2
        x += w
        if not ch.strip():
            continue
        c = _esc(ch)
        lines.append(f"Dialogue: 7,{_ts(start)},{_ts(hit)},Sub,,0,0,0,,{{{look}\\pos({cx:.0f},{y})"
                     f"\\fscx40\\fscy40\\t(0,140,\\fscx108\\fscy108)\\t(140,220,\\fscx100\\fscy100)}}{c}")
        side = 1 if cx >= hx else -1
        dx = side * (160 + 260 * _wobble(k))
        dy = -220 + 640 * _wobble(k + 3)
        rot = side * (25 + 70 * _wobble(k + 5))
        lines.append(f"Dialogue: 7,{_ts(hit)},{_ts(hit + fly)},Sub,,0,0,0,,{{{look}"
                     f"\\move({cx:.0f},{y},{cx + dx:.0f},{y + dy:.0f},0,{int(fly * 1000)})"
                     f"\\t(0,{int(fly * 1000)},\\frz{-rot:.0f})\\fad(0,{int(fly * 600)})}}{c}")
    return lines, Window(start, hit + fly)


GESTURE_BUILDERS = {"sube": sube_events, "aparece": aparece_events, "choque": choque_events}
