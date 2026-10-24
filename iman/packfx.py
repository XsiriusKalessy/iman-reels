"""Efectos de los packs por sector: ubicación, oferta, itinerario y ruta (viajes),
testimonio y plazas (cursos), precio (productos).

Siguen las zonas seguras de Instagram y TikTok: nada importante en los 220 px de arriba,
en los 320 px de abajo ni pegado al borde derecho, donde van los botones.
"""

from __future__ import annotations

import math

from . import textfit
from .captions import W, Style, _esc, _ts, rgb
from .effects import Window, WordClock, _accent, _dim, _rect, _span, _wrap

CREAM = rgb("#F4ECDF")
INK = rgb("#141518")
_PIN = "m 30 0 b 13 0 0 13 0 30 b 0 52 30 82 30 82 b 30 82 60 52 60 30 b 60 13 47 0 30 0"
_PLANE = ("m 0 -5 l 46 -5 b 56 -5 62 0 62 0 b 62 0 56 5 46 5 l 0 5 l 0 -5 "
          "m 20 -5 l 8 -34 l 17 -34 l 36 -5 m 20 5 l 8 34 l 17 34 l 36 5 "
          "m 2 -5 l -6 -17 l 2 -17 l 10 -5 m 2 5 l -6 17 l 2 17 l 10 5")


def _circle(d: float) -> str:
    """Círculo de diámetro d con la esquina en (0, 0); libass centra mal los dibujos con coordenadas negativas."""
    r, k = d / 2, d / 2 * 0.5523
    return (f"m {r:.1f} 0 b {r + k:.1f} 0 {d:.1f} {r - k:.1f} {d:.1f} {r:.1f} b {d:.1f} {r + k:.1f} {r + k:.1f} {d:.1f} {r:.1f} {d:.1f} "
            f"b {r - k:.1f} {d:.1f} 0 {r + k:.1f} 0 {r:.1f} b 0 {r - k:.1f} {r - k:.1f} 0 {r:.1f} 0")


def _star(cx: float, cy: float, r: float, points: int = 5, inner: float = 0.45) -> str:
    pts = []
    for k in range(2 * points):
        a = -math.pi / 2 + k * math.pi / points
        rr = r if k % 2 == 0 else r * inner
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return "m " + " l ".join(f"{x:.0f} {y:.0f}" for x, y in pts)


