"""Licencias con Lemon Squeezy.

Lemon Squeezy cobra, emite la clave de licencia y gestiona el IVA europeo
(actúa como "merchant of record"). Su API de licencias es pública: no hace
falta ninguna clave secreta en la app.

Sin licencia, Imán permite FREE_REELS reels de prueba con marca de agua.
"""

from __future__ import annotations

import json
import os
import platform
import time
import urllib.parse
import urllib.request

API = "https://api.lemonsqueezy.com/v1/licenses"
# Id del producto en Lemon Squeezy; evita que valga una clave de otra tienda.
PRODUCT_ID = os.environ.get("IMAN_LEMON_PRODUCT_ID", "")
FREE_REELS = 3
REVALIDATE_EVERY = 24 * 3600
OFFLINE_GRACE = 14 * 24 * 3600


class LicenseError(Exception):
    pass


def _post(action: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(f"{API}/{action}", data=data, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:  # la API responde 4xx con un JSON que explica el error
        try:
            return json.loads(e.read())
        except Exception:
            raise LicenseError(f"El servidor de licencias respondió {e.code}") from e
    except OSError as e:
        raise LicenseError("No hay conexión con el servidor de licencias") from e


def _check_product(meta: dict) -> None:
    if PRODUCT_ID and str(meta.get("product_id")) != PRODUCT_ID:
        raise LicenseError("Esta clave no es de Imán")


def activate(key: str) -> dict:
    """Activa la clave en este ordenador. Devuelve los datos a guardar en la configuración."""
    res = _post("activate", {"license_key": key.strip(), "instance_name": platform.node() or "Imán"})
    if not res.get("activated"):
        raise LicenseError(res.get("error") or "No se ha podido activar la licencia")
    _check_product(res.get("meta") or {})
    lk = res.get("license_key") or {}
    return {
        "license_key": key.strip(),
        "license_instance": (res.get("instance") or {}).get("id", ""),
        "license_expires": lk.get("expires_at") or "",
        "license_checked": time.time(),
        "license_valid": True,
    }


def deactivate(cfg: dict) -> None:
    if cfg.get("license_key") and cfg.get("license_instance"):
        try:
            _post("deactivate", {"license_key": cfg["license_key"], "instance_id": cfg["license_instance"]})
        except LicenseError:
            pass


def validate(cfg: dict) -> dict:
    """Comprueba la licencia como mucho una vez al día; sin conexión, aguanta 14 días."""
    if not cfg.get("license_key"):
        return {"license_valid": False}
    if time.time() - float(cfg.get("license_checked") or 0) < REVALIDATE_EVERY:
        return {}
    try:
        res = _post("validate", {"license_key": cfg["license_key"], "instance_id": cfg.get("license_instance", "")})
    except LicenseError:
        if time.time() - float(cfg.get("license_checked") or 0) > OFFLINE_GRACE:
            return {"license_valid": False}
        return {}
    ok = bool(res.get("valid")) and (res.get("license_key") or {}).get("status") in ("active", None)
    try:
        _check_product(res.get("meta") or {})
    except LicenseError:
        ok = False
    return {"license_valid": ok, "license_checked": time.time(),
            "license_expires": (res.get("license_key") or {}).get("expires_at") or ""}


def status(cfg: dict) -> dict:
    licensed = bool(cfg.get("license_valid") and cfg.get("license_key"))
    used = int(cfg.get("free_reels_used") or 0)
    return {
        "licensed": licensed,
        "expires": cfg.get("license_expires") or "",
        "free_left": 0 if licensed else max(0, FREE_REELS - used),
        "dev": os.environ.get("IMAN_DEV") == "1",
    }


def can_edit(cfg: dict) -> tuple[bool, bool]:
    """(se puede editar, lleva marca de agua)."""
    st = status(cfg)
    if st["licensed"] or st["dev"]:
        return True, False
    return st["free_left"] > 0, True
