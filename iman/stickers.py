"""Pegatinas de objetos: el dibujo de lo que nombras (🔌 adaptador, 🧦 calcetines…) en una tarjeta.

Los dibujos son los emojis de Noto Color Emoji (licencia OFL), que viajan con la app. Así no
hace falta internet ni bancos de imágenes, y siempre se ven igual en Windows y en Mac.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import HOME
from .textfit import FILES, FONTS_DIR

EMOJI_FONT = Path(__file__).parent / "assets" / "emoji" / "NotoColorEmoji.ttf"
EMOJI_SIZE = 109  # el único tamaño que trae la fuente (mapa de bits); luego se escala
CARD = 300  # lado de la tarjeta a 1080 de ancho


def _emoji(char: str) -> Image.Image | None:
    font = ImageFont.truetype(str(EMOJI_FONT), EMOJI_SIZE)
    im = Image.new("RGBA", (EMOJI_SIZE * 2, EMOJI_SIZE * 2), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((EMOJI_SIZE // 2, EMOJI_SIZE // 2), char, font=font, embedded_color=True)
    box = im.getbbox()
    return im.crop(box) if box else None


def render(char: str, label: str = "", tilt: float = -5.0, scale: float = 1.0) -> Path | None:
    """PNG con la pegatina (o None si ese emoji no existe). Se guarda en caché por contenido."""
    char, label = char.strip()[:8], label.strip()[:24]
    key = hashlib.sha1(f"{char}|{label}|{tilt}|{scale}".encode()).hexdigest()[:16]
    out = HOME / "cache" / "stickers" / f"{key}.png"
    if out.exists():
        return out
    pic = _emoji(char)
    if pic is None:
        return None
    s = lambda v: int(v * scale)  # noqa: E731
    side = s(CARD)
    font = ImageFont.truetype(str(FONTS_DIR / FILES["Figtree ExtraBold"]), s(40)) if label else None
    text_h = s(58) if label else 0
    w, h = side, side + text_h
    pad = s(40)  # margen para la sombra y el giro
    card = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad + s(10), pad + w, pad + h + s(10)), s(46), fill=(0, 0, 0, 110))
    card = Image.alpha_composite(card, shadow.filter(ImageFilter.GaussianBlur(s(14))))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((pad, pad, pad + w, pad + h), s(46), fill=(255, 255, 255, 255))
    icon = s(190)
    pic = pic.resize((icon, int(icon * pic.height / pic.width)), Image.LANCZOS)
    card.alpha_composite(pic, (pad + (w - pic.width) // 2, pad + (side - pic.height) // 2 + (s(8) if label else 0)))
    if label:
        while font.getlength(label) > w - s(36) and font.size > s(22):
            font = ImageFont.truetype(str(FONTS_DIR / FILES["Figtree ExtraBold"]), font.size - 2)
        d.text((pad + w / 2, pad + side + text_h / 2 - s(14)), label, font=font, fill=(20, 21, 24, 255), anchor="mm")
    card = card.rotate(tilt, resample=Image.BICUBIC, expand=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    card.save(out)
    return out
