"""Portadas que se pinchan (tipo YouTube): tú recortado, con luz de borde y la cara realzada, sobre un fondo
que no compite contigo y con el texto en grande. Tres variantes por reel, en vertical (portada del reel) y
en horizontal (miniatura de YouTube).

Todo en local con el mismo recorte de persona que usan los efectos; sin servicios de pago.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from . import fondos, segment
from .textfit import font_path

VARIANTS = {"brillo": "Brillo de marca", "real": "Tu fondo, desenfocado", "pop": "Pegatina"}
FORMATS = {"vertical": (1080, 1920), "horizontal": (1280, 720)}


def _rgb(hex_: str, default: str = "#FF5547") -> tuple[int, int, int]:
    h = (hex_ if hex_ and hex_.startswith("#") and len(hex_) == 7 else default).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _light(c) -> bool:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] > 165


def _cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    k = max(size[0] / img.width, size[1] / img.height)
    im = img.resize((math.ceil(img.width * k), math.ceil(img.height * k)), Image.LANCZOS)
    x, y = (im.width - size[0]) // 2, (im.height - size[1]) // 3
    return im.crop((x, y, x + size[0], y + size[1]))


def _enhance(img: Image.Image) -> Image.Image:
    """Cara realzada: un poco más de luz, contraste y color, y nitidez (sin pasarse: que siga siendo tu cara)."""
    img = ImageEnhance.Brightness(img).enhance(1.06)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Color(img).enhance(1.12)
    return img.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))


def _person(frame: Image.Image, mask: Image.Image, height: int) -> tuple[Image.Image, Image.Image]:
    """La persona recortada (RGBA) a `height` px de alto, y su máscara."""
    box = mask.point(lambda v: 255 if v > 40 else 0).getbbox() or (0, 0, *frame.size)
    x0, y0, x1, y1 = box
    pad = int((x1 - x0) * 0.04)
    box = (max(0, x0 - pad), max(0, y0 - pad), min(frame.width, x1 + pad), y1)
    face, m = frame.crop(box), mask.crop(box)
    k = height / face.height
    size = (max(1, int(face.width * k)), height)
    face, m = _enhance(face.resize(size, Image.LANCZOS)), m.resize(size, Image.LANCZOS)
    out = face.convert("RGBA")
    out.putalpha(m)
    return out, m


def _rim(mask: Image.Image, color, width: int) -> Image.Image:
    """Luz de borde: un halo del color de la marca por detrás de la silueta."""
    big = mask.filter(ImageFilter.MaxFilter(width | 1)).filter(ImageFilter.GaussianBlur(width))
    glow = Image.new("RGBA", mask.size, color + (0,))
    glow.putalpha(big.point(lambda v: int(v * 0.9)))
    return glow


def _edge_light(person: Image.Image, mask: Image.Image, color) -> Image.Image:
    """El borde de la persona iluminado por dentro, como un contraluz."""
    inner = mask.filter(ImageFilter.MinFilter(9))
    edge = ImageChops.subtract(mask, inner).filter(ImageFilter.GaussianBlur(3))
    light = Image.new("RGBA", mask.size, tuple(min(255, int(c * 0.5 + 128)) for c in color) + (0,))
    light.putalpha(edge.point(lambda v: int(v * 0.55)))
    return Image.alpha_composite(person, light)


def _sticker(mask: Image.Image, width: int) -> Image.Image:
    """Borde blanco grueso de pegatina alrededor de la silueta."""
    big = mask.filter(ImageFilter.MaxFilter(width | 1)).point(lambda v: 255 if v > 90 else 0)
    big = big.filter(ImageFilter.GaussianBlur(1.2))
    white = Image.new("RGBA", mask.size, (255, 255, 255, 0))
    white.putalpha(big)
    return white


def _background(variant: str, frame: Image.Image, size, acc, sec: str) -> Image.Image:
    if variant == "real":
        bg = _cover(frame, size).filter(ImageFilter.GaussianBlur(max(size) // 60))
        return ImageEnhance.Brightness(bg).enhance(0.55).convert("RGBA")
    if variant == "pop":
        bg = Image.new("RGBA", size, acc + (255,))
        d = ImageDraw.Draw(bg)
        cx, cy, r = size[0] * 0.62, size[1] * 0.55, max(size) * 1.2
        lighter = tuple(min(255, int(c * 0.85 + 40)) for c in acc) + (255,)
        for k in range(18):  # rayos de sol detrás de la pegatina
            a0, a1 = 2 * math.pi * k / 18, 2 * math.pi * (k + 0.5) / 18
            d.polygon([(cx, cy), (cx + r * math.cos(a0), cy + r * math.sin(a0)),
                       (cx + r * math.cos(a1), cy + r * math.sin(a1))], fill=lighter)
        return bg
    with tempfile.TemporaryDirectory() as tmp:
        p = fondos.render("color", "#%02X%02X%02X" % acc, sec, Path(tmp) / "f.jpg")
        return _cover(Image.open(p).convert("RGB"), size).convert("RGBA")


def _fit_font(family: str, lines: list[str], max_w: int, size: int) -> ImageFont.FreeTypeFont:
    path = str(font_path(family))
    font = ImageFont.truetype(path, size)
    while max(font.getlength(ln) for ln in lines) > max_w and size > 30:
        size -= 4
        font = ImageFont.truetype(path, size)
    return font


def _lines(text: str, max_words: int = 3) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [" ".join(words)]
    half = math.ceil(len(words) / 2)
    return [" ".join(words[:half]), " ".join(words[half:])]


def _title(canvas: Image.Image, text: str, variant: str, area, acc, family: str) -> None:
    """Texto grande; la última palabra destacada (caja de color, amarillo o borde, según la variante)."""
    text = " ".join(text.upper().split()[:7])
    if not text:
        return
    x0, y0, x1, y1 = area
    lines = _lines(text)
    font = _fit_font(family, lines, x1 - x0, int((y1 - y0) / (len(lines) * 1.05)))
    d = ImageDraw.Draw(canvas)
    lh = font.size * 1.04
    y = y0 + ((y1 - y0) - lh * len(lines)) / 2
    on_acc = (20, 21, 24) if _light(acc) else (255, 255, 255)
    for i, ln in enumerate(lines):
        last = i == len(lines) - 1
        head, _, tail = ln.rpartition(" ") if last and " " in ln else ("", "", ln) if last else (ln, "", "")
        x = x0
        stroke = max(4, font.size // 14)
        if head:
            d.text((x, y), head + " ", font=font, fill=(255, 255, 255), stroke_width=stroke, stroke_fill=(10, 10, 12))
            x += font.getlength(head + " ")
        if tail:
            if variant in ("brillo", "pop"):  # caja: del color de la marca, o negra sobre el fondo de color
                bx0, by0, bx1, by1 = d.textbbox((x, y), tail, font=font)
                pad = font.size // 9
                d.rounded_rectangle((bx0 - pad, by0 - pad, bx1 + pad, by1 + pad), pad + 6,
                                    fill=acc if variant == "brillo" else (16, 16, 18))
                d.text((x, y), tail, font=font, fill=on_acc if variant == "brillo" else (255, 255, 255))
            else:
                d.text((x, y), tail, font=font, fill=(255, 214, 10), stroke_width=stroke, stroke_fill=(10, 10, 12))
        y += lh


def render(frame: Image.Image, title: str, variant: str, fmt: str, accent: str = "#FF5547",
           secondary: str = "", family: str = "Anton", mask: Image.Image | None = None) -> Image.Image:
    size = FORMATS[fmt]
    W, H = size
    acc = _rgb(accent)
    frame = frame.convert("RGB")
    mask = mask if mask is not None else segment.person_mask(frame)
    canvas = _background(variant, frame, size, acc, secondary)
    if fmt == "vertical":
        text_area = (70, 170, W - 70, int(H * 0.34))
        p_h, p_x = int(H * 0.66), None
    else:
        text_area = (50, 60, int(W * 0.56), H - 60)
        p_h, p_x = int(H * 0.98), None
    if mask is None:  # sin recorte: tu fotograma entero, un poco oscurecido, y el texto encima
        canvas = Image.alpha_composite(canvas, ImageEnhance.Brightness(_cover(frame, size)).enhance(0.8).convert("RGBA"))
    else:
        person, m = _person(frame, mask, p_h)
        p_x = (W - person.width) // 2 if fmt == "vertical" else W - person.width + int(person.width * 0.05)
        p_y = H - person.height
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        if variant == "pop":
            layer.alpha_composite(_sticker(m, 31), (p_x, p_y))
            shadow = Image.new("RGBA", size, (0, 0, 0, 0))
            shadow.alpha_composite(_sticker(m, 31), (p_x + 18, p_y + 18))
            canvas = Image.alpha_composite(canvas, _tint(shadow, (0, 0, 0), 0.35))
        else:
            glow = _rim(m, acc if variant == "brillo" else (255, 255, 255), 41 if variant == "brillo" else 25)
            layer.alpha_composite(glow, (p_x, p_y))
        canvas = Image.alpha_composite(canvas, layer)
        canvas.alpha_composite(_edge_light(person, m, acc if variant != "pop" else (255, 255, 255)), (p_x, p_y))
    _title(canvas, title, variant, text_area, acc, family)
    return canvas.convert("RGB")


def _tint(layer: Image.Image, color, alpha: float) -> Image.Image:
    a = layer.getchannel("A").point(lambda v: int(v * alpha))
    out = Image.new("RGBA", layer.size, color + (0,))
    out.putalpha(a)
    return out


def best_frames(paths: list[Path], n: int = 3) -> list[Path]:
    """Los fotogramas más nítidos en los que se te ve bien (la persona ocupa un buen trozo y la cara está arriba)."""
    from PIL import ImageStat

    scored = []
    for p in paths:
        with Image.open(p) as im:
            g = im.convert("L").resize((270, 480))
            sharp = ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0]
            sub = segment.subject(im)
        bonus = 1.0 if sub is None else (1.4 if 0.03 < sub[1] < 0.45 else 1.0)
        scored.append((sharp * bonus, p))
    return [p for _, p in sorted(scored, key=lambda s: -s[0])[:n]]


def render_all(frames: list[Path], title: str, outdir: Path, accent: str, secondary: str = "",
               family: str = "Anton") -> list[str]:
    """Las 3 variantes en los dos formatos; cada variante con un fotograma distinto si hay varios buenos."""
    outdir.mkdir(parents=True, exist_ok=True)
    picks = best_frames(frames, 3) or frames[:1]
    names = []
    for k, variant in enumerate(VARIANTS):
        frame = Image.open(picks[k % len(picks)]).convert("RGB")
        mask = segment.person_mask(frame)
        for fmt in FORMATS:
            name = f"portada-{variant}-{fmt}.jpg"
            render(frame, title, variant, fmt, accent, secondary, family, mask).save(outdir / name, quality=92)
            names.append(name)
    return names


