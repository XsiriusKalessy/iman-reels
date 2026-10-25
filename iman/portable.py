"""Llevarte Imán a otro ordenador: tus ajustes, Mi marca (con el logo) y lo que Imán recuerda de ti.

El archivo es un .zip con extensión .iman. Las claves de IA y la licencia solo
van dentro si la persona lo pide, porque quien tenga el archivo podría usarlas.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import asdict

from . import brand, config, license

# Lo que siempre viaja. Las claves y la licencia, solo si se pide.
PREFS = ("provider", "claude_model", "openai_model", "transcriber", "whisper_model", "language", "memory")
SECRETS = ("anthropic_key", "openai_key", "pexels_key")
BRAND_FILES = ("brand.json", "logo.png")
MAX_SIZE = 20 * 1024 * 1024


class ImportError_(ValueError):
    pass


def export(with_secrets: bool = False) -> bytes:
    cfg = config.load()
    data = {k: cfg[k] for k in PREFS}
    if with_secrets:
        data.update({k: cfg[k] for k in SECRETS})
        data["license_key"] = cfg.get("license_key") or ""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("ajustes.json", json.dumps({"version": 1, "ajustes": data}, ensure_ascii=False, indent=2))
        for name in BRAND_FILES:
            f = brand.brand_dir() / name
            if f.exists():
                z.write(f, f"marca/{name}")
    return buf.getvalue()


def import_(raw: bytes) -> dict:
    """Carga un archivo exportado. Devuelve qué se ha traído, para enseñarlo."""
    if len(raw) > MAX_SIZE:
        raise ImportError_("El archivo es demasiado grande para ser unos ajustes de Imán")
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        payload = json.loads(z.read("ajustes.json"))
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise ImportError_("Este archivo no son unos ajustes de Imán") from e
    data = payload.get("ajustes") or {}
    updates = {k: data[k] for k in PREFS + SECRETS if k in data and data[k] not in (None, "")}
    config.save(updates)
    got = {"ajustes": True, "marca": False, "logo": False, "claves": any(k in updates for k in SECRETS), "licencia": False}

    names = set(z.namelist())
    if "marca/brand.json" in names:
        info = json.loads(z.read("marca/brand.json"))
        # Se suma a tu marca: lo que trae el archivo manda, y lo que no trae (tu fuente, tu logo…) se queda.
        mine = asdict(brand.load())
        info = {**mine, **{k: v for k, v in info.items() if v not in ("", None, []) and k in mine}}
        brand.save(brand.Brand(**info))
        got["marca"] = True
    if "marca/logo.png" in names:
        brand.set_logo(z.read("marca/logo.png"))  # vuelve a pasar por Pillow: solo entra una imagen de verdad
        if got["marca"]:  # set_logo propone colores; nos quedamos con los que ya tenías
            brand.save(brand.Brand(**{k: v for k, v in info.items() if k in brand.Brand.__dataclass_fields__}))
        got["logo"] = True

    key = (data.get("license_key") or "").strip()
    if key and not config.load().get("license_valid"):
        try:
            config.save(license.activate(key))
            got["licencia"] = True
        except license.LicenseError:
            pass
    return got
