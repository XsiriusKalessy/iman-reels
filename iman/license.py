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

from . import offline_license

API = "https://api.lemonsqueezy.com/v1/licenses"
# Id del producto en Lemon Squeezy; evita que valga una clave de otra tienda.
PRODUCT_ID = os.environ.get("IMAN_LEMON_PRODUCT_ID", "")
FREE_REELS = 3
REVALIDATE_EVERY = 24 * 3600
OFFLINE_GRACE = 14 * 24 * 3600


# Planes: "normal" (la licencia de siempre), "pro" y "dueno" (el dueño de Imán: todo, sin límites).
PLAN_LABELS = {"normal": "Licencia", "pro": "Licencia Pro", "dueno": "Licencia de dueño"}
# Funciones solo de Pro (y del dueño): varios clientes con su marca cada uno. El resto es para todos.
PRO_FEATURES: set[str] = {"clientes"}


def plan(cfg: dict) -> str:
    key = cfg.get("license_key") or ""
    if offline_license.is_offline(key):
        p = (offline_license.read(key) or {}).get("p", "")
        return p if p in PLAN_LABELS else "normal"
    return "normal"


def has(cfg: dict, feature: str) -> bool:
    """Si esta licencia tiene una función. La de dueño y la Pro lo tienen todo."""
    if feature not in PRO_FEATURES:
        return True
    return status(cfg)["licensed"] and plan(cfg) in ("pro", "dueno")


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
    if offline_license.is_offline(key):
        info = offline_license.read(key)
        if not info:
            raise LicenseError("Esta clave no es válida o ha caducado")
        return {"license_key": key.strip(), "license_instance": "", "license_expires": info.get("exp", ""),
                "license_checked": time.time(), "license_valid": True}
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
    if offline_license.is_offline(cfg.get("license_key") or ""):
        return
    if cfg.get("license_key") and cfg.get("license_instance"):
        try:
            _post("deactivate", {"license_key": cfg["license_key"], "instance_id": cfg["license_instance"]})
        except LicenseError:
            pass


def validate(cfg: dict) -> dict:
    """Comprueba la licencia como mucho una vez al día; sin conexión, aguanta 14 días."""
    if not cfg.get("license_key"):
        return {"license_valid": False}
    if offline_license.is_offline(cfg["license_key"]):  # firmada: se comprueba aquí mismo, sin internet
        return {"license_valid": offline_license.read(cfg["license_key"]) is not None, "license_checked": time.time()}
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


def _expired(cfg: dict) -> bool:
    """La licencia que tenía ha caducado (p. ej. una de la beta): para avisar con cariño, no con un error."""
    key = cfg.get("license_key") or ""
    if not key:
        return False
    exp = cfg.get("license_expires") or ""
    if offline_license.is_offline(key):
        return bool(exp) and exp < time.strftime("%Y-%m-%d")
    return bool(exp) and exp[:10] < time.strftime("%Y-%m-%d")


def status(cfg: dict) -> dict:
    licensed = bool(cfg.get("license_valid") and cfg.get("license_key"))
    used = int(cfg.get("free_reels_used") or 0)
    return {
        "licensed": licensed,
        "plan": plan(cfg) if licensed else "",
        "plan_label": PLAN_LABELS[plan(cfg)] if licensed else "",
        "expires": cfg.get("license_expires") or "",
        "free_left": 0 if licensed else max(0, FREE_REELS - used),
        "expired": not licensed and _expired(cfg),
        "dev": os.environ.get("IMAN_DEV") == "1",
    }


def can_edit(cfg: dict) -> tuple[bool, bool]:
    """(se puede editar, lleva marca de agua)."""
    st = status(cfg)
    if st["licensed"] or st["dev"]:
        return True, False
    return st["free_left"] > 0, True
