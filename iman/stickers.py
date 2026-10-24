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


def _frame(path: str) -> Image.Image | None:
    """La imagen de un archivo de apoyo: la foto tal cual o un fotograma del vídeo (al 30 %)."""
    p = Path(path)
    if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        try:
            return Image.open(p).convert("RGB")
        except OSError:
            return None
    import subprocess

    from .media import FFMPEG, probe

    out = HOME / "cache" / "stickers" / f"f-{hashlib.sha1(str(p).encode()).hexdigest()[:12]}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        t = probe(p).duration * 0.3
        subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(p), "-frames:v", "1", str(out)],
                       check=True, capture_output=True)
        return Image.open(out).convert("RGB")
    except Exception:  # noqa: BLE001 - si no se puede leer, no hay tarjeta
        return None


def _card(pic: Image.Image, width: int, label: str, tilt: float, top: bool = False) -> Image.Image:
    """Foto con marco blanco redondeado, sombra y, si hay, una etiqueta en píldora debajo (o encima)."""
    pic = pic.copy()
    pic.thumbnail((width, int(width * 1.5)), Image.LANCZOS)
    pad, frame = 30, 16
    w, h = pic.width + 2 * frame, pic.height + 2 * frame
    font = ImageFont.truetype(str(FONTS_DIR / FILES["Figtree ExtraBold"]), 38) if label else None
    lab_h = 80 if label else 0
    card = Image.new("RGBA", (w + 2 * pad, h + lab_h + 2 * pad), (0, 0, 0, 0))
    if top and label:
        pad_y = pad + lab_h
    else:
        pad_y = pad
    shadow = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad_y + 10, pad + w, pad_y + h + 10), 30, fill=(0, 0, 0, 120))
    card = Image.alpha_composite(card, shadow.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((pad, pad_y, pad + w, pad_y + h), 30, fill=(255, 255, 255, 255))
    mask = Image.new("L", pic.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pic.width, pic.height), 20, fill=255)
    card.paste(pic, (pad + frame, pad_y + frame), mask)
    if label:
        tw = font.getlength(label)
        x0 = pad + (w - tw) / 2 - 28
        y0 = pad_y - 36 if top else pad + h - 30
        d.rounded_rectangle((x0, y0, x0 + tw + 56, y0 + 66), 33, fill=(255, 85, 71, 255))
        d.text((x0 + 28 + tw / 2, y0 + 33), label, font=font, fill=(255, 255, 255, 255), anchor="mm")
    return card.rotate(tilt, resample=Image.BICUBIC, expand=True)


def captura(path: str, label: str = "", tilt: float = -3.0) -> Path | None:
    """Tarjeta con una captura o foto de apoyo y su etiqueta ("Mi web", "El resultado")."""
    label = label.strip()[:28]
    key = hashlib.sha1(f"cap|{path}|{label}|{tilt}".encode()).hexdigest()[:16]
    out = HOME / "cache" / "stickers" / f"{key}.png"
    if out.exists():
        return out
    pic = _frame(path)
    if pic is None:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    _card(pic, 720, label, tilt).save(out)
    return out


def collage(paths: list[str], labels: list[str]) -> Path | None:
    """Collage de 2 o 3 fotos de apoyo flotando inclinadas, cada una con su etiqueta."""
    pics = [(p, _frame(p)) for p in paths[:3]]
    pics = [(p, im) for p, im in pics if im is not None]
    if len(pics) < 2:
        return None
    key = hashlib.sha1(("col2|" + "|".join(paths) + "|".join(labels)).encode()).hexdigest()[:16]
    out = HOME / "cache" / "stickers" / f"{key}.png"
    if out.exists():
        return out
    canvas = Image.new("RGBA", (1040, 1000), (0, 0, 0, 0))
    spots = [(-6, 0, 0), (5, 470, 120), (-3, 160, 470)]
    for i, ((p, im), (tilt, x, y), lab) in enumerate(zip(pics, spots, labels + [""] * 3)):
        # La primera queda tapada por abajo: su etiqueta va encima.
        c = _card(im, 460, lab.strip()[:22], tilt, top=i == 0 and len(pics) == 3)
        canvas.alpha_composite(c, (min(x, canvas.width - c.width), min(y, canvas.height - c.height)))
    box = canvas.getbbox()
    out.parent.mkdir(parents=True, exist_ok=True)
    (canvas.crop(box) if box else canvas).save(out)
    return out
