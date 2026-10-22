"""Kit de publicación: portada, carrusel e historias del mismo reel, con la marca del creador.

El texto lo escribe la IA (ai.kit_copy) a partir de lo que dices en el vídeo; aquí se dibuja con
Pillow usando las fuentes incluidas, los colores de la marca y fotogramas del propio reel.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import brand as brand_mod
from .models import Word
from .textfit import FILES, FONTS_DIR

CAROUSEL = (1080, 1350)
STORY = (1080, 1920)
INK = "#141518"
PAPER = "#F7F7F5"
RED = "#E63A2E"
BODY_FONT = "Figtree SemiBold"
MARGIN = 96


def _font(family: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / FILES[family]), size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        probe = f"{line} {word}".strip()
        if draw.textlength(probe, font=font) <= max_w or not line:
            line = probe
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _fit(draw, text: str, family: str, size: int, max_w: int, max_h: int, spacing: float = 1.08):
    """El mayor tamaño con el que el texto cabe en la caja; devuelve (fuente, líneas, alto de línea)."""
    while True:
        font = _font(family, size)
        lines = _wrap(draw, text, font, max_w)
        lh = int(size * spacing)
        if (len(lines) * lh <= max_h and all(draw.textlength(ln, font=font) <= max_w for ln in lines)) or size <= 28:
            return font, lines, lh
        size = int(size * 0.92)


def _text(draw, xy, lines, font, lh, fill, anchor="la"):
    x, y = xy
    for ln in lines:
        draw.text((x, y), ln, font=font, fill=fill, anchor=anchor)
        y += lh
    return y


def _cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    s = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 3
    return img.crop((x, y, x + w, y + h))


def _shade(img: Image.Image, top: float = 0.35, strength: int = 215) -> Image.Image:
    """Degradado oscuro de abajo arriba para que el texto se lea sobre la foto."""
    w, h = img.size
    grad = Image.new("L", (1, h))
    for y in range(h):
        k = max(0.0, (y / h - top) / (1 - top))
        grad.putpixel((0, y), int(strength * k ** 1.2))
    black = Image.new("RGB", img.size, "#000000")
    return Image.composite(black, img.convert("RGB"), grad.resize(img.size))


def _pill(draw, xy, text, font, bg, fg, pad=(26, 14)):
    x, y = xy
    w = draw.textlength(text, font=font)
    h = font.size
    draw.rounded_rectangle((x, y, x + w + 2 * pad[0], y + h + 2 * pad[1]), radius=(h + 2 * pad[1]) // 2, fill=bg)
    draw.text((x + pad[0], y + pad[1] + h * 0.78), text, font=font, fill=fg, anchor="ls")
    return x + w + 2 * pad[0]


class Look:
    def __init__(self, b: brand_mod.Brand):
        self.accent = b.primary if brand_mod.is_hex(b.primary or "") else RED
        self.on_accent = brand_mod.ink_on(self.accent)
        self.title = brand_mod.FONTS.get(b.font, "Playfair Display ExtraBold")
        self.handle = b.handle.strip()
        self.cta = b.cta.strip()
        self.logo = brand_mod.logo_card() if b.logo_path else None


def carousel_slide(i: int, n: int, slide: dict, look: Look, frame: Image.Image | None) -> Image.Image:
    W, H = CAROUSEL
    first, last = i == 0, i == n - 1
    if first and frame is not None:
        img = _shade(_cover(frame, CAROUSEL), top=0.25)
        fg, sub = "#FFFFFF", "#E6E6E6"
    elif last:
        img = Image.new("RGB", CAROUSEL, look.accent)
        fg = sub = look.on_accent
    else:
        dark = i % 2 == 0
        img = Image.new("RGB", CAROUSEL, INK if dark else PAPER)
        fg, sub = ("#FFFFFF", "#B9BBC0") if dark else (INK, "#5E6168")
    d = ImageDraw.Draw(img)
    small = _font(BODY_FONT, 30)
    if not first:
        d.text((MARGIN, MARGIN), f"{i + 1:02d} / {n:02d}", font=small, fill=sub, anchor="la")
        if not last:
            d.rectangle((MARGIN, MARGIN + 60, MARGIN + 90, MARGIN + 68), fill=look.accent)
    max_w = W - 2 * MARGIN
    if first:
        tf, tl, tlh = _fit(d, slide["title"], look.title, 118, max_w, 560)
        y = H - MARGIN - 70 - len(tl) * tlh - (60 if slide["body"] else 0)
        y = _text(d, (MARGIN, y), tl, tf, tlh, fg)
        if slide["body"]:
            bf, bl, blh = _fit(d, slide["body"], BODY_FONT, 40, max_w, 100, 1.3)
            _text(d, (MARGIN, y + 10), bl[:2], bf, blh, sub)
        _pill(d, (MARGIN, MARGIN), "Desliza  →", small, look.accent, look.on_accent)
    else:
        top = MARGIN + 150
        tf, tl, tlh = _fit(d, slide["title"], look.title, 96, max_w, 420)
        y = _text(d, (MARGIN, top), tl, tf, tlh, fg)
        if slide["body"]:
            bf, bl, blh = _fit(d, slide["body"], BODY_FONT, 46, max_w, H - y - MARGIN - 260, 1.35)
            y = _text(d, (MARGIN, y + 40), bl, bf, blh, sub)
        room = H - MARGIN - 90 - (y + 50)
        if not last and frame is not None and room > 220:
            # Un fotograma del reel abajo, con esquinas redondeadas: que se vea que eres tú.
            ph = _cover(frame, (max_w, room))
            mask = Image.new("L", ph.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, *ph.size), radius=28, fill=255)
            img.paste(ph, (MARGIN, y + 50), mask)
        if last and look.logo is not None:
            logo = Image.open(look.logo).convert("RGBA")
            logo.thumbnail((360, 200))
            img.paste(logo, (MARGIN, H - MARGIN - logo.height), logo)
        elif not last:
            d.text((W - MARGIN, H - MARGIN + 10), "→", font=_font(BODY_FONT, 56), fill=sub, anchor="rs")
    if look.handle:
        d.text((W - MARGIN, MARGIN + (6 if first else 0)), look.handle, font=small, fill=sub if not first else "#FFFFFF",
               anchor="ra")
    return img


def story(story_: dict, look: Look, frame: Image.Image | None) -> Image.Image:
    W, H = STORY
    if frame is not None:
        img = _cover(frame, STORY).filter(ImageFilter.GaussianBlur(2))
        img = _shade(img, top=0.0, strength=150)
    else:
        img = Image.new("RGB", STORY, INK)
    d = ImageDraw.Draw(img)
    max_w = W - 2 * MARGIN
    tf, tl, tlh = _fit(d, story_["text"], look.title, 100, max_w, 700)
    block = len(tl) * tlh
    y = (H - block) // 2
    if story_["sticker"]:
        sf = _font(BODY_FONT, 44)
        sw = d.textlength(story_["sticker"], font=sf) + 52
        _pill(d, ((W - sw) // 2, y - 140), story_["sticker"], sf, look.accent, look.on_accent)
    for ln in tl:
        d.text((W // 2, y), ln, font=tf, fill="#FFFFFF", anchor="ma")
        y += tlh
    if look.handle:
        d.text((W // 2, H - 260), look.handle, font=_font(BODY_FONT, 40), fill="#FFFFFF", anchor="ma")
    return img


def fallback(words: list[Word], hook: str, cta: str = "") -> dict:
    """Sin IA: el carrusel sale de las frases del vídeo."""
    from .rhythm import phrases

    rows = [p.text for p in phrases(words, set()) if len(p.text.split()) >= 4][:5]
    slides = [{"title": hook or (rows[0] if rows else "Mi nuevo reel"), "body": ""}]
    slides += [{"title": " ".join(r.split()[:6]).rstrip(",.;:") + "…", "body": r} for r in rows[:5]]
    slides.append({"title": cta or "¿Te ha servido?", "body": "Guárdalo y compártelo con quien lo necesite."})
    stories = [{"text": hook or "Nuevo reel", "sticker": "Nuevo reel"},
               {"text": rows[0] if rows else "Te cuento algo que no sabías", "sticker": "¿Te pasa?"},
               {"text": "Lo tienes entero en mi perfil", "sticker": "Míralo"}]
    return {"carousel": slides, "stories": stories, "reply": ""}


def render(data: dict, outdir: Path, b: brand_mod.Brand, frames: list[Path]) -> dict:
    """Dibuja todas las piezas y un zip con todo. Devuelve los nombres de archivo."""
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("*.png"):
        old.unlink()
    look = Look(b)
    imgs = [Image.open(f).convert("RGB") for f in frames if f.exists()]
    pick = lambda k: imgs[k % len(imgs)] if imgs else None  # noqa: E731
    names = {"carousel": [], "stories": []}
    slides = data.get("carousel", [])
    for i, s in enumerate(slides):
        name = f"carrusel-{i + 1:02d}.png"
        carousel_slide(i, len(slides), s, look, pick(i)).save(outdir / name, optimize=True)
        names["carousel"].append(name)
    for i, s in enumerate(data.get("stories", [])):
        name = f"historia-{i + 1}.png"
        story(s, look, pick(i + 1)).save(outdir / name, optimize=True)
        names["stories"].append(name)
    (outdir / "kit.json").write_text(json.dumps({**data, "files": names}, ensure_ascii=False, indent=1))
    with zipfile.ZipFile(outdir / "kit.zip", "w") as z:
        for n in names["carousel"] + names["stories"]:
            z.write(outdir / n, n)
    return names
