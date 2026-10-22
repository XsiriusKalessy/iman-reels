"""Efectos en pantalla: lista animada, palabra gigante y zoom de énfasis.

La IA los describe con índices de palabras de la transcripción original; aquí
se convierten a tiempos del reel ya cortado y a eventos ASS.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import textfit
from .captions import H, W, Style, _esc, _ts, rgb
from .models import Span, Word

LISTA = "lista"
PALABRA = "palabra"
TITULAR = "titular"
CIFRA = "cifra"
FRASE = "frase"
TECLEO = "tecleo"
HAND = "Caveat"  # letra manuscrita

# Cajas de titular: (fondo, texto, remate manuscrito, fuente del texto)
LOOKS = {
    "revista": ("#F4ECDF", "#141518", "#D2372B", "Playfair Display ExtraBold"),
    "elegante": ("#1F3D33", "#F4ECDF", "#F4ECDF", "Playfair Display ExtraBold"),
    "pizarra": ("#141518", "#FFFFFF", None, "Montserrat Black"),
}

# Cuadrado redondeado de 90×90 en dibujo ASS.
_BOX = "m 20 0 l 90 0 b 101 0 110 9 110 20 l 110 90 b 110 101 101 110 90 110 l 20 110 b 9 110 0 101 0 90 l 0 20 b 0 9 9 0 20 0"
_SCREEN = f"m 0 0 l {W} 0 {W} {H} 0 {H}"


@dataclass
class VideoOp:
    """Efecto que necesita mezclar vídeo (lo pinta ffmpeg, no el ASS)."""
    kind: str
    start: float
    end: float
    src_start: float = 0.0
    path: str = ""  # imagen que se superpone (logo)
    color: str = ""  # fondo liso (cierre de marca)


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
    if effect.get("look") in ("checklist", "capitulos"):
        return checklist_events(effect, clock, style, duration)
    if effect.get("look") == "itinerario":
        from .packfx import itinerario_events

        return itinerario_events(effect, clock, style, duration)
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
            f"{{\\an4\\pos(100,{top - 130})\\fs64\\bord0\\shad0\\c{_accent(style)}&\\fad(150,150)}}{t}"
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
            box_c = _accent(style) if glow else "&H00505050"
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


_TICK = "m 14 40 l 26 28 l 40 42 l 70 12 l 82 24 l 40 66 l 14 40"


def _card(t: str, x: float, y: float, w: float, h: float, label: str, accent: str) -> list[str]:
    """Tarjeta oscura con etiqueta de color, la base de checklist y tecleo."""
    out = [f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7\\pos({x:.0f},{y:.0f})\\bord0\\shad0\\1c{rgb('#17171C')}&"
           f"\\1a&H10&\\fad(150,200)\\p1}}{_rect(0, 0, w, h, 22)}"]
    if label:
        out.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an7\\pos({x + 36:.0f},{y + 24:.0f})\\fnFigtree ExtraBold\\fs44"
                   f"\\bord0\\shad0\\c{accent}&\\fad(150,200)}}{_esc(label.upper())}")
    return out


def checklist_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Lista de casillas arriba que se van marcando según se nombra cada punto."""
    items = [it for it in effect.get("items", []) if it.get("text")][:6]
    times = [clock.at(int(it.get("at_word", 0))) for it in items]
    if len(items) < 2 or any(t is None for t in times):
        return [], None
    start = max(0.0, times[0] - 0.4)
    end_idx = effect.get("until_word")
    end = clock.end_of(int(end_idx)) if end_idx is not None else None
    end = min(duration, max(end or times[-1] + 1.8, times[-1] + 1.2))
    title = effect.get("title", "").strip()
    row_h, fs = 108, 74
    w = max(textfit.width(it["text"], "Figtree ExtraBold", fs) for it in items) + 210
    w = min(max(w, 560), 960)
    h = len(items) * row_h + (96 if title else 40)
    x, y = (W - w) / 2, 260
    t = f"{_ts(start)},{_ts(end)}"
    lines = _card(t, x, y, w, h, title, _accent(style))
    top = y + (90 if title else 26)
    if effect.get("look") == "capitulos":
        return lines + _chapters(items, times, x, top, row_h, fs, start, end, style), None
    for k, (it, t0) in enumerate(zip(items, times)):
        ry = top + k * row_h
        box = f"\\an7\\pos({x + 36:.0f},{ry + 8:.0f})\\bord0\\shad0"
        # Casilla vacía hasta que se nombra; después, marcada y con el texto encendido.
        lines.append(f"Dialogue: 5,{_ts(start)},{_ts(t0)},Sub,,0,0,0,,{{{box}\\1c&H00FFFFFF&\\1a&HB0&\\fad(150,0)\\p1}}"
                     f"{_rect(0, 0, 68, 68, 14)}")
        lines.append(f"Dialogue: 5,{_ts(t0)},{_ts(end)},Sub,,0,0,0,,{{{box}\\1c{_accent(style)}&\\fad(0,200)"
                     f"\\fscx60\\fscy60\\t(0,120,\\fscx100\\fscy100)\\p1}}{_rect(0, 0, 68, 68, 14)}")
        lines.append(f"Dialogue: 6,{_ts(t0)},{_ts(end)},Sub,,0,0,0,,{{\\an7\\pos({x + 36 + 4:.0f},{ry + 8 + 2:.0f})"
                     f"\\bord0\\shad0\\1c&H00FFFFFF&\\fscx76\\fscy76\\fad(0,200)\\p1}}{_TICK}")
        txt = f"\\an4\\pos({x + 136:.0f},{ry + 44:.0f})\\fnFigtree ExtraBold\\fs{fs}\\bord0\\shad0\\c&H00FFFFFF&"
        lines.append(f"Dialogue: 5,{_ts(start)},{_ts(t0)},Sub,,0,0,0,,{{{txt}\\alpha&H90&\\fad(150,0)}}{_esc(it['text'])}")
        lines.append(f"Dialogue: 5,{_ts(t0)},{_ts(end)},Sub,,0,0,0,,{{{txt}\\fad(0,200)}}{_esc(it['text'])}")
    return lines, None


