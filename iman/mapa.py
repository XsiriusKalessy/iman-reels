"""Mapa 3D del itinerario: la cámara sobrevuela un mapa inclinado mientras la ruta se dibuja de ciudad en ciudad.

Se pinta con Pillow fotograma a fotograma y sale un vídeo que se monta como plano de apoyo a pantalla
completa (el creador sigue en un círculo). Los datos del mapa son de Natural Earth (dominio público):
costas, fronteras y unas 7.000 ciudades para encontrar las paradas sin conexión.
"""

from __future__ import annotations

import gzip
import json
import math
import re
import subprocess
import unicodedata
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .textfit import FILES, FONTS_DIR

DATA = Path(__file__).parent / "assets" / "mapa"
W, H = 1080, 1920
FPS = 30

OCEAN = (11, 28, 44)
LAND = (40, 64, 84)
COAST = (74, 104, 128)
BORDER = (58, 84, 106)
SKY_TOP, SKY_LOW = (8, 16, 26), (30, 58, 82)

# Nombres en español que no salen en los datos (en inglés).
ALIAS = {
    "tokio": "tokyo", "kioto": "kyoto", "pekin": "beijing", "nueva york": "new york", "londres": "london",
    "moscu": "moscow", "el cairo": "cairo", "estambul": "istanbul", "atenas": "athens", "roma": "rome",
    "florencia": "florence", "venecia": "venice", "napoles": "naples", "milan": "milan", "turin": "turin",
    "paris": "paris", "berlin": "berlin", "munich": "munich", "viena": "vienna", "praga": "prague",
    "varsovia": "warsaw", "cracovia": "krakow", "bruselas": "brussels", "amberes": "antwerp",
    "copenhague": "copenhagen", "estocolmo": "stockholm", "edimburgo": "edinburgh", "dublin": "dublin",
    "lisboa": "lisbon", "oporto": "porto", "ginebra": "geneva", "zurich": "zurich", "basilea": "basel",
    "marrakech": "marrakesh", "fez": "fes", "tanger": "tangier", "ciudad del cabo": "cape town",
    "johannesburgo": "johannesburg", "nueva delhi": "new delhi", "bombay": "mumbai", "calcuta": "kolkata",
    "seul": "seoul", "shanghai": "shanghai", "hong kong": "hong kong", "singapur": "singapore",
    "bangkok": "bangkok", "hanoi": "hanoi", "ciudad ho chi minh": "ho chi minh city", "saigon": "ho chi minh city",
    "katmandu": "kathmandu", "dubai": "dubai", "abu dabi": "abu dhabi", "jerusalen": "jerusalem",
    "ammam": "amman", "petra": "wadi musa", "nueva orleans": "new orleans", "filadelfia": "philadelphia",
    "san francisco": "san francisco", "los angeles": "los angeles", "las vegas": "las vegas",
    "ciudad de mexico": "mexico city", "la habana": "havana", "cartagena de indias": "cartagena",
    "sao paulo": "sao paulo", "rio de janeiro": "rio de janeiro", "cuzco": "cusco", "osaka": "osaka",
    "hiroshima": "hiroshima", "nara": "nara", "sapporo": "sapporo", "nagoya": "nagoya",
    "ikebukuro": "tokyo", "gero": "takayama", "takayama": "takayama", "hakone": "odawara",
    "bali": "denpasar", "phuket": "phuket", "maldivas": "male", "zanzibar": "zanzibar",
    "islandia": "reykjavik", "reikiavik": "reykjavik", "laponia": "rovaniemi", "tenerife": "santa cruz de tenerife",
    "mallorca": "palma", "ibiza": "ibiza", "menorca": "mahon", "gran canaria": "las palmas",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


@lru_cache(maxsize=1)
def _places() -> dict[str, tuple[float, float, int]]:
    out: dict[str, tuple[float, float, int]] = {}
    with gzip.open(DATA / "lugares.tsv.gz", "rt", encoding="utf-8") as f:
        for row in f:
            name, ascii_, alt, _country, lat, lon, pop = row.rstrip("\n").split("\t")
            rec = (float(lat), float(lon), int(pop))
            for n in {name, ascii_, *alt.split("|")}:
                k = _norm(n)
                if k and (k not in out or out[k][2] < rec[2]):
                    out[k] = rec
    return out


def geocode(name: str) -> tuple[float, float] | None:
    k = _norm(name)
    k = ALIAS.get(k, k)
    hit = _places().get(k)
    return (hit[0], hit[1]) if hit else None


_COORDS = re.compile(r"\(\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)\s*\)")


def strip_coords(text: str) -> str:
    return _COORDS.sub("", text or "")


def stops(text: str) -> list[tuple[str, float, float]] | None:
    """Las paradas de "Tokio (35.68, 139.69) › Kioto › Osaka", con coordenadas; None si falta alguna."""
    out = []
    for raw in re.split(r"›|→|>", text or ""):
        raw = raw.strip()
        if not raw:
            continue
        m = _COORDS.search(raw)
        label = _COORDS.sub("", raw).strip()[:18]
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
            if not (-85 <= lat <= 85 and -180 <= lon <= 180):
                return None
        else:
            hit = geocode(label)
            if not hit:
                return None
            lat, lon = hit
        out.append((label, lat, lon))
    return out[:6] if len(out) >= 2 else None


@lru_cache(maxsize=1)
def _shapes():
    def load(name):
        with gzip.open(DATA / name, "rt") as f:
            rings = [np.array(r, dtype=np.float64).reshape(-1, 2) for r in json.load(f)]
        merc = [_merc(r[:, 0], r[:, 1]) for r in rings]
        boxes = np.array([[m[0].min(), m[1].min(), m[0].max(), m[1].max()] for m in merc])
        return merc, boxes

    return load("tierra.json.gz"), load("fronteras.json.gz")


def _merc(lon, lat):
    lat = np.clip(lat, -85, 85)
    return np.asarray(lon, dtype=np.float64), np.degrees(np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)))


