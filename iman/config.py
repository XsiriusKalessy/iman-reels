"""Ajustes locales (proveedor de IA y claves) en ~/.iman/config.json."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .ai import AIConfig

HOME = Path(os.environ.get("IMAN_HOME", Path.home() / ".iman"))
CONFIG_FILE = HOME / "config.json"

DEFAULTS = {
    "provider": "claude",
    "anthropic_key": "",
    "openai_key": "",
    "claude_model": "claude-opus-5-5",
    "openai_model": "gpt-4o",
    "transcriber": "local",
    "whisper_model": "small",
    "language": "es",
}


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
    out = {k: v for k, v in cfg.items() if not k.endswith("_key")}
    out["has_anthropic_key"] = bool(cfg["anthropic_key"])
    out["has_openai_key"] = bool(cfg["openai_key"])
    return out


def ai_config(cfg: dict) -> AIConfig:
    return AIConfig(
        provider=cfg["provider"],
        anthropic_key=cfg["anthropic_key"] or None,
        openai_key=cfg["openai_key"] or None,
        claude_model=cfg["claude_model"],
        openai_model=cfg["openai_model"],
    )
