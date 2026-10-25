"""Seguimiento de la cabeza para los textos que te siguen (efecto "etiqueta").

Se miran unos fotogramas por segundo de la toma original en el rato del efecto, se busca la cabeza con el
mismo recorte de persona que el resto de Imán y se pasa su posición al encuadre del reel (recorte vertical,
plano cerrado, fondo desenfocado…). Todo local: ni servicios ni modelos nuevos.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

from . import segment
from .media import FFMPEG, ZOOM, MediaInfo, reframe
from .models import Span

W, H = 1080, 1920
RATE = 6  # posiciones por segundo


def source_time(spans: list[Span], t: float) -> tuple[int, float] | None:
    """(tramo, segundo de la toma original) que se ve en el segundo `t` del reel."""
    done = 0.0
    for i, sp in enumerate(spans):
        if t < done + sp.duration:
            return i, sp.start + (t - done)
        done += sp.duration
    return None


def to_reel(x: float, y: float, info: MediaInfo, zoomed: bool, fit: str,
            cx: float | None = None) -> tuple[float, float]:
    """Punto de la toma (0-1) → píxel del reel de 1080x1920 (`cx`: centro del encuadre de ese tramo)."""
    sw, sh = info.width, info.height
    ref = reframe(cx, sw - sw % 2, sh - sh % 2) if cx is not None and fit != "fondo" else None
    if ref:  # recorte vertical centrado en la cabeza: x pasa a contar dentro del recorte
        x, sw = (x * sw - ref[0]) / ref[1], ref[1]
    if zoomed:  # el plano cerrado es un recorte centrado
        x, y = (x - 0.5) * ZOOM + 0.5, (y - 0.5) * ZOOM + 0.5
    if fit == "fondo":
        fh = W * sh / sw
        return x * W, (H - fh) / 2 + y * fh
    k = max(W / sw, H / sh)
    return x * sw * k - (sw * k - W) / 2, y * sh * k - (sh * k - H) / 2


def _frame(src: Path, t: float):
    from PIL import Image

    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(src), "-frames:v", "1",
                          "-vf", "scale=360:-2", "-f", "image2", "-c:v", "png", "-"], capture_output=True).stdout
    return Image.open(io.BytesIO(raw)) if raw else None


def framing(src: Path, info: MediaInfo, spans: list[Span]) -> list[float] | None:
    """Centro x (0-1) del encuadre de cada tramo para vídeos horizontales: donde está tu cabeza.

    Encuadre que casa (match cut): si entre un tramo y el siguiente te has movido poco, se deja el mismo
    encuadre para que el corte no "salte"; si te has movido de verdad, el encuadre te sigue."""
    if reframe(0.5, info.width - info.width % 2, info.height - info.height % 2) is None or not segment.available():
        return None
    # Un fotograma por tramo (como mucho 40, repartidos) y se rellena el resto con el más cercano.
    picks = sorted({round(i * (len(spans) - 1) / 39) for i in range(40)}) if len(spans) > 40 else range(len(spans))
    seen = {}
    for i in picks:
        img = _frame(src, (spans[i].start + spans[i].end) / 2)
        got = segment.subject(img) if img is not None else None
        if got:
            seen[i] = got[0]
    if not seen:
        return None
    out, cur = [], None
    for i in range(len(spans)):
        want = seen.get(i, seen[min(seen, key=lambda k: abs(k - i))])
        if cur is None or abs(want - cur) > 0.06:
            cur = want
        out.append(cur)
    return out


def track(src: Path, info: MediaInfo, spans: list[Span], zooms: list[bool], fit: str,
          start: float, end: float, frames: list[float] | None = None) -> list[tuple[float, float, float]]:
    """[(segundo del reel, x, y de la coronilla en píxeles del reel)], suavizado. Vacío si no hay nadie."""
    if not segment.available():
        return []
    pts = []
    n = max(2, int((end - start) * RATE) + 1)
    for k in range(n):
        t = start + (end - start) * k / (n - 1)
        where = source_time(spans, t)
        img = _frame(src, where[1]) if where else None
        got = segment.subject(img) if img is not None else None
        if got:
            i = where[0]
            x, y = to_reel(got[0], got[1], info, zooms[i] if i < len(zooms) else False, fit,
                           frames[i] if frames and i < len(frames) else None)
            pts.append((t, x, y))
    if len(pts) < max(2, n // 2):
        return []
    # Media móvil de 3: sin tirones cuando el recorte de un fotograma sale un poco distinto.
    out = []
    for i, (t, _, _) in enumerate(pts):
        near = pts[max(0, i - 1):i + 2]
        out.append((t, sum(p[1] for p in near) / len(near), sum(p[2] for p in near) / len(near)))
    return out