def _homography(src, dst) -> np.ndarray:
    """Matriz 3x3 que lleva los 4 puntos `src` a `dst`."""
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        b += [u, v]
    h = np.linalg.solve(np.array(a, float), np.array(b, float))
    return np.append(h, 1).reshape(3, 3)


def _apply(m: np.ndarray, x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    d = m[2, 0] * x + m[2, 1] * y + m[2, 2]
    return (m[0, 0] * x + m[0, 1] * y + m[0, 2]) / d, (m[1, 0] * x + m[1, 1] * y + m[1, 2]) / d


def _ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def _font(family: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / FILES[family]), size)


_PLANE = [
    [(0, -5), (46, -5), (56, -4), (62, 0), (56, 4), (46, 5), (0, 5)],
    [(20, -5), (8, -34), (17, -34), (36, -5)], [(20, 5), (8, 34), (17, 34), (36, 5)],
    [(2, -5), (-6, -17), (2, -17), (10, -5)], [(2, 5), (-6, 17), (2, 17), (10, 5)],
]


def _plane(draw: ImageDraw.ImageDraw, x: float, y: float, ang: float, k: float, color) -> None:
    c, s = math.cos(ang), math.sin(ang)
    for poly in _PLANE:
        pts = [((px - 28) * k * c - py * k * s + x, (px - 28) * k * s + py * k * c + y) for px, py in poly]
        draw.polygon(pts, fill=color)


def _arc(p0, p1, n: int = 40) -> np.ndarray:
    """Curva de vuelo entre dos puntos del plano (mercator), un poco arqueada."""
    (x0, y0), (x1, y1) = p0, p1
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    cx, cy = mx - dy * 0.18, my + dx * 0.18
    u = np.linspace(0, 1, n)[:, None]
    a, b, c = np.array([x0, y0]), np.array([cx, cy]), np.array([x1, y1])
    return (1 - u) ** 2 * a + 2 * (1 - u) * u * b + u ** 2 * c


def _sky() -> Image.Image:
    g = np.linspace(0, 1, H)[:, None, None]
    top, low = np.array(SKY_TOP, float), np.array(SKY_LOW, float)
    sky = top + (low - top) * np.clip(g / 0.33, 0, 1) ** 1.6
    return Image.fromarray(np.broadcast_to(sky, (H, W, 3)).astype(np.uint8))