def ubicacion_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Chincheta con el nombre del sitio, que entra desde la izquierda arriba."""
    span = _span(effect, clock, duration, 2.6, 1.6)
    if not span:
        return [], None
    start, end = span
    place, sub = effect["text"].strip()[:28], effect.get("subtitle", "").strip()[:32]
    size = textfit.fit(place, "Figtree ExtraBold", 64, 700, 40)
    w = max(textfit.width(place, "Figtree ExtraBold", size), textfit.width(sub, "Figtree SemiBold", 38) if sub else 0) + 170
    h = 150 if sub else 120
    x, y = 60, 300
    t = f"{_ts(start)},{_ts(end)}"
    slide = f"\\move({x - w - 80:.0f},{y},{x},{y},0,260)"
    base = "\\an7\\bord0\\shad0\\fad(0,200)"
    lines = [
        f"Dialogue: 4,{t},Sub,,0,0,0,,{{{base}{slide}\\1c&H00FFFFFF&\\p1}}{_rect(0, 0, w, h, h / 2)}",
        f"Dialogue: 5,{t},Sub,,0,0,0,,{{{base}\\move({x - w + 0:.0f},{y + (h - 82) / 2:.0f},{x + 34},{y + (h - 82) / 2:.0f},0,260)"
        f"\\1c{_accent(style)}&\\p1}}{_PIN}",
        f"Dialogue: 6,{t},Sub,,0,0,0,,{{{base}\\move({x - w + 18:.0f},{y + (h - 82) / 2 + 16:.0f},{x + 52},{y + (h - 82) / 2 + 16:.0f},0,260)"
        f"\\1c&H00FFFFFF&\\p1}}{_rect(0, 0, 24, 24, 12)}",
        f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an4\\bord0\\shad0\\fad(0,200)\\move({x - w + 76:.0f},{y + (44 if sub else h / 2):.0f},"
        f"{x + 120},{y + (44 if sub else h / 2):.0f},0,260)\\fnFigtree ExtraBold\\fs{size:.0f}\\c{INK}&}}{_esc(place)}",
    ]
    if sub:
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an4\\bord0\\shad0\\fad(0,200)\\move({x - w + 76:.0f},{y + 108},"
                     f"{x + 120},{y + 108},0,260)\\fnFigtree SemiBold\\fs38\\c&H00707070&}}{_esc(sub)}")
    return lines, None


def oferta_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Tarjeta de oferta: destino en grande, lo que incluye y el precio en una pegatina girada."""
    span = _span(effect, clock, duration, 3.2, 2.0)
    if not span:
        return [], None
    start, end = span
    dest = effect["text"].strip()[:40]
    price = effect.get("subtitle", "").strip()[:18]
    detail = effect.get("title", "").strip()[:40]
    w, x, y = 900, (W - 900) / 2, 520
    rows = _wrap(dest, "Playfair Display ExtraBold", 120, w - 120)[:2]
    size = 120 if len(rows) == 1 else 100
    h = 150 + len(rows) * size * 1.05 + (80 if detail else 0) + 40
    t = f"{_ts(start)},{_ts(end)}"
    pop = "\\fscx85\\fscy85\\t(0,180,\\fscx100\\fscy100)\\fad(120,200)\\bord0\\shad0"
    acc = _accent(style)
    lines = [_dim(start, end, "70"),
             f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7\\pos({x:.0f},{y}){pop}\\1c{CREAM}&\\p1}}{_rect(0, 0, w, h, 34)}"]
    tag = "OFERTA"
    tw = textfit.width(tag, "Figtree ExtraBold", 40) + 56
    lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an7\\pos({x + 60:.0f},{y + 56}){pop}\\1c{acc}&\\p1}}{_rect(0, 0, tw, 64, 32)}")
    lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an5\\pos({x + 60 + tw / 2:.0f},{y + 88}){pop}\\fnFigtree ExtraBold\\fs40"
                 f"\\c&H00FFFFFF&}}{tag}")
    ry = y + 150
    for row in rows:
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an7\\pos({x + 60:.0f},{ry:.0f}){pop}\\fnPlayfair Display ExtraBold"
                     f"\\fs{size}\\c{INK}&}}{_esc(row)}")
        ry += size * 1.05
    if detail:
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an7\\pos({x + 60:.0f},{ry + 14:.0f}){pop}\\fnFigtree SemiBold\\fs46"
                     f"\\c&H00505050&}}{_esc(detail)}")
    if price:
        ps = textfit.fit(price, "Figtree ExtraBold", 64, 220, 36)
        r = 130
        cx, cy = x + w - 110, y + h + 40
        sticker = f"\\an5\\pos({cx:.0f},{cy:.0f})\\bord0\\shad0\\frz8\\fscx10\\fscy10\\t(250,420,\\fscx100\\fscy100)\\fad(0,200)"
        lines.append(f"Dialogue: 7,{t},Sub,,0,0,0,,{{{sticker}\\1c{acc}&\\p1}}{_circle(2 * r)}")
        lines.append(f"Dialogue: 8,{t},Sub,,0,0,0,,{{{sticker}\\fnFigtree ExtraBold\\fs{ps:.0f}\\c&H00FFFFFF&}}{_esc(price)}")
    return lines, Window(start, end)