def _chapters(items, times, x, top, row_h, fs, start, end, style) -> list[str]:
    """Índice numerado: el capítulo que suena se enciende en color y los demás quedan atenuados."""
    out = []
    bounds = [start] + times[1:] + [end]
    for k, it in enumerate(items):
        ry = top + k * row_h + 44
        num = f"{k + 1:02d}"
        for a, b, on in ((start, times[k], False), (times[k], bounds[k + 1], True), (bounds[k + 1], end, False)):
            if b - a <= 0.02:
                continue
            color = _accent(style) if on else "&H00FFFFFF"
            alpha = "00" if on else "70"
            out.append(f"Dialogue: 5,{_ts(a)},{_ts(b)},Sub,,0,0,0,,{{\\an4\\pos({x + 36:.0f},{ry:.0f})\\fnFigtree ExtraBold"
                       f"\\fs{fs}\\bord0\\shad0\\c{color}&\\alpha&H{alpha}&}}{num}   {_esc(it['text'])}")
    return out


def tecleo_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Caja de texto que se escribe sola, como si tecleara una petición."""
    span = _span(effect, clock, duration, 3.0, 2.0)
    if not span:
        return [], None
    start, end = span
    text = effect["text"].strip()[:140]
    label = effect.get("title", "").strip()
    fs = 70
    rows = _wrap(text, "Figtree SemiBold", fs, 860)[:4]
    w = 940
    h = len(rows) * fs * 1.25 + (100 if label else 50)
    x, y = (W - w) / 2, 300
    t = f"{_ts(start)},{_ts(end)}"
    lines = _card(t, x, y, w, h, label, _accent(style))
    total = sum(len(r) for r in rows)
    type_ms = min(2200, max(700, int((end - start) * 1000 * 0.55)))
    per = type_ms / max(1, total)
    n = 0
    top = y + (88 if label else 30)
    for r, row in enumerate(rows):
        chars = []
        for ch in row:
            ms = int(300 + n * per)
            chars.append(f"{{\\alpha&HFF&\\t({ms},{ms + 1},\\alpha&H00&)}}{_esc(ch)}")
            n += 1
        lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an7\\pos({x + 36:.0f},{top + r * fs * 1.25:.0f})\\fnFigtree SemiBold"
                     f"\\fs{fs}\\bord0\\shad0\\c&H00FFFFFF&\\fad(0,200)}}" + "".join(chars))
    return lines, None


# color de fondo, color del texto
COLOR_FLASH = {
    "rosa": ("#F2679A", "#FFFFFF"), "amarillo": ("#F5D90A", "#141518"), "negro": ("#111111", "#FFFFFF"),
    "azul": ("#2B59E6", "#FFFFFF"), "rojo": ("#E63A2E", "#FFFFFF"), "verde": ("#1F7A55", "#FFFFFF"),
}


def color_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Golpe de color: la pantalla se tiñe y salta una palabra enorme."""
    span = _span(effect, clock, duration, 1.0, 0.6)
    if not span:
        return [], None
    start, end = span
    bg, fg = COLOR_FLASH.get(effect.get("look", ""), COLOR_FLASH["rosa"])
    text = effect["text"].upper()
    size = textfit.fit(text, "Anton", 230, 940)
    t = f"{_ts(start)},{_ts(end)}"
    lines = [
        f"Dialogue: 3,{t},Sub,,0,0,0,,{{\\an7\\pos(0,0)\\bord0\\shad0\\1c{rgb(bg)}&\\1a&H28&\\p1}}{_SCREEN}",
        f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an5\\pos(540,920)\\fnAnton\\fs{size:.0f}\\bord0\\shad0\\c{rgb(fg)}&"
        f"\\fscx118\\fscy118\\t(0,120,\\fscx100\\fscy100)}}{_esc(text)}",
    ]
    sub = effect.get("subtitle", "")
    if sub:
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an5\\pos(540,{920 + size * 0.62:.0f})\\fnAnton\\fs60\\bord0"
                     f"\\shad0\\c{rgb(fg)}&}}{_esc(sub.upper())}")
    return lines, Window(start, end)


