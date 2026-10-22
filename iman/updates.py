"""Actualizaciones de la app de escritorio.

Las versiones se publican como "releases" en un repositorio público de GitHub
(solo instaladores, sin código). Imán mira cuál es la última y, si es más nueva,
avisa en la app. Con un clic descarga el instalador de su sistema y lo abre:
en Windows se instala solo y vuelve a abrir Imán; en Mac se abre el DMG.

Las versiones publicadas después de que caduque la licencia no se ofrecen:
quien renueva sigue recibiendo mejoras, quien no, se queda con la suya.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from . import __version__, config, license

REPO = os.environ.get("IMAN_RELEASES_REPO", "XsiriusKalessy/iman-descargas")
CHECK_EVERY = 6 * 3600

_cache: dict = {"at": 0.0, "release": None}


def parse_version(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", (v or "").split("-")[0])
    return tuple(int(n) for n in nums[:3]) or (0,)


def asset_for(assets: list[dict], system: str | None = None, machine: str | None = None) -> dict | None:
    """El instalador que toca a este ordenador."""
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    names = {a.get("name", "").lower(): a for a in assets}
    if system == "Windows":
        wanted = [n for n in names if n.endswith(".exe") and "windows" in n]
    elif system == "Darwin":
        arch = "mac-arm64" if machine in ("arm64", "aarch64") else "mac-intel"
        wanted = [n for n in names if n.endswith(".dmg") and arch in n]
    else:
        wanted = []
    return names[wanted[0]] if wanted else None


def _fetch_latest() -> dict | None:
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "Iman"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except (OSError, ValueError):
        return None


def latest(force: bool = False) -> dict | None:
    if force or time.time() - _cache["at"] > CHECK_EVERY:
        rel = _fetch_latest()
        if rel is not None or force:
            _cache.update(at=time.time(), release=rel)
    return _cache["release"]


def check(cfg: dict | None = None, release: dict | None = None, current: str = __version__) -> dict:
    """Qué ve la app: si hay versión nueva, si la licencia la cubre y qué trae."""
    cfg = cfg if cfg is not None else config.load()
    rel = release if release is not None else latest()
    out = {"current": current, "available": False}
    if not rel:
        return out
    version = (rel.get("tag_name") or "").lstrip("v")
    asset = asset_for(rel.get("assets") or [])
    out.update(latest=version, notes=(rel.get("body") or "").strip()[:2000],
               published=rel.get("published_at") or "")
    if parse_version(version) <= parse_version(current) or not asset:
        return out
    st = license.status(cfg)
    expires = st.get("expires") or ""
    covered = not (st["licensed"] and expires and out["published"] and out["published"] > expires)
    out.update(available=True, covered=covered, size=asset.get("size", 0),
               url=asset.get("browser_download_url", ""), name=asset.get("name", ""))
    return out


_install: dict = {"state": "idle", "progress": 0.0, "message": ""}


def install_status() -> dict:
    return dict(_install)


def start_install(info: dict) -> None:
    if _install["state"] == "downloading":
        return
    _install.update(state="downloading", progress=0.0, message="")
    threading.Thread(target=_download_and_open, args=(info,), daemon=True).start()


def _download_and_open(info: dict) -> None:
    folder = config.HOME / "actualizaciones"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / Path(info["name"]).name
    try:
        req = urllib.request.Request(info["url"], headers={"User-Agent": "Iman"})
        with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or info.get("size") or 0)
            done = 0
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    _install["progress"] = done / total
    except OSError:
        _install.update(state="error", message="No se ha podido descargar. Revisa tu conexión y vuelve a probar.")
        return
    _install["progress"] = 1.0
    if sys.platform == "win32":
        # El instalador cierra Imán, se instala sin preguntar y lo vuelve a abrir.
        subprocess.Popen([str(dest), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"])
        _install.update(state="installing", message="Instalando… Imán se cerrará y volverá a abrirse solo.")
        threading.Timer(1.5, os._exit, args=(0,)).start()
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(dest)])
        _install.update(state="ready", message="Se ha abierto el instalador: arrastra Imán a Aplicaciones y "
                                                "elige «Reemplazar». Después vuelve a abrir Imán.")
    else:
        _install.update(state="ready", message=f"Descargado en {dest}")