def ass_hex(color: str) -> str:
    """'&H00BBGGRR' (ASS) o '#RRGGBB' -> '#RRGGBB'; dorado si no hay color."""
    c = (color or "").strip()
    if c.startswith("#") and len(c) == 7:
        c = "&H00" + c[5:7] + c[3:5] + c[1:3]
    m = re.fullmatch(r"&H(?:[0-9A-Fa-f]{2})?([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})&?", c)
    if m:
        r, g, b = (int(x, 16) for x in (m.group(3), m.group(2), m.group(1)))
        if 0.2126 * r + 0.7152 * g + 0.0722 * b < 225:  # el blanco no destaca sobre el mapa
            return f"#{r:02X}{g:02X}{b:02X}"
    return "#FFC23D"


def cached(route, duration: float, title: str = "", dates: str = "", accent: str = "#FFC23D") -> Path:
    """El vídeo del mapa, reutilizado si ya se pintó igual (al reeditar no se vuelve a pintar)."""
    import hashlib

    from . import config

    key = hashlib.sha1(json.dumps([route, round(duration, 2), title, dates, accent, 1]).encode()).hexdigest()[:16]
    out = config.HOME / "cache" / "mapas" / f"{key}.mp4"
    if not out.exists():
        tmp = out.with_suffix(".tmp.mp4")
        render(route, duration, tmp, title.strip()[:28], dates.strip()[:28], accent)
        tmp.replace(out)
    return out