def comentario_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Burbuja de comentario de un seguidor, para reels que responden a un comentario."""
    span = _span(effect, clock, duration, 3.2, 2.0)
    if not span:
        return [], None
    start, end = span
    fs = 54
    rows = _wrap(effect["text"][:140], "Figtree SemiBold", fs, 740)[:3]
    user = effect.get("title", "").strip().lstrip("@") or "seguidor"
    w = max(560.0, max(textfit.width(r, "Figtree SemiBold", fs) for r in rows) + 200)
    h = 100 + len(rows) * fs * 1.2 + 34
    x, y = (W - w) / 2, 330
    t = f"{_ts(start)},{_ts(end)}"
    mv = lambda px, py: f"\\move({px:.0f},{py + 30:.0f},{px:.0f},{py:.0f},0,200)\\fad(150,200)\\bord0\\shad0"
    lines = [
        f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7{mv(x, y)}\\1c&H00FFFFFF&\\p1}}{_rect(0, 0, w, h, 30)}",
        # Avatar genérico: un círculo gris.
        f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an7{mv(x + 30, y + 30)}\\1c&H00C8C8C8&\\p1}}{_rect(0, 0, 84, 84, 42)}",
        f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an7{mv(x + 136, y + 34)}\\fnFigtree ExtraBold\\fs42\\c&H00141518&}}"
        f"{_esc(user)} {{\\fnFigtree SemiBold\\c&H00888888&}}· 2 h",
    ]
    for k, r in enumerate(rows):
        lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an7{mv(x + 136, y + 90 + k * fs * 1.2)}\\fnFigtree SemiBold"
                     f"\\fs{fs}\\c&H00141518&}}{_esc(r)}")
    return lines, None


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
        f"{{\\an5\\pos(540,960)\\fs{size}\\bord6\\shad0\\c{_accent(style)}&\\fad(0,120)"
        f"\\fscx40\\fscy40\\t(0,130,\\fscx112\\fscy112)\\t(130,220,\\fscx100\\fscy100)}}{text}",
    ], Window(start, end)


def _accent(style: Style) -> str:
    """Color de acento para cajas y casillas; si el estilo lo tiene blanco, el rojo de Imán."""
    return rgb("#FF5547") if style.accent == rgb("#FFFFFF") else style.accent


def _rect(x: float, y: float, w: float, h: float, r: float = 18) -> str:
    """Rectángulo redondeado en dibujo ASS, con la esquina superior izquierda en (x, y)."""
    x2, y2 = x + w, y + h
    return (f"m {x + r:.0f} {y:.0f} l {x2 - r:.0f} {y:.0f} b {x2:.0f} {y:.0f} {x2:.0f} {y:.0f} {x2:.0f} {y + r:.0f} "
            f"l {x2:.0f} {y2 - r:.0f} b {x2:.0f} {y2:.0f} {x2:.0f} {y2:.0f} {x2 - r:.0f} {y2:.0f} "
            f"l {x + r:.0f} {y2:.0f} b {x:.0f} {y2:.0f} {x:.0f} {y2:.0f} {x:.0f} {y2 - r:.0f} "
            f"l {x:.0f} {y + r:.0f} b {x:.0f} {y:.0f} {x:.0f} {y:.0f} {x + r:.0f} {y:.0f}")


def _span(effect: dict, clock: WordClock, duration: float, default: float, minimum: float) -> tuple[float, float] | None:
    start = clock.at(int(effect.get("word", -1)))
    if start is None:
        return None
    end = None
    if effect.get("until_word") is not None:
        end = clock.end_of(int(effect["until_word"]))
    end = end if end and end > start + minimum else start + default
    # Nunca pisa al efecto siguiente.
    nxt = effect.get("_next")
    if nxt is not None and nxt > start + 0.3:
        end = min(end, nxt - 0.05)
    return start, min(duration, end)


def _wrap(text: str, family: str, size: float, max_width: float) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        cand = f"{cur} {word}".strip()
        if cur and textfit.width(cand, family, size) > max_width:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    return lines + ([cur] if cur else [])


def titular_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Titular de revista arriba: caja con la frase en serif y un remate en letra manuscrita."""
    span = _span(effect, clock, duration, 3.0, 1.5)
    if not span:
        return [], None
    start, end = span
    if effect.get("look") == "mixto":
        return _titular_mixto(effect, start, end, style)
    box_c, text_c, hand_c, font = LOOKS.get(effect.get("look", ""), LOOKS["revista"])
    hand_c = hand_c or "#" + _accent(style)[8:10] + _accent(style)[6:8] + _accent(style)[4:6]
    text = effect["text"].upper() if font == "Montserrat Black" else effect["text"]
    sub = effect.get("subtitle", "")
    size = 112 if font != "Montserrat Black" else 92
    rows = _wrap(text, font, size, 900)[:2]
    if sub:
        sub_size = textfit.fit(sub, HAND, 140, 900)
        sub_w = textfit.width(sub, HAND, sub_size)
    w = max([textfit.width(r, font, size) for r in rows] + ([sub_w] if sub else [])) + 90
    line_h = size * 1.12
    h = len(rows) * line_h + (sub_size * 0.95 if sub else 0) + 60
    top = 300
    x = (W - w) / 2
    t = f"{_ts(start)},{_ts(end)}"
    move = lambda px, py: f"\\move({px:.0f},{py + 24:.0f},{px:.0f},{py:.0f},0,220)\\fad(160,180)"
    out = [
        f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7{move(x, top)}\\bord0\\shad0\\1c{rgb(box_c)}&\\p1}}{_rect(0, 0, w, h)}",
    ]
    y = top + 30 + line_h / 2
    for r in rows:
        out.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an5{move(W / 2, y)}\\fn{font}\\fs{size}\\bord0\\shad0"
                   f"\\c{rgb(text_c)}&}}{_esc(r)}")
        y += line_h
    if sub:
        y += sub_size * 0.45 - line_h * 0.5
        out.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an5{move(W / 2, y)}\\fn{HAND}\\fs{sub_size:.0f}\\bord0\\shad0"
                   f"\\c{rgb(hand_c)}&}}{_esc(sub)}")
    # No tapa los subtítulos (va arriba), así que no devuelve ventana.
    return out, None


