"""Planos de apoyo de Pexels: insertos de 1-2 s que complementan lo que cuentas (tú sigues en el círculo).

Con la clave gratuita de Pexels de cada persona (https://www.pexels.com/api/). La licencia de Pexels permite
el uso comercial sin atribución; la API pide enseñar que los vídeos vienen de Pexels, y la app lo dice.
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

from . import config

API = "https://api.pexels.com/videos/search"


def _get(url: str, key: str, timeout: float = 15) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "Iman/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - solo la API y los vídeos de Pexels
        return r.read()


def best_file(video: dict) -> dict | None:
    """El archivo mp4 que mejor encaja en un reel: vertical si lo hay y cerca de 1080 de ancho."""
    files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("link")]
    if not files:
        return None

    def score(f):
        w, h = f.get("width") or 0, f.get("height") or 0
        portrait = h > w
        return (portrait, -abs(min(w, h) - 1080))

    return max(files, key=score)


def search(query: str, key: str) -> str | None:
    """Enlace del mejor vídeo para `query` (en inglés funciona mejor), o None."""
    q = urllib.parse.urlencode({"query": query, "orientation": "portrait", "per_page": 8, "size": "medium"})
    data = json.loads(_get(f"{API}?{q}", key))
    for v in data.get("videos", []):
        if (v.get("duration") or 0) < 2:
            continue
        f = best_file(v)
        if f:
            return f["link"]
    return None


def clip(query: str, key: str) -> Path | None:
    """El vídeo descargado (en caché: la misma búsqueda no se vuelve a bajar)."""
    query = " ".join(query.split())[:60].lower()
    if not query or not key:
        return None
    out = config.HOME / "cache" / "pexels" / f"{hashlib.sha1(query.encode()).hexdigest()[:16]}.mp4"
    if out.exists():
        return out
    link = search(query, key)
    if not link:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(_get(link, key, timeout=60))
    tmp.replace(out)
    return out
