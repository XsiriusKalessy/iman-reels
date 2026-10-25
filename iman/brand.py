"""Kit de marca: logo, colores, fuente y cierre que se aplican a todos los reels.

Se sube el logo y Imán saca de él los colores principales; el creador solo
confirma. Se guarda en ~/.iman/marca/ (brand.json + logo.png).
"""

from __future__ import annotations

import colorsys
import json
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from . import config, jsonfile
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
        with textfit.TTFont(probe, lazy=True) as f:
            if "cmap" not in f:
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
    description: str = ""  # el negocio en una frase: para que los textos de publicación vendan lo tuyo
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
    company: str = ""  # razón social (datos fijos de la empresa)
    # Frases de marca: [{"kind": "eslogan" | "promesa" | "cta" | "actitud" | "otra", "text": …, "where": …}].
    # La IA las usa en los textos y el eslogan sale en el cierre del reel.
    phrases: list[dict] = field(default_factory=list)
    # Tono de voz: cómo habla la marca (cercano, tú o usted, expresiones…) y textos reales suyos de ejemplo.
    voice: str = ""
    voice_examples: str = ""
    avoid: str = ""  # palabras y cosas que la marca no dice nunca
    no_emojis: bool = False  # la marca no usa emojis: ni en los textos ni en el vídeo

    def phrase(self, kind: str) -> str:
        return next((p.get("text", "") for p in self.phrases if p.get("kind") == kind and p.get("text")), "")

    def phrases_prompt(self) -> str:
        """Las frases de marca para la IA: cuál es cada una y dónde se usa."""
        rows = [f"- {p.get('kind', 'otra')}: «{p['text']}»" + (f" (se usa en: {p['where']})" if p.get("where") else "")
                for p in self.phrases if p.get("text")]
        return "FRASES DE MARCA (úsalas tal cual cuando encajen, sin forzarlas):\n" + "\n".join(rows) if rows else ""

    def voice_prompt(self) -> str:
        parts = []
        if self.voice.strip():
            parts.append(f"TONO DE VOZ DE LA MARCA: {self.voice.strip()}")
        if self.voice_examples.strip():
            parts.append("TEXTOS REALES DE LA MARCA (imita cómo suenan, no los copies):\n" + self.voice_examples.strip())
        if self.avoid.strip():
            parts.append(f"LA MARCA NO DICE NUNCA: {self.avoid.strip()}")
        if self.no_emojis:
            parts.append("SIN EMOJIS: la marca no usa emojis ni símbolos en ningún texto, ni en pantalla ni en las publicaciones.")
        return "\n\n".join(parts)

    def copy_prompt(self) -> str:
        """Todo lo que la IA necesita para escribir como la marca: tono de voz, ejemplos y frases."""
        return "\n\n".join(p for p in (self.voice_prompt(), self.phrases_prompt()) if p)

    @property
    def active(self) -> bool:
        return bool(self.primary or self.logo_path)

    @property
    def logo_path(self) -> Path | None:
        p = brand_dir() / "logo.png"
        return p if p.exists() else None


def brand_dir() -> Path:
    """La marca propia («marca») o, con un cliente activo (multi-cliente Pro), la de ese cliente."""
    from . import clientes

    cid = clientes.activo()
    return clientes.dir_for(cid) / "marca" if cid else config.HOME / "marca"


def load() -> Brand:
    f = brand_dir() / "brand.json"
    if not f.exists():
        return Brand()
    data = jsonfile.load(f)
    if not isinstance(data, dict):
        return Brand()
    return Brand(**clean(data))


def clean(data: dict) -> dict:
    """Solo los campos de la marca, con su tipo (un archivo editado a mano o importado no rompe Imán)."""
    out = {}
    for name, f in Brand.__dataclass_fields__.items():
        if name not in data:
            continue
        v, want = data[name], f.type
        if want in ("bool", bool):
            out[name] = bool(v)
        elif want in ("str", str):
            v = str(v if v is not None else "")
            if name in ("primary", "secondary") and v and not is_hex(v):
                continue
            if name == "font" and v and v not in FONTS and v != MINE:
                continue
            out[name] = v[:2000]
        elif name == "phrases":
            out[name] = clean_phrases(v if isinstance(v, list) else [])
        elif isinstance(v, list):
            out[name] = [str(x)[:300] for x in v][:20]
    return out


PHRASE_KINDS = {"eslogan": "Eslogan", "promesa": "Promesa", "cta": "Llamada a la acción", "actitud": "Actitud",
                "otra": "Otra"}


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u2190-\u21FF\u2300-\u23FF]")


def strip_emojis(text: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", _EMOJI.sub("", text)).strip()


def clean_phrases(raw) -> list[dict]:
    out = []
    for p in raw or []:
        text = " ".join(str(p.get("text", "")).split())[:160]
        if text:
            kind = p.get("kind") if p.get("kind") in PHRASE_KINDS else "otra"
            out.append({"kind": kind, "text": text, "where": " ".join(str(p.get("where", "")).split())[:200]})
    return out[:12]


def save(b: Brand) -> Brand:
    brand_dir().mkdir(parents=True, exist_ok=True)
    jsonfile.save(brand_dir() / "brand.json", asdict(b), indent=2)
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