def _titular_mixto(effect: dict, start: float, end: float, style: Style) -> tuple[list[str], Window | None]:
    """Palabras en mayúsculas sobre cajitas blancas y debajo un remate grande en cursiva."""
    t = f"{_ts(start)},{_ts(end)}"
    fs, pad, gap = 62, 14, 14
    words = effect["text"].upper().split()[:6]
    while fs > 36 and sum(textfit.width(w, "Figtree ExtraBold", fs) + 2 * pad + gap for w in words) > 980:
        fs -= 4
    widths = [textfit.width(w, "Figtree ExtraBold", fs) + 2 * pad for w in words]
    total = sum(widths) + gap * (len(words) - 1)
    x = (W - total) / 2
    y = 300
    out = []
    for k, (w, ww) in enumerate(zip(words, widths)):
        delay = k * 70
        out.append(f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7\\pos({x:.0f},{y})\\bord0\\shad0\\1c&H00FFFFFF&"
                   f"\\alpha&HFF&\\t({delay},{delay + 1},\\alpha&H00&)\\fad(0,180)\\p1}}{_rect(0, 0, ww, fs * 1.25, 6)}")
        out.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an5\\pos({x + ww / 2:.0f},{y + fs * 0.62:.0f})\\fnFigtree ExtraBold"
                   f"\\fs{fs}\\bord0\\shad0\\c&H00141518&\\alpha&HFF&\\t({delay},{delay + 1},\\alpha&H00&)"
                   f"\\fad(0,180)}}{_esc(w)}")
        x += ww + gap
    sub = effect.get("subtitle", "")
    if sub:
        size = textfit.fit(sub, "Playfair Display ExtraBold", 150, 960)
        out.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an8\\pos(540,{y + fs * 1.25 + 8:.0f})\\fnPlayfair Display ExtraBold"
                   f"\\i1\\fs{size:.0f}\\bord0\\shad4\\4a&H70&\\c&H00FFFFFF&\\fad(250,180)}}{_esc(sub)}")
    return out, None


def cifra_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Cifra gigante que cuenta hacia arriba, con una línea y su explicación a mano debajo."""
    span = _span(effect, clock, duration, 2.2, 1.6)
    if not span:
        return [], None
    start, end = span
    text = effect["text"].strip()
    size = textfit.fit(text, "Anton", 330, 900)
    lines = [_dim(start, end, "28")]
    digits = "".join(c for c in text if c.isdigit())
    count_up = digits and len(digits) <= 5 and text.replace(digits, "", 1) in ("", "x", "%", "€", "+", "K", "k", " €")
    head = f"\\an5\\pos(540,880)\\fn Anton\\fs{size:.0f}\\bord0\\shad0\\c{_accent(style)}&"
    if count_up and int(digits) > 1:
        # Cuenta de 0 a la cifra en 0,6 s (12 pasos) y se queda fija.
        n = int(digits)
        steps = 12
        for k in range(1, steps):
            a, b = start + 0.05 * (k - 1), start + 0.05 * k
            val = text.replace(digits, str(round(n * (k / steps) ** 0.6)), 1)
            lines.append(f"Dialogue: 6,{_ts(a)},{_ts(b)},Sub,,0,0,0,,{{{head}}}{_esc(val)}")
        lines.append(f"Dialogue: 6,{_ts(start + 0.05 * (steps - 1))},{_ts(end)},Sub,,0,0,0,,"
                     f"{{{head}\\fad(0,150)\\fscx108\\fscy108\\t(0,140,\\fscx100\\fscy100)}}{_esc(text)}")
    else:
        lines.append(f"Dialogue: 6,{_ts(start)},{_ts(end)},Sub,,0,0,0,,{{{head}\\fad(0,150)"
                     f"\\fscx40\\fscy40\\t(0,160,\\fscx106\\fscy106)\\t(160,240,\\fscx100\\fscy100)}}{_esc(text)}")
    bar_w = max(240.0, min(820.0, textfit.width(text, "Anton", size)))
    lines.append(f"Dialogue: 6,{_ts(start + 0.25)},{_ts(end)},Sub,,0,0,0,,{{\\an7\\pos({(W - bar_w) / 2:.0f},1060)"
                 f"\\bord0\\shad0\\1c{_accent(style)}&\\fscx0\\t(0,260,\\fscx100)\\fad(0,150)\\p1}}"
                 f"{_rect(0, 0, bar_w, 10, 5)}")
    sub = effect.get("subtitle", "")
    if sub:
        rows = _wrap(sub, HAND, 92, 880)[:2]
        for k, r in enumerate(rows):
            lines.append(f"Dialogue: 6,{_ts(start + 0.35)},{_ts(end)},Sub,,0,0,0,,{{\\an5\\pos(540,{1150 + k * 92})"
                         f"\\fn{HAND}\\fs92\\bord0\\shad3\\4a&H60&\\c&H00FFFFFF&\\fad(200,150)}}{_esc(r)}")
    return lines, Window(start, end)


def _mmss(t: float) -> str:
    t = max(0, int(round(t)))
    return f"{t // 60}:{t % 60:02d}"


def contador_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Contador: la duración de la toma en bruto baja hasta la del reel ya editado."""
    span = _span(effect, clock, duration, 2.6, 1.8)
    src = effect.get("_from")
    # Si la IA da una duración ("1:20"), manda sobre la del archivo.
    m, _, sec = str(effect.get("text", "")).partition(":")
    if m.isdigit() and sec.isdigit():
        src = int(m) * 60 + int(sec)
    if not span or not src:
        return [], None
    start, end = span
    a_label = (effect.get("title") or "Toma en bruto").upper()
    b_label = (effect.get("subtitle") or "Lo que estás viendo").upper()
    w, h, x, y = 620, 250, (W - 620) / 2, 290
    t = f"{_ts(start)},{_ts(end)}"
    lines = [f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7\\pos({x:.0f},{y})\\bord0\\shad0\\1c{rgb('#123A35')}&"
             f"\\fad(150,200)\\p1}}{_rect(0, 0, w, h, 22)}"]
    run = min(1.4, (end - start) * 0.6)
    steps = 14
    label = f"\\an5\\pos(540,{y + 40})\\fnFigtree ExtraBold\\fs32\\bord0\\shad0\\c&H00FFFFFF&"
    digits = f"\\an5\\pos(540,{y + 150})\\fnAnton\\fs150\\bord0\\shad0\\c{_accent(style)}&"
    hold = start + 0.5
    lines.append(f"Dialogue: 5,{_ts(start)},{_ts(hold + run)},Sub,,0,0,0,,{{{label}\\fad(150,0)}}{_esc(a_label)}")
    lines.append(f"Dialogue: 5,{_ts(hold + run)},{_ts(end)},Sub,,0,0,0,,{{{label}\\fad(0,200)}}{_esc(b_label)}")
    lines.append(f"Dialogue: 6,{_ts(start)},{_ts(hold)},Sub,,0,0,0,,{{{digits}\\fad(150,0)}}{_mmss(src)}")
    for k in range(1, steps + 1):
        a = hold + run * (k - 1) / steps
        b = hold + run * k / steps if k < steps else end
        val = src - (src - duration) * (k / steps) ** 0.7
        lines.append(f"Dialogue: 6,{_ts(a)},{_ts(b)},Sub,,0,0,0,,{{{digits}{'\\fad(0,200)' if k == steps else ''}}}{_mmss(val)}")
    return lines, None