def itinerario_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Itinerario por días: línea de tiempo vertical que se va encendiendo según se cuenta cada día."""
    items = [it for it in effect.get("items", []) if it.get("text")][:5]
    times = [clock.at(int(it.get("at_word", 0))) for it in items]
    if len(items) < 2 or any(t is None for t in times):
        return [], None
    start = max(0.0, times[0] - 0.3)
    end_idx = effect.get("until_word")
    end = clock.end_of(int(end_idx)) if end_idx is not None else None
    end = min(duration, max(end or times[-1] + 2.0, times[-1] + 1.2))
    acc = _accent(style)
    row = 190
    top = 960 - (len(items) - 1) * row / 2 - 60
    x = 150
    t = f"{_ts(start)},{_ts(end)}"
    lines = [_dim(start, end, "50")]
    title = effect.get("title", "").strip()[:30]
    if title:
        lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an1\\pos({x - 40},{top - 70:.0f})\\fnPlayfair Display ExtraBold\\fs76"
                     f"\\bord0\\shad0\\c&H00FFFFFF&\\fad(150,200)}}{_esc(title)}")
    # La línea que une los días.
    lines.append(f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7\\pos({x - 4},{top:.0f})\\bord0\\shad0\\1c&H00FFFFFF&\\1a&H90&"
                 f"\\fad(150,200)\\p1}}{_rect(0, 0, 8, (len(items) - 1) * row, 4)}")
    for k, (it, t0) in enumerate(zip(items, times)):
        cy = top + k * row
        label = it["text"].strip()
        day = f"DÍA {k + 1}"
        if label.lower().startswith("día") and "·" in label:  # "Día 1 · Roma"
            head, _, rest = label.partition("·")
            day, label = head.strip().upper(), rest.strip() or label
        # Punto apagado hasta que se nombra el día; luego, encendido y con su texto.
        lines.append(f"Dialogue: 5,{_ts(start)},{_ts(t0)},Sub,,0,0,0,,{{\\an5\\pos({x},{cy:.0f})\\bord0\\shad0"
                     f"\\1c&H00FFFFFF&\\1a&H80&\\fad(150,0)\\p1}}{_circle(36)}")
        lines.append(f"Dialogue: 5,{_ts(t0)},{_ts(end)},Sub,,0,0,0,,{{\\an5\\pos({x},{cy:.0f})\\bord0\\shad0\\1c{acc}&"
                     f"\\fscx40\\fscy40\\t(0,160,\\fscx100\\fscy100)\\fad(0,200)\\p1}}{_circle(60)}")
        lines.append(f"Dialogue: 6,{_ts(t0)},{_ts(end)},Sub,,0,0,0,,{{\\an1\\bord0\\shad0\\fad(0,200)"
                     f"\\move({x + 90},{cy - 8:.0f},{x + 70},{cy - 8:.0f},0,200)\\fnFigtree ExtraBold\\fs40\\c{acc}&}}{_esc(day)}")
        size = textfit.fit(label, "Figtree ExtraBold", 74, 800, 44)
        lines.append(f"Dialogue: 6,{_ts(t0)},{_ts(end)},Sub,,0,0,0,,{{\\an7\\bord0\\shad0\\fad(0,200)"
                     f"\\move({x + 90},{cy + 4:.0f},{x + 70},{cy + 4:.0f},0,200)\\fnFigtree ExtraBold\\fs{size:.0f}"
                     f"\\c&H00FFFFFF&}}{_esc(label)}")
    return lines, Window(start, end)


def ruta_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Ruta de un sitio a otro: arco de puntos que se dibuja y un avión que lo recorre."""
    span = _span(effect, clock, duration, 3.0, 2.0)
    if not span:
        return [], None
    start, end = span
    a_name, b_name = effect["text"].strip()[:18], effect.get("subtitle", "").strip()[:18]
    if not b_name:
        return [], None
    note = effect.get("title", "").strip()[:30]
    acc = _accent(style)
    p0, p2, c = (200, 900), (880, 900), (540, 560)
    fly = min(1.6, (end - start) * 0.6)

    def at(u: float) -> tuple[float, float]:
        x = (1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * c[0] + u ** 2 * p2[0]
        y = (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * c[1] + u ** 2 * p2[1]
        return x, y

    t = f"{_ts(start)},{_ts(end)}"
    lines = [_dim(start, end, "40")]
    for name, (px, py) in ((a_name, p0), (b_name, p2)):
        lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an5\\pos({px},{py})\\bord0\\shad0\\1c&H00FFFFFF&\\fad(150,200)"
                     f"\\p1}}{_circle(44)}")
        size = textfit.fit(name, "Figtree ExtraBold", 64, 380, 40)
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an8\\pos({px},{py + 46})\\fnFigtree ExtraBold\\fs{size:.0f}\\bord0"
                     f"\\shad0\\c&H00FFFFFF&\\fad(150,200)}}{_esc(name)}")
    steps = 22
    for k in range(1, steps):
        u = k / steps
        x, y = at(u)
        ms = int(u * fly * 1000)
        lines.append(f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an5\\pos({x:.0f},{y:.0f})\\bord0\\shad0\\1c{acc}&\\alpha&HFF&"
                     f"\\t({ms},{ms + 60},\\alpha&H00&)\\fad(0,200)\\p1}}{_circle(14)}")
    # El avión, por tramos, girando con la curva.
    seg = 8
    for k in range(seg):
        u0, u1 = k / seg, (k + 1) / seg
        (x0, y0), (x1, y1) = at(u0), at(u1)
        a = start + u0 * fly
        b = start + u1 * fly if k < seg - 1 else end
        ang = -math.degrees(math.atan2(y1 - y0, x1 - x0))
        mv = f"\\move({x0:.0f},{y0 - 34:.0f},{x1:.0f},{y1 - 34:.0f},0,{int((u1 - u0) * fly * 1000)})"
        lines.append(f"Dialogue: 7,{_ts(a)},{_ts(b)},Sub,,0,0,0,,{{\\an5{mv}\\frz{ang:.0f}\\bord0\\shad0\\1c&H00FFFFFF&"
                     f"\\fscx140\\fscy140\\p1}}{_PLANE}")
    if note:
        lines.append(f"Dialogue: 6,{_ts(start + fly)},{_ts(end)},Sub,,0,0,0,,{{\\an2\\pos(540,{c[1] + 90})\\fn{'Caveat'}\\fs84"
                     f"\\bord0\\shad0\\c{acc}&\\fad(200,200)}}{_esc(note)}")
    return lines, Window(start, end)


