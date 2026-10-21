"""Efectos en pantalla: lista animada, palabra gigante y zoom de énfasis.

La IA los describe con índices de palabras de la transcripción original; aquí
se convierten a tiempos del reel ya cortado y a eventos ASS.
"""

from __future__ import annotations

from dataclasses import dataclass

from .captions import H, W, Style, _esc, _ts
from .models import Span, Word

LISTA = "lista"
PALABRA = "palabra"

# Cuadrado redondeado de 90×90 en dibujo ASS.
_BOX = "m 20 0 l 90 0 b 101 0 110 9 110 20 l 110 90 b 110 101 101 110 90 110 l 20 110 b 9 110 0 101 0 90 l 0 20 b 0 9 9 0 20 0"
_SCREEN = f"m 0 0 l {W} 0 {W} {H} 0 {H}"


@dataclass
class Window:
    start: float
    end: float


class WordClock:
    """Tiempo en el reel de cada palabra original (o de la siguiente que sobrevive)."""

    def __init__(self, kept: list[Word], kept_idx: list[int]):
        self.kept = kept
        self.kept_idx = kept_idx

    def at(self, orig_idx: int) -> float | None:
        for w, i in zip(self.kept, self.kept_idx):
            if i >= orig_idx:
                return w.start
        return None

    def end_of(self, orig_idx: int) -> float | None:
        best = None
        for w, i in zip(self.kept, self.kept_idx):
            if i <= orig_idx:
                best = w.end
            else:
                break
        return best


def _dim(start: float, end: float, alpha: str = "60") -> str:
    return (
        f"Dialogue: 3,{_ts(start)},{_ts(end)},Sub,,0,0,0,,"
        f"{{\\an7\\pos(0,0)\\bord0\\shad0\\1c&H000000&\\1a&H{alpha}&\\fad(150,150)\\p1}}{_SCREEN}"
    )


def lista_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    items = [it for it in effect.get("items", []) if it.get("text")][:5]
    if not items:
        return [], None
    times = [clock.at(int(it.get("at_word", 0))) for it in items]
    if any(t is None for t in times):
        return [], None
    start = times[0]
    end_idx = effect.get("until_word")
    end = clock.end_of(int(end_idx)) if end_idx is not None else None
    end = min(duration, max(end or times[-1] + 2.0, times[-1] + 1.2))
    lines = [_dim(start, end)]
    title = effect.get("title", "").strip()
    n = len(items)
    top = 960 - (n * 150) // 2 + (50 if title else 0)
    if title:
        t = _esc(title.upper())
        lines.append(
            f"Dialogue: 4,{_ts(start)},{_ts(end)},Sub,,0,0,0,,"
            f"{{\\an4\\pos(100,{top - 130})\\fs64\\bord0\\shad0\\c{style.accent}&\\fad(150,150)}}{t}"
        )
    for k, (it, t0) in enumerate(zip(items, times)):
        y = top + k * 150
        nxt = times[k + 1] if k + 1 < n else end
        text = _esc(it["text"])
        # Activo mientras se habla de él; después se queda atenuado.
        for a, b, alpha, glow in ((t0, nxt, "00", True), (nxt, end, "70", False)):
            if b - a <= 0.02:
                continue
            pop = r"\fscx70\fscy70\t(0,140,\fscx100\fscy100)" if glow else ""
            box_c = style.accent if glow else "&H00505050"
            lines.append(
                f"Dialogue: 4,{_ts(a)},{_ts(b)},Sub,,0,0,0,,"
                f"{{\\an7\\pos(100,{y - 55})\\bord0\\shad0\\1c{box_c}&\\1a&H{alpha}&{pop}\\p1}}{_BOX}"
            )
            lines.append(
                f"Dialogue: 5,{_ts(a)},{_ts(b)},Sub,,0,0,0,,"
                f"{{\\an5\\pos(155,{y})\\fs72\\bord0\\shad0\\c&H00141518&\\alpha&H{alpha}&}}{k + 1}"
            )
            lines.append(
                f"Dialogue: 5,{_ts(a)},{_ts(b)},Sub,,0,0,0,,"
                f"{{\\an4\\pos(250,{y})\\fs84\\bord3\\shad0\\alpha&H{alpha}&{pop}}}{text}"
            )
    return lines, Window(start, end)


def palabra_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    idx = effect.get("word")
    if idx is None:
        return [], None
    start = clock.at(int(idx))
    if start is None:
        return [], None
    end = min(duration, start + float(effect.get("seconds", 1.0)))
    text = _esc(str(effect.get("text", "")).strip() or "")
    if not text:
        w = next((w for w, i in zip(clock.kept, clock.kept_idx) if i >= int(idx)), None)
        text = _esc(w.text if w else "")
    text = text.upper() if style.uppercase else text
    size = 230 if len(text) <= 7 else 170 if len(text) <= 11 else 120
    return [
        _dim(start, end, "50"),
        f"Dialogue: 6,{_ts(start)},{_ts(end)},Sub,,0,0,0,,"
        f"{{\\an5\\pos(540,960)\\fs{size}\\bord6\\shad0\\c{style.accent}&\\fad(0,120)"
        f"\\fscx40\\fscy40\\t(0,130,\\fscx112\\fscy112)\\t(130,220,\\fscx100\\fscy100)}}{text}",
    ], Window(start, end)


def build_effects(effects: list[dict], clock: WordClock, style: Style, duration: float) -> tuple[list[str], list[Window]]:
    lines: list[str] = []
    windows: list[Window] = []
    for fx in effects or []:
        kind = fx.get("type")
        if kind == LISTA:
            ev, win = lista_events(fx, clock, style, duration)
        elif kind == PALABRA:
            ev, win = palabra_events(fx, clock, style, duration)
        else:
            continue
        lines += ev
        if win:
            windows.append(win)
    return lines, windows


def zoom_flags(spans: list[Span], words: list[Word], zooms: list[tuple[int, int]], auto: bool) -> list[bool]:
    """Qué tramos van con zoom.

    - `auto`: alterna plano normal y plano cerrado en cada corte, el truco
      clásico para que los saltos no se noten.
    - `zooms`: rangos de palabras que la IA quiere enfatizar.
    """
    flags = []
    cut = 0
    for i, sp in enumerate(spans):
        if i and abs(spans[i - 1].end - sp.start) > 1e-3:
            cut += 1
        flags.append(auto and cut % 2 == 1)
    for a, b in zooms or []:
        if not (0 <= a <= b < len(words)):
            continue
        s, e = words[a].start, words[b].end
        for i, sp in enumerate(spans):
            if sp.start < e and sp.end > s:
                flags[i] = True
    return flags


def split_spans(spans: list[Span], words: list[Word], zooms: list[tuple[int, int]]) -> list[Span]:
    """Parte los tramos en los bordes de cada zoom para que el zoom dure lo justo."""
    cuts = set()
    for a, b in zooms or []:
        if 0 <= a <= b < len(words):
            cuts.add(round(max(0.0, words[a].start - 0.05), 3))
            cuts.add(round(words[b].end + 0.1, 3))
    out: list[Span] = []
    for sp in spans:
        points = sorted(c for c in cuts if sp.start + 0.15 < c < sp.end - 0.15)
        start = sp.start
        for c in points:
            out.append(Span(start, c))
            start = c
        out.append(Span(start, sp.end))
    return out