def portada_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Portada de revista: cabecera enorme, marco fino, código de barras y titulares de portada."""
    span = _span(effect, clock, duration, 2.8, 1.8)
    if not span:
        return [], None
    start, end = span
    t = f"{_ts(start)},{_ts(end)}"
    head = effect["text"].upper()[:14]
    size = textfit.fit(head, "Playfair Display ExtraBold", 260, 960)
    base = "\\bord0\\shad0\\fad(200,250)"
    lines = []
    # Marco fino a 40 px del borde.
    for rx, ry, rw, rh in ((40, 180, 1000, 3), (40, 1700, 1000, 3), (40, 180, 3, 1523), (1037, 180, 3, 1523)):
        lines.append(f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7\\pos({rx},{ry}){base}\\1c&H00FFFFFF&\\p1}}"
                     f"m 0 0 l {rw} 0 l {rw} {rh} l 0 {rh}")
    lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an8\\pos(540,205){base}\\fnFigtree ExtraBold\\fs26"
                 f"\\c&H00FFFFFF&\\fsp4}}Nº 01  ·  EDICIÓN ESPECIAL  ·  HECHO CON IMÁN")
    lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an8\\pos(540,235){base}\\fnPlayfair Display ExtraBold"
                 f"\\fs{size:.0f}\\c&H00FFFFFF&\\shad3\\4a&H80&}}{_esc(head)}")
    sub = effect.get("subtitle", "")
    if sub:
        rows = _wrap(sub, "Playfair Display ExtraBold", 46, 420)[:3]
        for k, r in enumerate(rows):
            lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an6\\pos(1000,{1520 + k * 54}){base}\\fnPlayfair Display ExtraBold"
                         f"\\i1\\fs46\\c&H00FFFFFF&\\shad3\\4a&H80&}}{_esc(r)}")
    # Código de barras (siempre el mismo dibujo).
    bars, bx = [], 0
    for k, wbar in enumerate([3, 1, 2, 1, 3, 2, 1, 1, 3, 1, 2, 3, 1, 2, 1, 3, 1, 1, 2, 1, 3, 2, 1, 2]):
        if k % 2 == 0:
            bars.append(f"m {bx} 0 l {bx + wbar * 4} 0 l {bx + wbar * 4} 90 l {bx} 90")
        bx += wbar * 4
    lines.append(f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7\\pos(70,1560){base}\\1c&H00FFFFFF&\\p1}}"
                 f"m -10 -10 l {bx + 10} -10 l {bx + 10} 110 l -10 110")
    lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an7\\pos(70,1560){base}\\1c&H00141518&\\p1}}{' '.join(bars)}")
    return lines, None


def cta_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Llamada a la acción: se escribe la palabra clave en los comentarios y sale el aviso del mensaje privado."""
    span = _span(effect, clock, duration, 3.2, 2.4)
    if not span:
        return [], None
    start, end = span
    key = effect["text"].strip().upper()[:20]
    dm = effect.get("subtitle", "").strip() or "Te envío el enlace por privado"
    typed_ms = 250 + 110 * len(key)
    mid = start + typed_ms / 1000 + 0.35
    base = "\\bord0\\shad0"
    lines = []
    # 1) La caja de comentarios donde se teclea la palabra.
    bar_w, bar_x, bar_y = 820, (W - 820) / 2, 1500
    lines.append(f"Dialogue: 4,{_ts(start)},{_ts(mid)},Sub,,0,0,0,,{{\\an7\\pos({bar_x:.0f},{bar_y}){base}"
                 f"\\1c&H00202020&\\1a&H20&\\fad(150,100)\\p1}}{_rect(0, 0, bar_w, 100, 50)}")
    chars = "".join(f"{{\\alpha&HFF&\\t({250 + 110 * i},{251 + 110 * i},\\alpha&H00&)}}{_esc(c)}" for i, c in enumerate(key))
    lines.append(f"Dialogue: 5,{_ts(start)},{_ts(mid)},Sub,,0,0,0,,{{\\an4\\pos({bar_x + 50:.0f},{bar_y + 50})"
                 f"{base}\\fnFigtree ExtraBold\\fs54\\c&H00FFFFFF&\\fad(150,100)}}{chars}")
    # 2) El comentario publicado y la respuesta por privado.
    t = f"{_ts(mid)},{_ts(end)}"
    cw = textfit.width(key, "Figtree ExtraBold", 72) + 230
    cx = (W - cw) / 2
    lines.append(f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7\\pos({cx:.0f},1360){base}\\1c&H00FFFFFF&"
                 f"\\fscx80\\fscy80\\t(0,140,\\fscx100\\fscy100)\\fad(0,200)\\p1}}{_rect(0, 0, cw, 120, 60)}")
    lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an7\\pos({cx + 26:.0f},1386){base}\\1c&H00C8C8C8&\\fad(0,200)\\p1}}"
                 f"{_rect(0, 0, 68, 68, 34)}")
    lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an4\\pos({cx + 116:.0f},1420){base}\\fnFigtree SemiBold\\fs34"
                 f"\\c&H00888888&\\fad(0,200)}}tú  {{\\fnFigtree ExtraBold\\fs72\\c&H00141518&}}{_esc(key)}")
    dm_w = textfit.width(dm, "Figtree ExtraBold", 44) + 80
    dx = (W - dm_w) / 2
    t2 = f"{_ts(mid + 0.5)},{_ts(end)}"
    lines.append(f"Dialogue: 4,{t2},Sub,,0,0,0,,{{\\an7\\move({dx:.0f},1540,{dx:.0f},1510,0,200){base}"
                 f"\\1c&H00141518&\\1a&H10&\\fad(150,200)\\p1}}{_rect(0, 0, dm_w, 170, 28)}")
    lines.append(f"Dialogue: 5,{t2},Sub,,0,0,0,,{{\\an7\\move({dx + 40:.0f},1560,{dx + 40:.0f},1530,0,200){base}"
                 f"\\fnFigtree ExtraBold\\fs44\\c&H00FFFFFF&\\fad(150,200)}}{_esc(dm)}")
    pill = "Enlace enviado"
    pw = textfit.width(pill, "Figtree ExtraBold", 36) + 60
    lines.append(f"Dialogue: 5,{t2},Sub,,0,0,0,,{{\\an7\\move({dx + 40:.0f},1620,{dx + 40:.0f},1590,0,200){base}"
                 f"\\1c{_accent(style)}&\\fad(150,200)\\p1}}{_rect(0, 0, pw, 60, 30)}")
    lines.append(f"Dialogue: 6,{t2},Sub,,0,0,0,,{{\\an5\\move({dx + 40 + pw / 2:.0f},1650,{dx + 40 + pw / 2:.0f},1620,0,200)"
                 f"{base}\\fnFigtree ExtraBold\\fs36\\c&H00141518&\\fad(150,200)}}{pill}")
    return lines, Window(start, end)