def viaje_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Itinerario de varias paradas: la ruta se dibuja de ciudad en ciudad, con el avión, los nombres y las fechas."""
    stops = [x.strip()[:16] for x in effect["text"].replace("→", "›").replace(">", "›").split("›") if x.strip()][:6]
    if len(stops) < 2:
        return [], None
    span = _span(effect, clock, duration, max(4.0, 1.3 * len(stops)), 2.6)
    if not span:
        return [], None
    start, end = span
    acc = _accent(style)
    title, dates = effect.get("title", "").strip()[:28], effect.get("subtitle", "").strip()[:28]
    n = len(stops)
    top, bottom = 560, 1180
    pts = [(250 if k % 2 == 0 else 830, top + (bottom - top) * k / (n - 1)) for k in range(n)]
    leg = min(1.1, (end - start) * 0.75 / (n - 1))  # segundos por tramo
    t = f"{_ts(start)},{_ts(end)}"
    lines = [_dim(start, end, "30")]
    if title:
        size = textfit.fit(title, "Anton", 96, 860, 56)
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an8\\pos(540,300)\\fnAnton\\fs{size:.0f}\\bord0\\shad0"
                     f"\\c&H00FFFFFF&\\fad(200,200)\\fscx90\\fscy90\\t(0,220,\\fscx100\\fscy100)}}{_esc(title.upper())}")
    if dates:
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an8\\pos(540,{420 if title else 330})\\fnCaveat\\fs80\\bord0\\shad0"
                     f"\\c{acc}&\\fad(300,200)}}{_esc(dates)}")
    for k, (x0, y0) in enumerate(pts):
        when = start + k * leg
        ms = int((when - start) * 1000)
        lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an5\\pos({x0:.0f},{y0:.0f})\\bord0\\shad0\\1c&H00FFFFFF&\\alpha&HFF&"
                     f"\\fscx40\\fscy40\\t({ms},{ms + 200},\\alpha&H00&\\fscx100\\fscy100)\\fad(0,200)\\p1}}{_circle(40)}")
        an = 4 if k % 2 == 0 else 6
        nx = x0 + (40 if k % 2 == 0 else -40)
        size = textfit.fit(stops[k], "Figtree ExtraBold", 66, 360, 40)
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an{an}\\pos({nx:.0f},{y0:.0f})\\fnFigtree ExtraBold\\fs{size:.0f}\\bord0"
                     f"\\shad2\\c&H00FFFFFF&\\alpha&HFF&\\t({ms},{ms + 220},\\alpha&H00&)\\fad(0,200)}}{_esc(stops[k])}")
        if k == n - 1:
            break
        x1, y1 = pts[k + 1]
        steps = 12
        for j in range(1, steps):
            u = j / steps
            px, py = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
            dms = ms + int(u * leg * 1000)
            lines.append(f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an5\\pos({px:.0f},{py:.0f})\\bord0\\shad0\\1c{acc}&\\alpha&HFF&"
                         f"\\t({dms},{dms + 60},\\alpha&H00&)\\fad(0,200)\\p1}}{_circle(12)}")
        ang = -math.degrees(math.atan2(y1 - y0, x1 - x0))
        b = when + leg if k < n - 2 else end
        lines.append(f"Dialogue: 7,{_ts(when)},{_ts(b)},Sub,,0,0,0,,{{\\an5\\move({x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f},0,"
                     f"{int(leg * 1000)})\\frz{ang:.0f}\\bord0\\shad0\\1c&H00FFFFFF&\\fscx130\\fscy130\\p1}}{_PLANE}")
    return lines, Window(start, end)


def testimonio_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Tarjeta de reseña: cinco estrellas, la frase del alumno o cliente y su nombre."""
    span = _span(effect, clock, duration, 3.4, 2.2)
    if not span:
        return [], None
    start, end = span
    quote, who = effect["text"].strip()[:110], effect.get("subtitle", "").strip()[:40]
    w, x = 900, (W - 900) / 2
    rows = _wrap(f"«{quote}»", "Figtree SemiBold", 54, w - 120)[:4]
    h = 130 + len(rows) * 66 + (80 if who else 30)
    y = 1250 - h
    t = f"{_ts(start)},{_ts(end)}"
    up = f"\\move({x:.0f},{y + 80:.0f},{x:.0f},{y:.0f},0,260)"
    lines = [f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7{up}\\bord0\\shad0\\1c&H00FFFFFF&\\fad(120,200)\\p1}}{_rect(0, 0, w, h, 30)}"]
    for k in range(5):
        ms = 200 + 90 * k
        lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an7\\move({x:.0f},{y + 80:.0f},{x:.0f},{y:.0f},0,260)\\bord0\\shad0"
                     f"\\1c{rgb('#F5B400')}&\\alpha&HFF&\\t({ms},{ms + 120},\\alpha&H00&)\\fad(0,200)\\p1}}"
                     f"{_star(80 + k * 64, 70, 28)}")
    for r, row in enumerate(rows):
        lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an7\\move({x + 60:.0f},{y + 210 + r * 66:.0f},{x + 60:.0f},"
                     f"{y + 130 + r * 66:.0f},0,260)\\fnFigtree SemiBold\\fs54\\bord0\\shad0\\c{INK}&\\fad(120,200)}}"
                     f"{_esc(row)}")
    if who:
        yy = y + 130 + len(rows) * 66 + 18
        lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an7\\move({x + 60:.0f},{yy + 80:.0f},{x + 60:.0f},{yy:.0f},0,260)"
                     f"\\fnFigtree ExtraBold\\fs42\\bord0\\shad0\\c{_accent(style)}&\\fad(120,200)}}— {_esc(who)}")
    return lines, Window(start, end)


