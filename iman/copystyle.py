"""Copiar el estilo de un reel: subes un reel que te gusta y Imán saca su letra, colores y ritmo.

Se guardan como estilos tuyos ("mio-…") junto a los de serie y se eligen igual que ellos.
Solo se toma el estilo (tipo de letra, colores, cuántas palabras, posición, ritmo); nunca el contenido.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

from . import brand, config, media
from .captions import STYLES, Style, rgb

POSITIONS = {"arriba": 520, "centro": 1000, "abajo": 1340}
SIZES = {"pequeño": 0.8, "mediano": 1.0, "grande": 1.2}


def store() -> Path:
    return config.HOME / "estilos.json"


def custom() -> dict[str, dict]:
    f = store()
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def register() -> None:
    """Carga los estilos guardados en la lista de estilos disponibles."""
    for k in [k for k in STYLES if k.startswith("mio-")]:
        del STYLES[k]
    for key, data in custom().items():
        try:
            STYLES[key] = Style(**data["style"])
        except TypeError:
            continue


def _hex(v: str, default: str) -> str:
    return v.upper() if brand.is_hex(v or "") else default


def frames(src: Path, n: int = 6) -> list[bytes]:
    """Fotogramas repartidos por el vídeo (o la imagen tal cual), en JPEG pequeños."""
    if src.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "f.jpg"
            subprocess.run([media.FFMPEG, "-y", "-v", "error", "-i", str(src), "-vf", "scale=540:-2", str(out)],
                           check=True)
            return [out.read_bytes()]
    dur = media.probe(src).duration
    shots = []
    with tempfile.TemporaryDirectory() as d:
        for k in range(n):
            t = dur * (k + 0.5) / n
            out = Path(d) / f"f{k}.jpg"
            subprocess.run([media.FFMPEG, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
                            "-vf", "scale=540:-2", "-q:v", "4", str(out)], check=True)
            if out.exists():
                shots.append(out.read_bytes())
    return shots


def cut_rate(src: Path) -> float:
    """Cortes de plano por segundo: dice si el reel es rápido o pausado."""
    if src.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        return 0.0
    res = subprocess.run([media.FFMPEG, "-v", "info", "-i", str(src), "-vf", "select='gt(scene,0.3)',showinfo",
                          "-an", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    cuts = len(re.findall(r"pts_time:", res.stderr))
    dur = media.probe(src).duration or 1
    return cuts / dur


def rhythm_for(rate: float) -> str:
    return "rapido" if rate >= 0.45 else ("dinamico" if rate >= 0.2 else "natural")


def build(a: dict) -> Style:
    """De lo que ha visto la IA a un estilo de subtítulos de Imán."""
    n = max(1, min(7, int(a.get("words_per_line") or 3)))
    font = brand.FONTS.get(a.get("font"), "Figtree ExtraBold")
    if a.get("box"):
        base = STYLES["caja"]
    elif n == 1:
        base = STYLES["palabra"]
    elif n >= 5:
        base = STYLES["karaoke"]
    else:
        base = STYLES["impacto"] if a.get("uppercase") else STYLES["editorial"]
    size = round(base.size * SIZES.get(a.get("size"), 1.0))
    text = _hex(a.get("text_color"), "#FFFFFF")
    box = _hex(a.get("box_color"), "#141518") if a.get("box") else ""
    outline = (box or "#000000") if a.get("outline") or box else "#000000"
    return replace(
        base, font=font, title_font=font, size=size, uppercase=bool(a.get("uppercase")),
        text=rgb(text), accent=rgb(_hex(a.get("highlight_color"), text)), outline=rgb(outline),
        outline_w=base.outline_w if (a.get("outline") or box) else 0, shadow=base.shadow if a.get("outline") else 0,
        max_words=n, max_chars=max(8, n * 7), y=POSITIONS.get(a.get("position"), base.y), pop=bool(a.get("pop")),
        box=rgb(box) if box else "",
    )


def save(name: str, analysis: dict, rhythm: str) -> dict:
    data = custom()
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().translate(str.maketrans("áéíóúñü", "aeiounu"))).strip("-")[:24]
    key = f"mio-{slug or len(data) + 1}"
    style = replace(build(analysis), key=key, label=name.strip()[:30] or "Mi estilo")
    data[key] = {"style": asdict(style), "rhythm": rhythm, "notes": str(analysis.get("notes", ""))[:200],
                 "analysis": analysis}
    store().parent.mkdir(parents=True, exist_ok=True)
    store().write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    register()
    return {"key": key, **data[key]}


def remove(key: str) -> None:
    data = custom()
    if data.pop(key, None) is not None:
        store().write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    register()