def _frase_enfoque(effect: dict, start: float, end: float) -> tuple[list[str], Window | None]:
    """Frase en serif sobre fondo oscuro que entra desenfocada y se enfoca."""
    text = effect["text"].strip()[:90]
    size = 150 if len(text) <= 24 else 120
    rows = _wrap(text, "Playfair Display ExtraBold", size, 900)[:5]
    t = f"{_ts(start)},{_ts(end)}"
    lines = [_dim(start, end, "18")]
    top = 960 - (len(rows) - 1) * size * 0.55
    for r, row in enumerate(rows):
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an5\\pos(540,{top + r * size * 1.08:.0f})\\fnPlayfair Display ExtraBold"
                     f"\\fs{size}\\bord0\\shad0\\c&H00FFFFFF&\\blur18\\alpha&H80&"
                     f"\\t(0,450,\\blur0\\alpha&H00&)\\fad(0,180)}}{_esc(row)}")
    return lines, Window(start, end)


def dato_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Etiqueta pequeña con un dato junto a la cara: cifra grande y una línea debajo."""
    span = _span(effect, clock, duration, 2.2, 1.4)
    if not span:
        return [], None
    start, end = span
    num, sub = effect["text"].strip()[:10], effect.get("subtitle", "").strip()[:28]
    nw = textfit.width(num, "Figtree ExtraBold", 120)
    sw = textfit.width(sub, "Figtree ExtraBold", 40) if sub else 0
    w, h = max(nw, sw) + 70, 170 + (40 if sub else 0)
    x, y = 640 - w / 2, 420  # a la derecha de la cara
    t = f"{_ts(start)},{_ts(end)}"
    pop = "\\fscx70\\fscy70\\t(0,150,\\fscx100\\fscy100)\\fad(0,200)\\bord0\\shad0"
    lines = [
        f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7\\pos({x:.0f},{y}){pop}\\1c{rgb('#123A35')}&\\3c{_accent(style)}&"
        f"\\p1}}{_rect(0, 0, w, h, 24)}",
        f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an8\\pos({x + w / 2:.0f},{y + 6}){pop}\\fnFigtree ExtraBold\\fs120"
        f"\\c{_accent(style)}&}}{_esc(num)}",
    ]
    if sub:
        lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an8\\pos({x + w / 2:.0f},{y + 140}){pop}\\fnFigtree ExtraBold"
                     f"\\fs40\\c&H00FFFFFF&}}{_esc(sub)}")
    return lines, None


def frase_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Frase corta a pantalla completa en letra manuscrita; las palabras entran al ritmo de la voz."""
    span = _span(effect, clock, duration, 1.8, 1.2)
    if not span:
        return [], None
    start, end = span
    if effect.get("look") == "enfoque":
        return _frase_enfoque(effect, start, end)
    tokens = effect["text"].split()[:8]
    size = 170 if len(" ".join(tokens)) <= 14 else 130
    rows = _wrap(" ".join(tokens), HAND, size, 920)
    first = int(effect["word"])
    parts, k = [], 0
    for r, row in enumerate(rows):
        words = []
        for tok in row.split():
            t = clock.at(first + k)
            ms = 0 if t is None else max(0, min(int((t - start) * 1000), int((end - start) * 600)))
            words.append(f"{{\\alpha&HFF&\\t({ms},{ms + 90},\\alpha&H00&)}}{_esc(tok)}")
            k += 1
        parts.append(" ".join(words))
    top = 960 - (len(rows) - 1) * size * 0.5
    lines = [_dim(start, end, "45")]
    for r, row in enumerate(parts):
        lines.append(f"Dialogue: 6,{_ts(start)},{_ts(end)},Sub,,0,0,0,,{{\\an5\\pos(540,{top + r * size * 0.95:.0f})"
                     f"\\fn{HAND}\\fs{size}\\bord0\\shad4\\4a&H70&\\c&H00FFFFFF&\\fad(0,150)}}{row}")
    return lines, Window(start, end)