def plazas_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Aviso de escasez arriba ("Solo 7 plazas"), con un punto que late."""
    span = _span(effect, clock, duration, 2.6, 1.6)
    if not span:
        return [], None
    start, end = span
    text = effect["text"].strip().upper()[:28]
    size = textfit.fit(text, "Figtree ExtraBold", 58, 760, 40)
    w = textfit.width(text, "Figtree ExtraBold", size) + 150
    x, y = (W - w) / 2, 290
    t = f"{_ts(start)},{_ts(end)}"
    red = rgb("#E63A2E")
    beats = "".join(f"\\t({i * 600},{i * 600 + 300},\\fscx150\\fscy150\\alpha&H60&)"
                    f"\\t({i * 600 + 300},{i * 600 + 600},\\fscx100\\fscy100\\alpha&H00&)"
                    for i in range(int((end - start) / 0.6) + 1))
    drop = "\\fscy60\\t(0,160,\\fscy100)\\fad(0,200)\\bord0\\shad0"
    return [
        f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7\\pos({x:.0f},{y}){drop}\\1c{red}&\\p1}}{_rect(0, 0, w, 100, 50)}",
        f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an5\\pos({x + 56:.0f},{y + 50})\\bord0\\shad0\\1c&H00FFFFFF&\\fad(0,200){beats}"
        f"\\p1}}{_circle(28)}",
        f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an4\\pos({x + 100:.0f},{y + 52}){drop}\\fnFigtree ExtraBold\\fs{size:.0f}"
        f"\\c&H00FFFFFF&}}{_esc(text)}",
    ], None


def precio_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Etiqueta de precio: el precio de antes tachado, el nuevo grande y una pegatina de descuento."""
    span = _span(effect, clock, duration, 2.6, 1.6)
    if not span:
        return [], None
    start, end = span
    new, old, tag = effect["text"].strip()[:12], effect.get("subtitle", "").strip()[:12], effect.get("title", "").strip()[:10]
    acc = _accent(style)
    ns = textfit.fit(new, "Figtree ExtraBold", 150, 520, 80)
    nw = textfit.width(new, "Figtree ExtraBold", ns)
    ow = textfit.width(old, "Figtree ExtraBold", 64) if old else 0
    w = max(nw, ow) + 120
    h = ns * 1.1 + (90 if old else 0) + 60
    x, y = 600 - w / 2, 400
    t = f"{_ts(start)},{_ts(end)}"
    pop = "\\frz-4\\fscx70\\fscy70\\t(0,170,\\fscx100\\fscy100)\\fad(0,200)\\bord0\\shad0"
    lines = [f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7\\pos({x:.0f},{y}){pop}\\1c{CREAM}&\\p1}}{_rect(0, 0, w, h, 26)}"]
    yy = y + 30
    if old:
        lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an8\\pos({x + w / 2:.0f},{yy}){pop}\\fnFigtree ExtraBold\\fs64"
                     f"\\c&H00808080&\\s1}}{_esc(old)}")
        yy += 90
    lines.append(f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an8\\pos({x + w / 2:.0f},{yy:.0f}){pop}\\fnFigtree ExtraBold\\fs{ns:.0f}"
                 f"\\c{INK}&}}{_esc(new)}")
    if tag:
        ts = textfit.fit(tag, "Figtree ExtraBold", 56, 190, 34)
        r = 105
        sticker = (f"\\an5\\pos({x + w - 10:.0f},{y + 10})\\frz12\\bord0\\shad0\\fscx10\\fscy10"
                   f"\\t(220,380,\\fscx100\\fscy100)\\fad(0,200)")
        lines.append(f"Dialogue: 6,{t},Sub,,0,0,0,,{{{sticker}\\1c{acc}&\\p1}}{_star(r, r, r, 14, 0.84)}")
        lines.append(f"Dialogue: 7,{t},Sub,,0,0,0,,{{{sticker}\\fnFigtree ExtraBold\\fs{ts:.0f}\\c&H00FFFFFF&}}{_esc(tag)}")
    return lines, None


