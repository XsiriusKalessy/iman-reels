"""Cliente de la IA incluida: habla con el servidor de Imán (carpeta `iman_cloud`)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .ai import AIConfig

CLOUD_URL = os.environ.get("IMAN_CLOUD_URL", "https://api.imanreels.com")


class CloudError(RuntimeError):
    def __init__(self, msg: str, code: int = 0, licensed: bool = True):
        super().__init__(msg)
        self.code, self.licensed = code, licensed


def _detail(raw: bytes) -> str:
    """El «detail» de FastAPI en una frase (un 422 trae una lista de errores)."""
    try:
        d = json.loads(raw).get("detail", "")
    except Exception:  # noqa: BLE001
        return ""
    if isinstance(d, list):
        return "; ".join(f"{'.'.join(str(x) for x in e.get('loc', [])[1:])}: {e.get('msg', '')}".strip(": ")
                         for e in d if isinstance(e, dict))[:300]
    return str(d)[:500]


def call(cfg: AIConfig, endpoint: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{CLOUD_URL.rstrip('/')}/v1/{endpoint}",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Iman-License": cfg.license_key or "",
            "X-Iman-Instance": cfg.license_instance or "",
        },
    )
    licensed = bool(cfg.license_key)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise CloudError(_detail(e.read()) or f"El servidor de Imán respondió {e.code}", e.code, licensed) from e
    except (OSError, ValueError) as e:
        raise CloudError("No hay conexión con el servidor de Imán", 0, licensed) from e
    if not isinstance(data, dict):
        raise CloudError("El servidor de Imán ha devuelto una respuesta rara", 502, licensed)
    return data
