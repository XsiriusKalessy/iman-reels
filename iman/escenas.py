"""Reels sin salir tú: tu voz sobre imágenes que cuentan lo que dices, una escena cada ~3 s.

Cada escena lleva una imagen, sacada por este orden:
1. tus fotos (las que subes como «apoyo»), en orden;
2. fotos de Pexels con tu propia clave gratuita (licencia que permite uso comercial);
3. ilustraciones generadas con TU clave de OpenAI, solo si lo eliges (lo paga tu cuenta, no Imán);
4. si no hay nada de eso, una lámina de diseño con tu marca y la idea de la escena en grande.
Cada imagen se mueve en 2.5D (iman/paralaje.py) para que nada esté quieto, y luego el reel se monta como uno de
«solo mi voz»: subtítulos, gancho, música, sonidos y efectos de Imán. Nada de avatares ni de voces clonadas.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import random
import urllib.parse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import brand as brand_mod
from . import config
from .models import Word

log = logging.getLogger(__name__)
W, H = 1080, 1920
SOURCES = ("auto", "fotos", "pexels", "openai", "laminas")
STOP = set("""a al algo algunas algunos ante antes como con contra cual cuando de del desde donde dos el ella ellas
ellos en entre era eres es esa ese eso esta este esto estos fue ha hay la las le les lo los mas me mi mis mucho muy
nada ni no nos o os para pero poco por porque que quien se ser si sin sobre su sus tambien te tengo tiene todo
tu tus un una uno unos y ya yo vale bueno pues entonces eh em""".split())


def scenes(words: list[Word], cuts: list[float]) -> list[dict]:
    """Las escenas del reel (una por plano): desde, hasta y lo que se dice en ella."""
    total = words[-1].end if words else 0.0
    bounds = [0.0, *[c for c in cuts if 0 < c < total], max(total, 0.1)]
    out = []
    for a, b in zip(bounds, bounds[1:]):
        text = " ".join(w.text for w in words if a - 0.05 <= w.start < b)
        out.append({"from": round(a, 3), "to": round(b, 3), "text": text.strip()})
    return out


def keywords(text: str, n: int = 3) -> str:
    """Sin IA: las palabras con más contenido de la escena (las más largas que no son de relleno)."""
    from .models import normalize

    ws = [w.strip(".,;:!?¡¿«»\"'()") for w in text.split()]
    ws = [w for w in ws if len(w) > 3 and normalize(w) not in STOP]
    ranked = sorted(dict.fromkeys(ws), key=lambda w: -len(w))[:n]
    return " ".join(w for w in ws if w in ranked)[:60]


SCENES_SCHEMA = {
    "type": "object",
    "properties": {"scenes": {"type": "array", "items": {"type": "object", "properties": {
        "search": {"type": "string", "description": "2-4 palabras en inglés para buscar una foto de stock"},
        "prompt": {"type": "string", "description": "Descripción en inglés de una ilustración vertical para la escena"},
        "title": {"type": "string", "description": "La idea de la escena en 2-5 palabras, en el idioma del vídeo"},
    }, "required": ["search", "prompt", "title"], "additionalProperties": False}}},
    "required": ["scenes"],
    "additionalProperties": False,
}
SCENES_SYSTEM = """Eres director de arte de reels sin persona en cámara: la voz del creador va sobre imágenes.
Para cada escena (lo que se dice en ese trozo) propones UNA imagen que la cuente de forma visual y concreta:
"search" para buscarla en un banco de fotos (inglés, 2-4 palabras, cosas que se puedan fotografiar),
"prompt" para ilustrarla (inglés, una frase: sujeto, acción, ambiente, luz; estilo coherente en todo el reel,
vertical 9:16, sin texto ni logotipos ni personas famosas ni marcas) y "title", la idea en 2-5 palabras.
Devuelve exactamente una entrada por escena, en el mismo orden."""


def _short(text: str, n: int = 5) -> str:
    """Sin IA, el título de la lámina es el principio de lo que dices (se lee como una frase, no como etiquetas)."""
    ws = text.split()
    return (" ".join(ws[:n]).rstrip(",.;:") + ("…" if len(ws) > n else "")) or "…"


def plan(scn: list[dict], aicfg=None) -> list[dict]:
    """Qué imagen va en cada escena (con IA si la hay; si no, palabras clave)."""
    out = [{"search": keywords(s["text"]) or "abstract light", "prompt": s["text"][:200],
            "title": _short(s["text"])} for s in scn]
    if aicfg is not None and getattr(aicfg, "enabled", False) and scn:
        from . import ai

        try:
            user = "\n".join(f"Escena {i + 1}: {s['text']}" for i, s in enumerate(scn))
            data = ai._ask_json(aicfg, SCENES_SYSTEM, user, SCENES_SCHEMA)
            for i, d in enumerate((data.get("scenes") or [])[:len(out)]):
                for k in ("search", "prompt", "title"):
                    if str(d.get(k, "")).strip():
                        out[i][k] = str(d[k]).strip()[:300]
        except Exception as e:  # noqa: BLE001 - sin IA, palabras clave
            log.warning("No se pudieron planificar las escenas con IA: %s", e)
    return out


def pexels_photo(query: str, key: str, pick: int = 0) -> Path | None:
    """Una foto vertical de Pexels para `query` (en caché)."""
    from . import pexels

    query = " ".join(query.split())[:60].lower()
    if not query or not key:
        return None
    out = config.HOME / "cache" / "pexels-fotos" / f"{hashlib.sha1(f'{query}{pick}'.encode()).hexdigest()[:16]}.jpg"
    if out.exists():
        return out
    q = urllib.parse.urlencode({"query": query, "orientation": "portrait", "per_page": 6})
    data = json.loads(pexels._get(f"https://api.pexels.com/v1/search?{q}", key))
    photos = data.get("photos") or []
    if not photos:
        return None
    src = photos[pick % len(photos)].get("src") or {}
    link = src.get("portrait") or src.get("large2x") or src.get("large")
    if not link:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(pexels._get(link, key, timeout=60))
    tmp.replace(out)
    return out


def openai_image(prompt: str, key: str, dst: Path) -> Path:
    """Ilustración con la clave de OpenAI del creador (lo cobra su cuenta de OpenAI)."""
    from openai import OpenAI

    r = OpenAI(api_key=key).images.generate(model="gpt-image-1", prompt=prompt[:900], size="1024x1536", n=1)
    dst.write_bytes(base64.b64decode(r.data[0].b64_json))
    return dst


def lamina(title: str, kit, dst: Path, k: int = 0) -> Path:
    """Lámina de diseño con la idea de la escena en grande, con los colores de la marca (sin IA ni internet)."""
    from .kit import _fit  # noqa: PLC2701 - mismas letras que el carrusel

    accent = kit.primary if kit is not None and brand_mod.is_hex(kit.primary or "") else "#FF5547"
    second = kit.secondary if kit is not None and brand_mod.is_hex(kit.secondary or "") else "#5B80FF"
    rnd = random.Random(f"{title}{k}")
    img = Image.new("RGB", (W, H), "#111215")
    glow = Image.new("RGB", (W, H), "#111215")
    d = ImageDraw.Draw(glow)
    for color in (accent, second, accent):  # manchas de luz con los colores de la marca
        x, y, r = rnd.randint(0, W), rnd.randint(0, H), rnd.randint(380, 720)
        d.ellipse((x - r, y - r, x + r, y + r), fill=color)
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(220)), 0.55)
    d = ImageDraw.Draw(img)
    family = brand_mod.font_family(kit.font) if kit is not None and getattr(kit, "font", "") else ""
    family = family or "Bricolage Grotesque ExtraBold"
    try:
        font, lines, lh = _fit(d, title.upper(), family, 150, W - 200, 900)
    except Exception:  # noqa: BLE001 - letra que no está: la de serie
        font, lines, lh = _fit(d, title.upper(), "Figtree ExtraBold", 150, W - 200, 900)
    y = (H - len(lines) * lh) // 2 - 120
    for ln in lines:
        d.text((W // 2, y), ln, font=font, fill="#FFFFFF", anchor="ma")
        y += lh
    d.rectangle((W // 2 - 70, y + 30, W // 2 + 70, y + 42), fill=accent)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, quality=92)
    return dst


def images(words: list[Word], cuts: list[float], workdir: Path, cfg: dict, kit=None, fotos: list[Path] | None = None,
           source: str = "auto", aicfg=None, progress=lambda msg, pct: None) -> list[Path]:
    """Una imagen por escena, por el orden de preferencia de arriba. Devuelve las rutas en orden."""
    scn = scenes(words, cuts)
    ideas = plan(scn, aicfg)
    fotos = [p for p in fotos or [] if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    out_dir = workdir / "escenas"
    out_dir.mkdir(parents=True, exist_ok=True)
    key_pexels, key_openai = cfg.get("pexels_key") or "", cfg.get("openai_key") or ""
    result: list[Path] = []
    used: dict[str, int] = {}
    for i, idea in enumerate(ideas):
        progress(f"Preparando la imagen {i + 1} de {len(ideas)}", i / max(1, len(ideas)))
        got = None
        if source in ("auto", "fotos") and i < len(fotos):
            got = fotos[i]
        if got is None and source == "openai" and key_openai:
            try:
                dst = out_dir / f"ia-{i + 1:02d}-{hashlib.sha1(idea['prompt'].encode()).hexdigest()[:8]}.png"
                got = dst if dst.exists() else openai_image(idea["prompt"], key_openai, dst)
            except Exception as e:  # noqa: BLE001
                log.warning("Falla la ilustración %d: %s", i + 1, e)
        if got is None and source in ("auto", "pexels", "openai") and key_pexels:
            try:
                n = used.get(idea["search"], 0)
                used[idea["search"]] = n + 1
                got = pexels_photo(idea["search"], key_pexels, n)
            except Exception as e:  # noqa: BLE001
                log.warning("Falla Pexels en la escena %d: %s", i + 1, e)
        if got is None and fotos and source == "fotos":  # «solo mis fotos»: se repiten en orden
            got = fotos[i % len(fotos)]
        if got is None:
            got = lamina(idea["title"], kit, out_dir / f"lamina-{i + 1:02d}.jpg", i)
        result.append(got)
    return result


def clips(words: list[Word], cuts: list[float], workdir: Path, cfg: dict, kit=None, fotos=None, source="auto",
          aicfg=None, progress=lambda msg, pct: None) -> list[Path]:
    """Las imágenes de las escenas, ya en movimiento 2.5D, listas para el lienzo de «solo mi voz»."""
    from . import paralaje

    imgs = images(words, cuts, workdir, cfg, kit, fotos, source, aicfg, progress)
    scn = scenes(words, cuts)
    out = []
    for img, s in zip(imgs, scn):
        try:
            out.append(paralaje.cached(img, max(1.0, s["to"] - s["from"] + 0.2)))
        except Exception as e:  # noqa: BLE001 - sin movimiento, la foto quieta (el lienzo le da un barrido)
            log.warning("Sin 2.5D para %s: %s", img, e)
            out.append(img)
    return out