def render(route: list[tuple[str, float, float]], duration: float, dst: Path, title: str = "", dates: str = "",
           accent: str = "#FFC23D") -> Path:
    """Vídeo del mapa (1080x1920, 30 fps, sin sonido) de `duration` segundos."""
    acc = tuple(int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    mx, my = _merc([r[2] for r in route], [r[1] for r in route])
    pts = list(zip(mx.tolist(), my.tolist()))
    # Encuadre del plano: la ruta ocupa el centro con margen; mínimo de ~4 grados para que se vea el entorno.
    x0, x1, y0, y1 = mx.min(), mx.max(), my.min(), my.max()
    span = max(x1 - x0, y1 - y0, 3.0) * 4.0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    BW, BH = 3000, 3000  # mapa plano de base, píxeles
    scale = BW / span  # píxeles por unidad mercator
    bx0, by1 = cx - span / 2, cy + span / 2 * BH / BW

    def to_base(x, y):
        return (np.asarray(x) - bx0) * scale, (by1 - np.asarray(y)) * scale

    land, borders = _shapes()
    base = Image.new("RGB", (BW, BH), OCEAN)
    d = ImageDraw.Draw(base)
    view = (bx0, by1 - BH / scale, bx0 + BW / scale, by1)
    for (rings, boxes), kind in ((land, "land"), (borders, "border")):
        hit = np.nonzero((boxes[:, 2] >= view[0]) & (boxes[:, 0] <= view[2]) &
                         (boxes[:, 3] >= view[1]) & (boxes[:, 1] <= view[3]))[0]
        for i in hit:
            u, v = to_base(*rings[i])
            xy = list(zip(u.tolist(), v.tolist()))
            if kind == "land" and len(xy) >= 3:
                d.polygon(xy, fill=LAND, outline=COAST, width=3)
            elif kind == "border":
                d.line(xy, fill=BORDER, width=2)
    # Retícula de meridianos y paralelos: da la sensación de suelo en 3D.
    deg = next(g for g in (1, 2, 5, 10, 20) if g >= span / 14)
    grid = (52, 76, 98)
    for lon in np.arange(math.floor(view[0] / deg) * deg, view[2] + deg, deg):
        u, _ = to_base(lon, 0)
        d.line([(float(u), 0), (float(u), BH)], fill=grid, width=2)
    lat_hi = math.degrees(2 * math.atan(math.exp(math.radians(view[3]))) - math.pi / 2)
    lat_lo = math.degrees(2 * math.atan(math.exp(math.radians(view[1]))) - math.pi / 2)
    for lat in np.arange(math.floor(lat_lo / deg) * deg, lat_hi + deg, deg):
        _, v = to_base(0, _merc(0, lat)[1])
        d.line([(0, float(v)), (BW, float(v))], fill=grid, width=2)
    base = base.filter(ImageFilter.SMOOTH)

    # Plano inclinado: el horizonte arriba y el suelo acercándose abajo.
    top_y, bot_y = 600, 2300
    quad = [(-260, top_y), (W + 260, top_y), (W + 1100, bot_y), (-1100, bot_y)]
    sky = _sky()
    fog = Image.linear_gradient("L").resize((W, H)).point(lambda p: 255 - min(255, int(max(0, p - 255 * top_y / H) * 5.0)))
    arcs = [_arc(pts[k], pts[k + 1]) for k in range(len(pts) - 1)]
    allx, ally = to_base(np.concatenate([a[:, 0] for a in arcs]), np.concatenate([a[:, 1] for a in arcs]))
    ccx, ccy = float(allx.min() + allx.max()) / 2, float(ally.min() + ally.max()) / 2

    def camera(fx, fy, ext, rot):
        corners = [(-ext, -ext), (ext, -ext), (ext, ext), (-ext, ext)]
        cs, sn = math.cos(rot), math.sin(rot)
        src = [(float(fx + a * cs - b * sn), float(fy + a * sn + b * cs)) for a, b in corners]
        m_out = _homography(quad, src)  # salida -> base
        return m_out, np.linalg.inv(m_out)

    # Lo justo de mapa para que toda la ruta quepa en el centro de la pantalla, girando a un lado y a otro.
    # Primero, cuánto adelantar la cámara para que el centro de la ruta caiga a la altura buscada (no depende del zoom).
    lo, hi = -0.9, 0.9
    for _ in range(30):
        off = (lo + hi) / 2
        _, y = _apply(camera(ccx, ccy + off * 500, 500, 0.0)[1], ccx, ccy)
        lo, hi = (lo, off) if float(y) < 900 else (off, hi)
    off = (lo + hi) / 2
    lo, hi = 50.0, BW / 2
    for _ in range(30):
        ext = (lo + hi) / 2
        ok = True
        for rot in (-0.08, 0.08):
            sx, sy = _apply(camera(ccx, ccy + off * ext, ext, rot)[1], allx, ally)
            ok &= bool(sx.min() > 150 and sx.max() < W - 150 and sy.min() > 680 and sy.max() < 1120)
        lo, hi = (lo, ext) if ok else (ext, hi)
    ext_fit = hi * 1.08  # margen para el empujón de la cámara
    n = len(route)
    intro, outro = 0.5, 0.5
    leg = max(0.5, (duration - intro - outro) / max(1, n - 1))
    label_f = _font("Figtree ExtraBold", 50)
    title_f = _font("Anton", 92)
    date_f = _font("Caveat", 76)

    # Dónde va cada etiqueta (encima, debajo o a un lado) para que no se pisen; se decide una vez.
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    m_end = camera(ccx, ccy + off * ext_fit, ext_fit, 0.0)[1]
    options = [(lambda tw: -tw / 2, -104), (lambda tw: -tw / 2, 44), (lambda tw: 40, -30), (lambda tw: -tw - 40, -30)]
    placed, sides = [], []
    for j, (label, _, _) in enumerate(route):
        sx, sy = (float(v) for v in _apply(m_end, *to_base(*pts[j])))
        tw = probe.textlength(label, font=label_f)
        for ox, oy in options:
            box = (sx + ox(tw) - 30, sy + oy - 12, sx + ox(tw) + tw + 30, sy + oy + 70)
            if not any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in placed):
                break
        placed.append(box)
        sides.append((ox, oy))

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    from .media import FFMPEG

    proc = subprocess.Popen(
        [FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(dst)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    frames = max(1, int(round(duration * FPS)))
    try:
        for f in range(frames):
            t = f / FPS
            # Progreso de la ruta: cuántos tramos lleva dibujados.
            prog = min(n - 1.0, max(0.0, (t - intro) / leg))
            k = min(n - 2, int(prog))
            u = _ease(prog - k) if prog < n - 1 else 1.0
            if prog >= n - 1:
                k, u = n - 2, 1.0
            head = arcs[k][min(len(arcs[k]) - 1, int(u * (len(arcs[k]) - 1)))]
            # Cámara: baja desde lejos al empezar y sigue un poco al avión.
            z = 0.78 + 0.22 * _ease(t / 0.9) + 0.06 * t / duration
            hx, hy = to_base(*head)
            ext = ext_fit / z
            fx, fy = ccx * 0.85 + float(hx) * 0.15, (ccy + off * ext_fit) * 0.85 + float(hy) * 0.15
            rot = math.radians(-4 + 8 * t / duration)
            m_out, m_in = camera(fx, fy, ext, rot)
            coeffs = (m_out / m_out[2, 2]).flatten()[:8]
            ground = base.transform((W, H), Image.PERSPECTIVE, tuple(coeffs), Image.BILINEAR, fillcolor=OCEAN)
            frame = Image.composite(sky, ground, fog)
            if t < 0.3:
                frame = Image.blend(Image.new("RGB", (W, H), SKY_TOP), frame, t / 0.3)

            glow = Image.new("RGBA", (W // 2, H // 2), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow)
            over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            od = ImageDraw.Draw(over)

            def scr(x, y):
                bx, by = to_base(x, y)
                return _apply(m_in, bx, by)

            for j in range(n - 1):
                if j > k or (j == k and u <= 0):
                    break
                seg = arcs[j] if j < k else arcs[j][: max(2, int(u * (len(arcs[j]) - 1)) + 1)]
                sx, sy = scr(seg[:, 0], seg[:, 1])
                line = list(zip(sx.tolist(), sy.tolist()))
                gd.line([(x / 2, y / 2) for x, y in line], fill=acc + (170,), width=14, joint="curve")
                od.line(line, fill=acc + (255,), width=9, joint="curve")
                od.line(line, fill=(255, 255, 255, 230), width=3, joint="curve")
            glow = glow.filter(ImageFilter.GaussianBlur(9)).resize((W, H))
            frame = frame.convert("RGBA")
            frame.alpha_composite(glow)
            frame.alpha_composite(over)
            pd = ImageDraw.Draw(frame)

            for j, (label, _, _) in enumerate(route):
                at = intro * 0.6 if j == 0 else intro + j * leg
                age = t - at
                if age < 0:
                    continue
                sx, sy = scr(*pts[j])
                sx, sy = float(sx), float(sy)
                pop = min(1.0, age / 0.18)
                pop = pop * (1 + 0.35 * math.sin(min(1.0, age / 0.3) * math.pi))
                if age < 0.7:  # onda que se abre al llegar
                    rr = 20 + 90 * age / 0.7
                    a = int(200 * (1 - age / 0.7))
                    pd.ellipse((sx - rr, sy - rr * 0.55, sx + rr, sy + rr * 0.55), outline=acc + (a,), width=5)
                r = 17 * pop
                pd.ellipse((sx - r - 7, sy - r - 7, sx + r + 7, sy + r + 7), fill=acc + (255,))
                pd.ellipse((sx - r, sy - r, sx + r, sy + r), fill=(255, 255, 255, 255))
                # Etiqueta: píldora oscura encima del punto.
                la = min(1.0, max(0.0, (age - 0.08) / 0.2))
                if la > 0:
                    tw = pd.textlength(label, font=label_f)
                    ox, oy = sides[j]
                    lx, ly = sx + ox(tw), sy + oy + 20 * (1 - la)
                    lx = min(W - tw - 70, max(40, lx))
                    pd.rounded_rectangle((lx - 26, ly - 8, lx + tw + 26, ly + 66), 37, fill=(10, 18, 28, int(215 * la)))
                    pd.text((lx, ly - 2), label, font=label_f, fill=(255, 255, 255, int(255 * la)))
            if t >= intro * 0.6 and prog < n - 1:
                nxt = arcs[k][min(len(arcs[k]) - 1, int(u * (len(arcs[k]) - 1)) + 1)]
                ax, ay = scr(head[0], head[1])
                bx, by = scr(nxt[0], nxt[1])
                ang = math.atan2(float(by - ay), float(bx - ax)) if (bx != ax or by != ay) else 0.0
                _plane(pd, float(ax), float(ay), ang, 1.25, (255, 255, 255, 255))

            ta = min(1.0, max(0.0, (t - 0.2) / 0.35))
            if title and ta > 0:
                tf = title_f
                while pd.textlength(title.upper(), font=tf) > 600 and tf.size > 50:
                    tf = _font("Anton", tf.size - 4)
                y = 300 + 30 * (1 - ta)
                pd.text((64, y), title.upper(), font=tf, fill=(255, 255, 255, int(255 * ta)))
                if dates:
                    pd.text((68, y + tf.size + 10), dates, font=date_f, fill=acc + (int(255 * ta),))
            proc.stdin.write(frame.convert("RGB").tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError(proc.stderr.read().decode(errors="ignore")[-400:])
    finally:
        if proc.poll() is None:
            proc.kill()
    return dst