SEG_KINDS = {"detras": (2.2, 1.2), "fondo": (2.5, 1.2), "desenfoque": (2.5, 1.2)}
# Colores de texto gigante detrás y de fondo liso.
SEG_COLORS = {"rosa": "#FF4F7B", "amarillo": "#F5D90A", "negro": "#141518", "azul": "#2B59E6", "rojo": "#E63A2E",
              "verde": "#1F7A55"}


@dataclass
class SegOp:
    kind: str
    start: float
    end: float
    color: str = ""


def _seg_spans(effects: list[dict], clock: WordClock, duration: float):
    starts = [clock.at(int(fx.get("word", -1))) for fx in effects or []]
    for i, fx in enumerate(effects or []):
        kind = fx.get("type")
        if kind not in SEG_KINDS:
            continue
        later = [t for j, t in enumerate(starts) if j != i and t is not None and starts[i] is not None and t > starts[i]]
        span = _span({**fx, "_next": min(later) if later else None}, clock, duration, *SEG_KINDS[kind])
        if span:
            yield fx, span


def seg_ops(effects: list[dict], clock: WordClock, duration: float) -> list[SegOp]:
    """Efectos que necesitan recortar a la persona, en tiempos del reel."""
    return [SegOp(fx["type"], a, b, SEG_COLORS.get(fx.get("look", ""), "#123A35"))
            for fx, (a, b) in _seg_spans(effects, clock, duration)]


def behind_events(effects: list[dict], clock: WordClock, style: Style, duration: float) -> list[str]:
    """Textos que van detrás de la persona: la palabra gigante de "detras" y el texto de "fondo"."""
    lines = []
    for fx, (start, end) in _seg_spans(effects, clock, duration):
        text = str(fx.get("text", "")).strip()
        if fx["type"] == "desenfoque" or not text or text == "-":
            continue
        text = text.upper()[:14]
        color = rgb(SEG_COLORS[fx["look"]]) if fx.get("look") in SEG_COLORS else _accent(style)
        if fx["type"] == "fondo":
            color = "&H00FFFFFF"
        size = textfit.fit(text, "Anton", 420, 1020)
        t = f"{_ts(start)},{_ts(end)}"
        # A la altura de la cabeza y los hombros, para que la persona tape parte de las letras.
        lines.append(f"Dialogue: 2,{t},Sub,,0,0,0,,{{\\an5\\pos(540,760)\\fnAnton\\fs{size:.0f}\\bord0\\shad0"
                     f"\\c{color}&\\fscx80\\fscy80\\t(0,180,\\fscx100\\fscy100)\\fad(120,200)}}{_esc(text)}")
        sub = str(fx.get("subtitle", "")).strip()
        if sub:
            lines.append(f"Dialogue: 2,{t},Sub,,0,0,0,,{{\\an2\\pos(540,{760 - size * 0.46:.0f})\\fnFigtree ExtraBold"
                         f"\\fs64\\bord0\\shad2\\4a&H80&\\c&H00FFFFFF&\\fad(120,200)}}{_esc(sub.upper()[:30])}")
    return lines


VIDEO_KINDS = {"bruto": (3.0, 2.0), "fantasma": (1.6, 0.8), "pagina": (2.6, 1.6), "apoyo": (3.0, 1.5)}
PERSON_TYPES = (*SEG_KINDS, "apoyo")  # necesitan a alguien delante de la cámara
MEDIA_EXT = (".mp4", ".mov", ".m4v", ".webm", ".jpg", ".jpeg", ".png", ".webp")


def auto_broll(effects: list[dict], kept_idx: list[int], clips: int) -> list[dict]:
    """Sin IA (o si no los ha usado): reparte los vídeos de apoyo por el reel, lejos del gancho."""
    if not clips or any(fx.get("type") == "apoyo" for fx in effects) or len(kept_idx) < 12:
        return effects
    out = list(effects)
    n = len(kept_idx)
    for k in range(clips):
        at = int(n * (0.2 + 0.65 * (k + 0.5) / clips))
        out.append({"type": "apoyo", "word": kept_idx[at], "text": str(k + 1),
                    "until_word": kept_idx[min(n - 1, at + 8)], "auto": True})
    return out


def bruto_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Etiqueta y nota a mano de la tarjeta con la toma original (la tarjeta la pinta ffmpeg)."""
    span = _span(effect, clock, duration, *VIDEO_KINDS["bruto"])
    if not span:
        return [], None
    start, end = span
    t = f"{_ts(start)},{_ts(end)}"
    label = (effect.get("title") or "Bruto").upper()[:16]
    note = (effect.get("subtitle", "").strip() or "tal cual, sin tocar")[:22]
    lw = textfit.width(label, "Figtree ExtraBold", 40) + 40
    return [
        f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an7\\pos(600,290)\\frz4\\bord0\\shad0\\1c{_accent(style)}&\\fad(150,150)\\p1}}"
        f"{_rect(0, 0, lw, 58, 12)}",
        f"Dialogue: 7,{t},Sub,,0,0,0,,{{\\an4\\pos(620,318)\\frz4\\fnFigtree ExtraBold\\fs40\\bord0\\shad0"
        f"\\c&H00141518&\\fad(150,150)}}{_esc(label)}",
        f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an7\\pos(640,1060)\\frz4\\fn{HAND}\\fs64\\bord0\\shad3"
        f"\\4a&H70&\\c&H00FFFFFF&\\fad(250,150)}}{_esc(note)}",
    ], None


def pagina_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Texto de la hoja de revista; el vídeo encogido lo pinta ffmpeg. Tapa los subtítulos."""
    span = _span(effect, clock, duration, *VIDEO_KINDS["pagina"])
    if not span:
        return [], None
    start, end = span
    t = f"{_ts(start)},{_ts(end)}"
    rows = _wrap(effect["text"].strip()[:60], "Playfair Display ExtraBold", 84, 860)[:2]
    lines = []
    for k, r in enumerate(rows):
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an2\\pos(540,{520 - (len(rows) - 1 - k) * 92})\\fnPlayfair Display ExtraBold"
                     f"\\fs84\\bord0\\shad0\\c&H00141518&\\fad(200,150)}}{_esc(r)}")
    sub = effect.get("subtitle", "").strip()
    if sub:
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an8\\pos(540,1735)\\fn{HAND}\\fs72\\bord0\\shad0"
                     f"\\c{rgb('#D2372B')}&\\fad(300,150)}}{_esc(sub)}")
    return lines, Window(start, end)


