"""Ajustes locales (proveedor de IA y claves) en ~/.iman/config.json."""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import jsonfile
from .ai import AIConfig

HOME = Path(os.environ.get("IMAN_HOME", Path.home() / ".iman"))
CONFIG_FILE = HOME / "config.json"

DEFAULTS = {
    # "iman": la IA incluida en la licencia (servidor de Imán). "claude"/"openai": tu propia clave.
    "provider": "iman",
    "anthropic_key": "",
    "openai_key": "",
    "pexels_key": "",  # gratis en pexels.com/api: planos de apoyo de 1-2 s
    "claude_model": "claude-opus-5-5",
    "openai_model": "gpt-4o",
    "transcriber": "local",
    "whisper_model": "small",
    "language": "es",
    "license_key": "",
    "license_instance": "",
    "license_expires": "",
    "license_checked": 0,
    "license_valid": False,
    "free_reels_used": 0,
    # Modo ligero para ordenadores sencillos: "auto" (lo decide Imán según tu ordenador), "si" o "no".
    "ligero": "auto",
    # Formulario de opiniones y fallos (beta). Vacío: el botón copia los datos y te dice a dónde mandarlos.
    "feedback_url": os.environ.get("IMAN_FEEDBACK_URL", ""),
    # "Recuérdalo para mis próximos reels": preferencias que se aplican a todos los reels nuevos.
    "memory": [],
    # Modo equipo: nombres de quienes revisan y aprueban reels (iman/aprobacion.py).
    "equipo": [],
    # Multi-cliente (Pro): lista de clientes [{id, name, created}] y el activo (iman/clientes.py).
    "clientes": [],
    "cliente": "",
}

MEMORY_MAX = 20


def remember(text: str) -> list[str]:
    text = " ".join(text.split())[:300]
    mem = [m for m in load().get("memory", []) if m.lower() != text.lower()]
    if text:
        mem = (mem + [text])[-MEMORY_MAX:]
    save({"memory": mem})
    return mem


def memory_prompt(cfg: dict) -> str:
    mem = cfg.get("memory") or []
    if not mem:
        return ""
    return ("PREFERENCIAS GUARDADAS DEL CREADOR (aplícalas siempre, salvo que las instrucciones de este reel digan "
            "otra cosa):\n" + "\n".join(f"- {m}" for m in mem))


def _stored() -> dict:
    """Lo guardado en disco; si el archivo se rompió (corte de luz), se parte de los valores por defecto."""
    data = jsonfile.load(CONFIG_FILE) if CONFIG_FILE.exists() else None
    return {k: v for k, v in data.items() if k in DEFAULTS} if isinstance(data, dict) else {}


def load() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(_stored())
    if not isinstance(cfg.get("license_checked"), (int, float)) or cfg["license_checked"] > __import__("time").time() + 86400:
        cfg["license_checked"] = 0  # un reloj adelantado no alarga la licencia
    # Las variables de entorno mandan si existen.
    cfg["anthropic_key"] = os.environ.get("ANTHROPIC_API_KEY") or cfg["anthropic_key"]
    cfg["openai_key"] = os.environ.get("OPENAI_API_KEY") or cfg["openai_key"]
    return cfg


def save(updates: dict) -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(_stored())
    for k, v in updates.items():
        if k in DEFAULTS and v is not None:
            cfg[k] = v
    HOME.mkdir(parents=True, exist_ok=True)
    jsonfile.save(CONFIG_FILE, cfg, indent=2)
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass
    return load()


def public(cfg: dict) -> dict:
    """Versión para enseñar en la web: nunca devuelve las claves."""
    out = {k: v for k, v in cfg.items() if not k.endswith("_key") and not k.startswith("license_")}
    out["has_anthropic_key"] = bool(cfg["anthropic_key"])
    out["has_openai_key"] = bool(cfg["openai_key"])
    out["has_pexels_key"] = bool(cfg.get("pexels_key"))
    from .license import status

    out["license"] = status(cfg)
    from .equipo import info

    out["equipo"] = info()
    return out


def ai_config(cfg: dict) -> AIConfig:
    provider = cfg["provider"]
    if provider == "iman":  # si has puesto tu propia clave, manda ella
        provider = "claude" if cfg["anthropic_key"] else "openai" if cfg["openai_key"] else "iman"
    return AIConfig(
        provider=provider,
        anthropic_key=cfg["anthropic_key"] or None,
        openai_key=cfg["openai_key"] or None,
        claude_model=cfg["claude_model"],
        openai_model=cfg["openai_model"],
        license_key=cfg.get("license_key") or None,
        license_instance=cfg.get("license_instance") or None,
    )
