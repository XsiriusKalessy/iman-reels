"""Guía en PDF sacada del vídeo, para regalarla a cambio de un contacto (lead magnet).

«Escríbeme GUÍA y te la mando»: el reel atrae, la guía capta el contacto y lleva a pedir la propuesta. Se
dibuja con la marca del creador (colores, logo, eslogan) y fotogramas del propio vídeo, sin servicios de pago.
Sin IA, la guía sale de tus frases del vídeo.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from . import brand as brand_mod
from .kit import _clean, _cover, _fit, _font, _text, _wrap
from .models import Word
from .rhythm import phrases

PAGE = (1240, 1754)  # A4 a 150 ppp
MARGIN = 110
TITLE_FONT = "Playfair Display ExtraBold"
BODY_FONT = "Figtree SemiBold"
HEAD_FONT = "Figtree ExtraBold"


def fallback(words: list[Word], hook: str = "", cta: str = "") -> dict:
    """Sin IA: tus frases del vídeo, repartidas en apartados."""
    rows = [p.text.strip() for p in phrases(words, set()) if len(p.text.split()) >= 5]
    chunks = [rows[i:i + 3] for i in range(0, min(len(rows), 12), 3)] or [[" ".join(w.text for w in words)[:400]]]
    return {
        "title": hook or "Lo que tienes que saber",
        "subtitle": "La guía de mi último vídeo, para que la tengas a mano",
        "intro": "Te dejo por escrito lo más importante del vídeo, para que no se te olvide nada.",
        "sections": [{"heading": f"Parte {k}", "body": " ".join(c[:1]), "tips": c[1:]} for k, c in enumerate(chunks, 1)],
        "checklist": [], "faq": [], "cta": cta or "Escríbeme y te ayudo con lo que necesites.",
    }


def _colors(b) -> tuple[str, str]:
    primary = b.primary if brand_mod.is_hex(b.primary or "") else "#E63A2E"
    dark = b.secondary if brand_mod.is_hex(b.secondary or "") else "#141518"
    return primary, dark


class _Pages:
    """Va llenando páginas A4 y salta a la siguiente cuando no cabe."""

    def __init__(self, b, primary: str, dark: str):
        self.b, self.primary, self.dark = b, primary, dark
        self.pages: list[Image.Image] = []
        self.new()

    def new(self):
        self.img = Image.new("RGB", PAGE, "#FBFAF7")
        self.d = ImageDraw.Draw(self.img)
        self.pages.append(self.img)
        self.d.rectangle((0, 0, PAGE[0], 18), fill=self.primary)
        self.y = MARGIN
        self._footer()

    def _footer(self):
        f = _font(BODY_FONT, 22)
        name = _clean(self.b.name or "", BODY_FONT)
        self.d.text((MARGIN, PAGE[1] - 70), name, font=f, fill="#8A8A86")
        self.d.text((PAGE[0] - MARGIN, PAGE[1] - 70), str(len(self.pages)), font=f, fill="#8A8A86", anchor="ra")

    def room(self, h: int):
        if self.y + h > PAGE[1] - 130:
            self.new()

    def heading(self, text: str, size: int = 50):
        f = _font(HEAD_FONT, size)
        lines = _wrap(self.d, _clean(text, HEAD_FONT), f, PAGE[0] - 2 * MARGIN)
        self.room(len(lines) * int(size * 1.15) + 120)
        self.d.rectangle((MARGIN, self.y + 8, MARGIN + 60, self.y + 16), fill=self.primary)
        self.y = _text(self.d, (MARGIN, self.y + 34), lines, f, int(size * 1.15), self.dark) + 16

    def para(self, text: str, size: int = 30, indent: int = 0, color: str = "#2A2A28"):
        f = _font(BODY_FONT, size)
        lh = int(size * 1.45)
        for ln in _wrap(self.d, _clean(text, BODY_FONT), f, PAGE[0] - 2 * MARGIN - indent):
            self.room(lh)
            self.d.text((MARGIN + indent, self.y), ln, font=f, fill=color)
            self.y += lh
        self.y += 14

    def bullet(self, text: str, box: bool = False):
        size, lh = 30, int(30 * 1.45)
        self.room(lh)
        x, y = MARGIN, self.y + 8
        if box:
            self.d.rounded_rectangle((x, y, x + 30, y + 30), radius=6, outline=self.primary, width=4)
        else:
            self.d.ellipse((x + 8, y + 8, x + 22, y + 22), fill=self.primary)
        self.para(text, size, indent=52)
        self.y -= 6


def render(data: dict, out: Path, frames: list[Path], b=None) -> Path:
    b = b or brand_mod.load()
    primary, dark = _colors(b)
    # Portada: tu fotograma a sangre, velo oscuro y el título grande.
    cover = Image.new("RGB", PAGE, dark)
    if frames:
        with Image.open(frames[0]) as im:
            cover.paste(_cover(im.convert("RGB"), (PAGE[0], int(PAGE[1] * 0.62))), (0, 0))
        veil = Image.new("RGBA", PAGE, (0, 0, 0, 0))
        vd = ImageDraw.Draw(veil)
        top = int(PAGE[1] * 0.30)
        for k in range(PAGE[1] - top):
            vd.line((0, top + k, PAGE[0], top + k), fill=(0, 0, 0, min(235, int(235 * k / (PAGE[1] * 0.32)))))
        cover = Image.alpha_composite(cover.convert("RGBA"), veil).convert("RGB")
    d = ImageDraw.Draw(cover)
    d.rectangle((MARGIN, int(PAGE[1] * 0.60), MARGIN + 90, int(PAGE[1] * 0.60) + 10), fill=primary)
    f, lines, lh = _fit(d, _clean(data.get("title", ""), TITLE_FONT), TITLE_FONT, 104, PAGE[0] - 2 * MARGIN, 420)
    y = _text(d, (MARGIN, int(PAGE[1] * 0.60) + 50), lines, f, lh, "#FFFFFF")
    fs = _font(BODY_FONT, 36)
    _text(d, (MARGIN, y + 30), _wrap(d, _clean(data.get("subtitle", ""), BODY_FONT), fs, PAGE[0] - 2 * MARGIN), fs, 50,
          "#E8E6E0")
    logo = b.logo_path
    if logo:
        with Image.open(logo) as lg:
            lg = lg.convert("RGBA")
            lg.thumbnail((260, 140))
            cover.paste(lg, (MARGIN, PAGE[1] - 120 - lg.height), lg)
    elif b.name:
        d.text((MARGIN, PAGE[1] - 150), _clean(b.name, HEAD_FONT), font=_font(HEAD_FONT, 40), fill=primary)

    p = _Pages(b, primary, dark)
    if data.get("intro"):
        p.para(data["intro"], 34, color=dark)
        p.y += 20
    for k, sec in enumerate(data.get("sections") or []):
        p.heading(sec.get("heading", ""))
        if sec.get("body"):
            p.para(sec["body"])
        for tip in sec.get("tips") or []:
            p.bullet(tip)
        p.y += 26
        if k == 1 and len(frames) > 1:  # una foto del vídeo en mitad de la guía
            p.room(560)
            with Image.open(frames[1]) as im:
                p.img.paste(_cover(im.convert("RGB"), (PAGE[0] - 2 * MARGIN, 520)), (MARGIN, p.y))
            p.y += 560
    if data.get("checklist"):
        p.heading("Antes de decidirte")
        for item in data["checklist"]:
            p.bullet(item, box=True)
        p.y += 26
    if data.get("faq"):
        p.heading("Lo que más nos preguntan")
        for qa in data["faq"]:
            p.para(qa.get("q", ""), 32, color=dark)
            p.y -= 8
            p.para(qa.get("a", ""))
    # Cierre: la llamada a la acción en una caja con tu color y tu eslogan.
    p.room(420)
    box_top = p.y + 20
    f = _font(HEAD_FONT, 44)
    cta_lines = _wrap(p.d, _clean(data.get("cta", ""), HEAD_FONT), f, PAGE[0] - 2 * MARGIN - 80)
    contact = _clean(b.contact or "", BODY_FONT)
    slogan = _clean(b.phrase("eslogan"), BODY_FONT)
    h = len(cta_lines) * 56 + (70 if contact else 0) + (60 if slogan else 0) + 90
    p.d.rounded_rectangle((MARGIN, box_top, PAGE[0] - MARGIN, box_top + h), radius=28, fill=dark)
    y = _text(p.d, (MARGIN + 40, box_top + 45), cta_lines, f, 56, "#FFFFFF")
    if contact:
        p.d.text((MARGIN + 40, y + 16), contact, font=_font(HEAD_FONT, 36), fill=primary)
        y += 70
    if slogan:
        p.d.text((MARGIN + 40, y + 16), slogan, font=_font(TITLE_FONT, 32), fill="#E8E6E0")
    out.parent.mkdir(parents=True, exist_ok=True)
    cover.save(out, "PDF", resolution=150, save_all=True, append_images=p.pages)
    return out