def notificaciones_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Notificaciones que caen y se apilan ("Nuevo pedido", "Reserva confirmada"…), una tras otra."""
    span = _span(effect, clock, duration, 3.4, 2.0)
    if not span:
        return [], None
    start, end = span
    items = [x.strip()[:46] for x in effect["text"].replace("›", "|").split("|") if x.strip()][:4]
    title = (effect.get("title") or "Ahora").strip()[:18]
    if not items:
        return [], None
    acc = _accent(style)
    w, h, x = 860, 150, (W - 860) / 2
    step = max(0.15, min(0.45, (end - start - 0.6) / max(1, len(items))))
    lines = [_dim(start, end, "90")]
    for k, msg in enumerate(items):
        a = start + k * step
        # La nueva cae arriba y empuja a las anteriores hacia abajo.
        y_final = 330 + (len(items) - 1 - k) * (h + 22)
        t = f"{_ts(a)},{_ts(end)}"
        mv = f"\\move({x:.0f},{y_final - 260},{x:.0f},{y_final},0,260)"
        fade = "\\fad(120,200)\\bord0"
        size = textfit.fit(msg, "Figtree ExtraBold", 44, w - 210, 30)
        lines += [
            f"Dialogue: 4,{t},Sub,,0,0,0,,{{\\an7{mv}{fade}\\shad6\\4c&H000000&\\4a&HB0&\\1c&HF8F8F8&\\p1}}"
            f"{_rect(0, 0, w, h, 38)}",
            f"Dialogue: 5,{t},Sub,,0,0,0,,{{\\an7\\move({x + 34:.0f},{y_final - 260 + 34},{x + 34:.0f},{y_final + 34},0,260)"
            f"{fade}\\shad0\\1c{acc}&\\p1}}{_rect(0, 0, 82, 82, 22)}",
            f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an7\\move({x + 148:.0f},{y_final - 260 + 28},{x + 148:.0f},{y_final + 28},0,260)"
            f"{fade}\\shad0\\fnFigtree ExtraBold\\fs30\\c&H00808080&}}{_esc(title.upper())}",
            f"Dialogue: 6,{t},Sub,,0,0,0,,{{\\an7\\move({x + 148:.0f},{y_final - 260 + 66},{x + 148:.0f},{y_final + 66},0,260)"
            f"{fade}\\shad0\\fnFigtree ExtraBold\\fs{size:.0f}\\c{INK}&}}{_esc(msg)}",
        ]
    return lines, None


def foco_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Foco: los bordes se oscurecen poco a poco y solo queda la luz sobre ti, para el momento clave."""
    span = _span(effect, clock, duration, 2.8, 1.4)
    if not span:
        return [], None
    start, end = span
    t = f"{_ts(start)},{_ts(end)}"
    lines = []
    # Seis óvalos con un borde enorme y muy transparente: al sumarse, la sombra crece suave hacia los bordes.
    for k in range(6):
        d = 760 + k * 130
        lines.append(f"Dialogue: 3,{t},Sub,,0,0,0,,{{\\an7\\pos({(W - d) / 2:.0f},{700 - d * 0.675:.0f})\\fscy135"
                     f"\\1a&HFF&\\3c&H000000&\\bord900\\blur90\\shad0\\3a&HFF&\\t(0,600,\\3a&HC8&)"
                     f"\\fad(0,300)\\p1}}{_circle(d)}")
    text = effect.get("text", "").strip()
    if text and text != "-":
        size = textfit.fit(text, "Playfair Display ExtraBold", 92, 900, 52)
        lines.append(f"Dialogue: 5,{_ts(start + 0.3)},{_ts(end)},Sub,,0,0,0,,{{\\an2\\pos({W / 2:.0f},1480)"
                     f"\\fnPlayfair Display ExtraBold\\fs{size:.0f}\\i1\\bord0\\shad0\\blur8\\alpha&HFF&"
                     f"\\t(0,350,\\blur0\\alpha&H00&)\\fad(0,250)}}{_esc(text)}")
    return lines, None


