"""Kit de marca: logo, colores, fuente y cierre que se aplican a todos los reels.

Se sube el logo y Imán saca de él los colores principales; el creador solo
confirma. Se guarda en ~/.iman/marca/ (brand.json + logo.png).
"""

from __future__ import annotations

import colorsys
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from . import config
from .captions import STYLES, Style, rgb

FONTS = {  # nombre visible -> fuente incluida
    "Moderna": "Figtree ExtraBold",
    "Impacto": "Montserrat Black",
    "Condensada": "Anton",
    "Elegante": "Playfair Display ExtraBold",
    "Manuscrita": "Caveat",
    "Bebas": "Bebas Neue",
    "Hormozi": "Poppins ExtraBold",
    "Bloque": "Archivo Black",
    "Cómic": "Bangers",
}


MINE = "Mía"  # la fuente que ha subido el creador


def fonts() -> dict[str, str]:
    """Las fuentes que se pueden elegir: las incluidas y, si la hay, la del creador."""
    from . import textfit

    mine = textfit.user_fonts()
    return {**FONTS, **({MINE: next(iter(mine))} if mine else {})}


def font_family(key: str) -> str:
    return fonts().get(key or "", "")


def set_font(name: str, data: bytes) -> str:
    """Guarda la fuente del creador (sustituye a la anterior) y devuelve su nombre."""
    import tempfile

    from . import textfit

    ext = Path(name).suffix.lower()
    if ext not in textfit.FONT_EXT:
        raise ValueError("La fuente tiene que ser .ttf u .otf")
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / f"f{ext}"
        probe.write_bytes(data)
        family = textfit.family_name(probe)  # falla si no es una fuente de verdad
        if "cmap" not in textfit.TTFont(probe, lazy=True):
            raise ValueError("Esa fuente no tiene letras")
    d = textfit.user_dir()
    if d.exists():
        for old in d.iterdir():
            old.unlink(missing_ok=True)
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in family if c.isalnum() or c in " -_").strip() or "fuente"
    (d / f"{safe}{ext}").write_bytes(data)
    textfit._metrics.cache_clear()
    return family


def remove_font() -> None:
    from . import textfit

    d = textfit.user_dir()
    if d.exists():
        for old in d.iterdir():
            old.unlink(missing_ok=True)


@dataclass
class Brand:
    name: str = ""
    primary: str = ""  # '#RRGGBB'
    secondary: str = ""
    font: str = ""  # una clave de FONTS, o vacío para la del estilo
    handle: str = ""  # @usuario
    cta: str = ""  # texto del cierre, p. ej. "Reserva por WhatsApp"
    contact: str = ""  # web, teléfono…
    sector: str = ""  # pack por defecto: viajes, cursos, productos, empresas
    logo_corner: bool = True  # logo pequeño arriba a la derecha todo el reel
    end_card: bool = True  # cierre con logo y llamada a la acción
    palette: list[str] = field(default_factory=list)  # colores sacados del logo, para elegir

    @property
    def active(self) -> bool:
        return bool(self.primary or self.logo_path)

    @property
    def logo_path(self) -> Path | None:
        p = brand_dir() / "logo.png"
        return p if p.exists() else None


def brand_dir() -> Path:
    return config.HOME / "marca"


def load() -> Brand:
    f = brand_dir() / "brand.json"
    if not f.exists():
        return Brand()
    data = json.loads(f.read_text(encoding="utf-8"))
    return Brand(**{k: v for k, v in data.items() if k in Brand.__dataclass_fields__})


def save(b: Brand) -> Brand:
    brand_dir().mkdir(parents=True, exist_ok=True)
    (brand_dir() / "brand.json").write_text(json.dumps(asdict(b), ensure_ascii=False, indent=2), encoding="utf-8")
    return b


def set_logo(data: bytes) -> Brand:
    """Guarda el logo como PNG y propone los colores de la marca a partir de él."""
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.load()
    img = img.convert("RGBA")
    img.thumbnail((1200, 1200))
    brand_dir().mkdir(parents=True, exist_ok=True)
    img.save(brand_dir() / "logo.png")
    b = load()
    b.palette = palette(img)
    if b.palette and not b.primary:
        b.primary = b.palette[0]
        b.secondary = b.palette[1] if len(b.palette) > 1 else ""
    return save(b)


def logo_card() -> Path | None:
    """El logo sobre una tarjeta blanca redondeada, para el cierre.

    Así se lee aunque el logo sea del mismo color que el fondo de la marca.
    """
    src = brand_dir() / "logo.png"
    if not src.exists():
        return None
    dst = brand_dir() / "logo_card.png"
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst
    from PIL import Image, ImageDraw

    logo = Image.open(src).convert("RGBA")
    pad = max(logo.size) // 7
    w, h = logo.width + 2 * pad, logo.height + 2 * pad
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle([0, 0, w - 1, h - 1], radius=min(w, h) // 6, fill=(255, 255, 255, 255))
    card.alpha_composite(logo, (pad, pad))
    card.save(dst)
    return dst


def remove_logo() -> Brand:
    for name in ("logo.png", "logo_card.png"):
        if (p := brand_dir() / name).exists():
            p.unlink()
    b = load()
    b.palette = []
    return save(b)


def palette(img, n: int = 4) -> list[str]:
    """Colores con más presencia del logo, sin fondos blancos, negros ni transparentes."""
    small = img.convert("RGBA").resize((96, 96))
    counts: dict[tuple[int, int, int], int] = {}
    raw = small.tobytes()
    for r, g, b, a in zip(raw[0::4], raw[1::4], raw[2::4], raw[3::4]):
        if a < 128:
            continue
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if l > 0.93 or l < 0.07 or s < 0.12:
            continue  # blanco, negro o gris: casi siempre es fondo o texto
        key = (r // 24 * 24 + 12, g // 24 * 24 + 12, b // 24 * 24 + 12)
        counts[key] = counts.get(key, 0) + 1
    picked: list[tuple[int, int, int]] = []
    for c, _ in sorted(counts.items(), key=lambda kv: -kv[1]):
        # Que no se parezcan entre sí.
        if all(sum((x - y) ** 2 for x, y in zip(c, p)) > 70 ** 2 for p in picked):
            picked.append(c)
        if len(picked) == n:
            break
    return ["#%02X%02X%02X" % tuple(min(255, v) for v in c) for c in picked]


def is_hex(v: str) -> bool:
    h = v.lstrip("#")
    return v.startswith("#") and len(h) == 6 and all(c in "0123456789abcdefABCDEF" for c in h)


def ink_on(hex6: str) -> str:
    """Blanco o negro, lo que se lea mejor sobre ese color."""
    h = hex6.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#141518" if lum > 0.6 else "#FFFFFF"


def apply(style: Style, b: Brand) -> Style:
    """El estilo de subtítulos con los colores y la fuente de la marca."""
    if not b.active:
        return style
    changes = {}
    if b.primary:
        changes.update(accent=rgb(b.primary), title_box=rgb(b.primary), title_text=rgb(ink_on(b.primary)))
        if style.box:
            changes.update(box=rgb(b.primary), outline=rgb(b.primary), text=rgb(ink_on(b.primary)),
                           accent=rgb(b.secondary or ink_on(b.primary)))
    fam = font_family(b.font)
    if fam:
        changes.update(font=fam, title_font=fam)
    return replace(style, **changes)


def styled(key: str, b: Brand | None = None) -> Style:
    return apply(STYLES[key], b if b is not None else load())
