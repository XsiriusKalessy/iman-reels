"""Cliente de la IA incluida: habla con el servidor de Imán (carpeta `iman_cloud`)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .ai import AIConfig

CLOUD_URL = os.environ.get("IMAN_CLOUD_URL", "https://api.imanreels.com")


class CloudError(RuntimeError):
    pass


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
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("detail", "")
        except Exception:
            detail = ""
        raise CloudError(detail or f"El servidor de Imán respondió {e.code}") from e
    except OSError as e:
        raise CloudError("No hay conexión con el servidor de Imán") from e
