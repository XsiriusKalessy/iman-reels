"""Ajustes locales (proveedor de IA y claves) en ~/.iman/config.json."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .ai import AIConfig

HOME = Path(os.environ.get("IMAN_HOME", Path.home() / ".iman"))
CONFIG_FILE = HOME / "config.json"

DEFAULTS = {
    # "iman": la IA incluida en la licencia (servidor de Imán). "claude"/"openai": tu propia clave.
    "provider": "iman",
    "anthropic_key": "",
    "openai_key": "",
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
    # "Recuérdalo para mis próximos reels": preferencias que se aplican a todos los reels nuevos.
    "memory": [],
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
    return "PREFERENCIAS GUARDADAS DEL CREADOR (aplícalas siempre):\n" + "\n".join(f"- {m}" for m in mem)


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        cfg.update(json.loads(CONFIG_FILE.read_text()))
    # Las variables de entorno mandan si existen.
    cfg["anthropic_key"] = os.environ.get("ANTHROPIC_API_KEY") or cfg["anthropic_key"]
    cfg["openai_key"] = os.environ.get("OPENAI_API_KEY") or cfg["openai_key"]
    return cfg


def save(updates: dict) -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        cfg.update(json.loads(CONFIG_FILE.read_text()))
    for k, v in updates.items():
        if k in DEFAULTS and v is not None:
            cfg[k] = v
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
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
    from .license import status

    out["license"] = status(cfg)
    return out


def ai_config(cfg: dict) -> AIConfig:
    return AIConfig(
        provider=cfg["provider"],
        anthropic_key=cfg["anthropic_key"] or None,
        openai_key=cfg["openai_key"] or None,
        claude_model=cfg["claude_model"],
        openai_model=cfg["openai_model"],
        license_key=cfg.get("license_key") or None,
        license_instance=cfg.get("license_instance") or None,
    )
