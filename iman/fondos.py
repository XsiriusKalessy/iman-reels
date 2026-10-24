"""Fondos de marca para cuando la persona va recortada: oscuros, con la luz y el color de la marca.

Un color liso detrás de la persona queda plano y se come los subtítulos del mismo color; estos fondos
llevan una base oscura, el color de la marca como luz (brillo, degradado, bokeh o el logo en trama),
viñeta y un poco de grano para que no parezcan de plástico.
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1080, 1920
VARIANTS = {  # clave -> nombre visible
    "color": "Brillo de mi marca",
    "marca_degradado": "Degradado de mi marca",
    "marca_bokeh": "Luces de mi marca",
    "marca_logo": "Trama con mi logo",
}


def _rgb(hex_: str) -> np.ndarray:
    h = (hex_ or "#FF5547").lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float)


def _dark_base(secondary: str) -> np.ndarray:
    """La base: el secundario de la marca si es oscuro; si no, casi negro."""
    s = _rgb(secondary) if secondary else None
    if s is not None and (0.2126 * s[0] + 0.7152 * s[1] + 0.0722 * s[2]) < 60:
        return s
    return np.array([14, 15, 18], float)


def _radial(cx: float, cy: float, rx: float, ry: float) -> np.ndarray:
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2)
    return np.clip(1 - d, 0, 1) ** 2


def _finish(img: np.ndarray, seed: int) -> Image.Image:
    # Viñeta y grano: el fondo se aleja y no se ve plano.
    vig = 1 - 0.45 * (1 - _radial(W / 2, H * 0.45, W * 1.05, H * 0.75)) ** 1.5
    img = img * vig[..., None]
    rng = np.random.default_rng(seed)
    img = img + rng.normal(0, 3.2, (H, W, 1))
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def render(variant: str, primary: str, secondary: str, dst: Path, logo: Path | None = None) -> Path:
    p, base = _rgb(primary), _dark_base(secondary)
    img = np.broadcast_to(base, (H, W, 3)).astype(np.float32).copy()
    seed = int(hashlib.sha1(f"{variant}{primary}".encode()).hexdigest()[:6], 16)
    if variant == "marca_degradado":
        t = np.linspace(0, 1, H, dtype=np.float32)[:, None, None] ** 1.4
        deep = p * 0.7
        img = img * (1 - t) + deep * t
        sweep = _radial(W * 0.9, H * 0.15, W * 0.9, H * 0.35)[..., None]
        img = img + (p * 0.35) * sweep
    elif variant == "marca_bokeh":
        img = img + p * 0.25 * _radial(W / 2, H * 0.4, W * 1.1, H * 0.6)[..., None]
        layer = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(layer)
        rng = random.Random(seed)
        for _ in range(26):
            r = rng.uniform(40, 150)
            x, y = rng.uniform(-50, W + 50), rng.uniform(0, H * 0.85)
            k = rng.uniform(0.25, 0.7)
            tint = p * k + 255 * (1 - k) * 0.35
            f = rng.uniform(0.35, 0.8)
            d.ellipse((x - r, y - r, x + r, y + r), fill=tuple(int(c * f) for c in tint))
        bokeh = np.asarray(layer.filter(ImageFilter.GaussianBlur(14)), np.float32)
        img = img + bokeh * 0.75
    else:
        # Brillo detrás de la cabeza, como una luz de estudio con el color de la marca.
        img = img + p * 0.85 * _radial(W / 2, H * 0.36, W * 0.95, H * 0.42)[..., None]
        img = img + p * 0.18 * _radial(W / 2, H * 1.0, W * 1.2, H * 0.35)[..., None]
        if variant == "marca_logo" and logo is not None and logo.exists():
            mark = Image.open(logo).convert("RGBA")
            mark.thumbnail((170, 170))
            alpha = np.asarray(mark, np.float32)[..., 3] / 255 * 0.16
            tile = Image.new("L", (W * 2, H * 2), 0)
            a = Image.fromarray((alpha * 255).astype(np.uint8))
            for row, y in enumerate(range(0, H * 2, 260)):
                for x in range(-260 if row % 2 else 0, W * 2, 300):
                    tile.paste(a, (x, y), a)
            tile = tile.rotate(-14, resample=Image.BICUBIC).crop((W // 2, H // 2, W // 2 + W, H // 2 + H))
            m = np.asarray(tile, np.float32)[..., None] / 255
            img = img * (1 - m) + (p * 0.6 + 100) * m
    out = _finish(img, seed)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, quality=92)
    return dst
