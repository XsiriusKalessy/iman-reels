"""Medir texto con las fuentes incluidas, para ajustar cajas y tamaños como lo dibuja libass."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont

FONTS_DIR = Path(__file__).parent / "assets" / "fonts"
FILES = {
    "Montserrat Black": "Montserrat-Black.ttf",
    "Anton": "Anton-Regular.ttf",
    "Playfair Display ExtraBold": "PlayfairDisplay-ExtraBold.ttf",
    "Caveat": "Caveat-Bold.ttf",
    "Figtree SemiBold": "Figtree-SemiBold.ttf",
    "Figtree ExtraBold": "Figtree-ExtraBold.ttf",
    "Bebas Neue": "BebasNeue-Regular.ttf",
    "Archivo Black": "ArchivoBlack-Regular.ttf",
    "Bangers": "Bangers-Regular.ttf",
    "Poppins ExtraBold": "Poppins-ExtraBold.ttf",
}


@lru_cache(maxsize=None)
def _metrics(family: str):
    f = TTFont(FONTS_DIR / FILES[family], lazy=True)
    os2 = f["OS/2"]
    # libass escala la fuente para que ascendente + descendente (Windows) midan `fs` píxeles.
    height = os2.usWinAscent + os2.usWinDescent
    return f.getBestCmap(), f["hmtx"].metrics, height


def width(text: str, family: str, size: float) -> float:
    cmap, hmtx, height = _metrics(family)
    units = 0
    for ch in text:
        glyph = cmap.get(ord(ch)) or cmap.get(ord("n"))
        units += hmtx.get(glyph, (height // 2, 0))[0]
    return units * size / height


def fit(text: str, family: str, size: float, max_width: float, min_size: float = 40) -> float:
    """El mayor tamaño (hasta `size`) con el que `text` cabe en una línea de `max_width`."""
    w = width(text, family, size)
    return size if w <= max_width else max(min_size, size * max_width / w)
