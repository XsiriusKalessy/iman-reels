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


FONT_EXT = (".ttf", ".otf")


def user_dir() -> Path:
    """Fuentes que ha subido el creador (Mi marca)."""
    from . import brand

    return brand.brand_dir() / "fuentes"


def family_name(path: Path) -> str:
    """El nombre completo con el que libass encuentra la fuente ("Poppins ExtraBold")."""
    names = TTFont(path, lazy=True)["name"]
    for nid in (4, 1):
        rec = names.getName(nid, 3, 1, 0x409) or names.getName(nid, 1, 0, 0) or names.getName(nid, 3, 1)
        if rec and str(rec).strip():
            return str(rec).strip()
    return path.stem


def user_fonts() -> dict[str, Path]:
    d = user_dir()
    if not d.exists():
        return {}
    out = {}
    for p in sorted(d.iterdir()):
        if p.suffix.lower() in FONT_EXT:
            try:
                out[family_name(p)] = p
            except Exception:  # noqa: BLE001 - una fuente rota no rompe el resto
                continue
    return out


def font_path(family: str) -> Path:
    if family in FILES:
        return FONTS_DIR / FILES[family]
    return user_fonts().get(family) or FONTS_DIR / FILES["Figtree ExtraBold"]


def fonts_dir() -> Path:
    """La carpeta de fuentes para libass: las incluidas y, si hay, las del creador juntas."""
    mine = user_fonts()
    if not mine:
        return FONTS_DIR
    dest = user_dir().parent / "fuentes-render"
    dest.mkdir(parents=True, exist_ok=True)
    import shutil

    for src in [*(FONTS_DIR / f for f in FILES.values()), *mine.values()]:
        dst = dest / src.name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copyfile(src, dst)
    keep = {f for f in FILES.values()} | {p.name for p in mine.values()}
    for old in dest.iterdir():
        if old.name not in keep:
            old.unlink(missing_ok=True)
    return dest


@lru_cache(maxsize=None)
def _metrics(family: str):
    f = TTFont(font_path(family), lazy=True)
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