def video_ops(effects: list[dict], clock: WordClock, duration: float, src_of=None,
              assets: dict[str, str] | None = None) -> list[VideoOp]:
    """Los efectos de vídeo de un plan, en tiempos del reel. `src_of(t)` da el segundo de la toma original.
    `assets`: número de vídeo de apoyo ("1", "2"…) -> archivo."""
    ops = []
    starts = [clock.at(int(fx.get("word", -1))) for fx in effects or []]
    for i, fx in enumerate(effects or []):
        kind = fx.get("type")
        if kind not in VIDEO_KINDS:
            continue
        later = [t for j, t in enumerate(starts) if j != i and t is not None and starts[i] is not None and t > starts[i]]
        span = _span({**fx, "_next": min(later) if later else None}, clock, duration, *VIDEO_KINDS[kind])
        if not span:
            continue
        # La tarjeta "bruto" enseña la toma sin cortar desde el principio de lo que se dice ahí.
        src = src_of(span[0]) if (src_of and kind == "bruto") else 0.0
        path = ""
        if kind == "apoyo":
            path = (assets or {}).get(str(fx.get("text", "")).strip(), "")
            if not path:
                continue
        ops.append(VideoOp(kind, span[0], span[1], max(0.0, src - 0.5), path=path))
    return ops


BUILDERS = {"bruto": bruto_events, "pagina": pagina_events, LISTA: lista_events, PALABRA: palabra_events, TITULAR: titular_events, CIFRA: cifra_events, FRASE: frase_events,
            TECLEO: tecleo_events, "color": color_events, "comentario": comentario_events,
            "contador": contador_events, "portada": portada_events, "cta": cta_events, "dato": dato_events}


def _pack_builders() -> dict:
    from .gestos import GESTURE_BUILDERS
    from .packfx import PACK_BUILDERS

    return {**PACK_BUILDERS, **GESTURE_BUILDERS}


def build_effects(effects: list[dict], clock: WordClock, style: Style, duration: float, source_duration: float = 0.0) -> tuple[list[str], list[Window]]:
    lines: list[str] = []
    windows: list[Window] = []
    starts = [clock.at(int(fx.get("word", fx.get("items", [{}])[0].get("at_word", -1) if fx.get("items") else -1)))
              for fx in effects or []]
    for i, fx in enumerate(effects or []):
        later = [t for j, t in enumerate(starts) if j != i and t is not None and starts[i] is not None and t > starts[i]]
        fx = {**fx, "_next": min(later) if later else None, "_from": source_duration}
        builder = BUILDERS.get(fx.get("type")) or _pack_builders().get(fx.get("type"))
        if not builder:
            continue
        ev, win = builder(fx, clock, style, duration)
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


END_CARD = 2.4  # segundos del cierre de marca


def brand_ops(brand, duration: float) -> list[VideoOp]:
    """Logo en la esquina durante el reel y, al final, el cierre con fondo de marca y logo grande.

    El fondo del cierre lo pinta ffmpeg (no el ASS) para que el logo quede encima
    y los textos del cierre, que van en el ASS, encima de todo.
    """
    if brand is None or not brand.active:
        return []
    logo = brand.logo_path
    closing = brand.end_card and duration > END_CARD + 1
    end_start = duration - END_CARD if closing else duration
    ops = []
    if logo and brand.logo_corner and end_start > 0.5:
        ops.append(VideoOp("logo", 0.0, end_start, path=str(logo)))
    if closing:
        ops.append(VideoOp("endcard", end_start, duration, color=brand.primary or "#141518"))
        if logo:
            from .brand import logo_card

            ops.append(VideoOp("logo_end", end_start, duration, path=str(logo_card())))
    return ops


def end_card_events(brand, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Cierre de marca: fondo del color de la marca, llamada a la acción y contacto."""
    if brand is None or not brand.end_card or not brand.active or duration <= END_CARD + 1:
        return [], None
    start, end = duration - END_CARD, duration
    t = f"{_ts(start)},{_ts(end)}"
    bg = brand.primary or "#141518"
    from .brand import ink_on

    ink = rgb(ink_on(bg))
    lines = []
    y = 980 if brand.logo_path else 860
    if not brand.logo_path and brand.name:
        size = textfit.fit(brand.name, "Figtree ExtraBold", 120, 900)
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an5\\pos(540,700)\\fnFigtree ExtraBold\\fs{size:.0f}\\bord0\\shad0"
                     f"\\c{ink}&\\fad(300,0)}}{_esc(brand.name)}")
    if brand.cta:
        size = textfit.fit(brand.cta, "Figtree ExtraBold", 76, 920)
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an8\\pos(540,{y})\\fnFigtree ExtraBold\\fs{size:.0f}\\bord0\\shad0"
                     f"\\c{ink}&\\fad(400,0)}}{_esc(brand.cta)}")
        y += size * 1.4
    for txt in (brand.contact, brand.handle):
        if txt:
            lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an8\\pos(540,{y:.0f})\\fnFigtree SemiBold\\fs52\\bord0\\shad0"
                         f"\\c{ink}&\\alpha&H30&\\fad(500,0)}}{_esc(txt)}")
            y += 72
    return lines, Window(start, end)