def anillo_events(effect: dict, clock: WordClock, style: Style, duration: float) -> tuple[list[str], Window | None]:
    """Anillo de texto que gira alrededor de tu cabeza: las letras de detrás se ven más pequeñas y apagadas."""
    span = _span(effect, clock, duration, 3.2, 1.8)
    if not span:
        return [], None
    start, end = span
    text = effect["text"].strip().upper()[:26]
    if not text:
        return [], None
    ring = f"{text} • " * (2 if len(text) < 13 else 1)
    n = len(ring)
    cx, cy, rx, ry = W / 2, 660, 420, 120  # elipse inclinada alrededor de la cabeza
    acc = _accent(style)
    fps, speed = 15, 0.9  # cuadros por segundo del anillo, vueltas por… radianes por segundo
    lines = []
    frames = int((end - start) * fps)
    for f in range(frames):
        t0, t1 = start + f / fps, min(end, start + (f + 1) / fps)
        ang0 = (t0 - start) * speed
        for k, ch in enumerate(ring):
            if ch == " ":
                continue
            a = ang0 + 2 * math.pi * k / n
            depth = math.sin(a)  # >0 delante, <0 detrás
            x, y = cx + rx * math.cos(a), cy + ry * depth
            sc = 100 + 18 * depth
            alpha = "00" if depth > 0 else "A0"
            layer = 6 if depth > 0 else 2
            fade = "\\fad(250,0)" if f == 0 else ("\\fad(0,250)" if f == frames - 1 else "")
            lines.append(f"Dialogue: {layer},{_ts(t0)},{_ts(t1)},Sub,,0,0,0,,{{\\an5\\pos({x:.0f},{y:.0f})"
                         f"\\fnAnton\\fs84\\fscx{sc:.0f}\\fscy{sc:.0f}\\frz{-12 * math.cos(a):.0f}\\bord3\\3c&H000000&"
                         f"\\shad0\\1c{acc}&\\alpha&H{alpha}&{fade}}}{_esc(ch)}")
    return lines, None


PACK_BUILDERS = {
    "ubicacion": ubicacion_events,
    "oferta": oferta_events,
    "ruta": ruta_events,
    "viaje": viaje_events,
    "testimonio": testimonio_events,
    "plazas": plazas_events,
    "precio": precio_events,
    "notificaciones": notificaciones_events,
    "foco": foco_events,
    "anillo": anillo_events,
}
