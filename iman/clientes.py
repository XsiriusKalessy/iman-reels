"""Multi-cliente (Pro): una marca (colores, logo, tono, cierre) por cada cliente de la agencia.

El cliente activo decide qué «Mi marca» se usa al montar; cada reel recuerda para qué cliente se hizo, y la
biblioteca se filtra por cliente. Sin cliente activo, se usa la marca propia de siempre (carpeta «marca»).
"""
from __future__ import annotations

import re
import shutil
import time
import uuid

from . import config

MAX = 30


def listar() -> list[dict]:
    return [c for c in config.load().get("clientes") or [] if isinstance(c, dict) and c.get("id")]


def activo() -> str:
    cfg = config.load()
    cur = str(cfg.get("cliente") or "")
    return cur if any(c["id"] == cur for c in listar()) else ""


def dir_for(cid: str):
    return config.HOME / "clientes" / cid


def crear(name: str) -> dict:
    name = " ".join((name or "").split())[:40]
    if not name:
        raise ValueError("Ponle nombre al cliente")
    items = listar()
    if len(items) >= MAX:
        raise ValueError(f"Como mucho {MAX} clientes")
    if any(c["name"].lower() == name.lower() for c in items):
        raise ValueError("Ya tienes un cliente con ese nombre")
    cid = re.sub(r"[^a-z0-9]+", "", name.lower().translate(str.maketrans("áéíóúñü", "aeiounu")))[:12] or "c"
    cid = f"{cid}{uuid.uuid4().hex[:4]}"
    item = {"id": cid, "name": name, "created": time.time()}
    config.save({"clientes": items + [item]})
    (dir_for(cid) / "marca").mkdir(parents=True, exist_ok=True)
    return item


def borrar(cid: str) -> bool:
    items = listar()
    keep = [c for c in items if c["id"] != cid]
    if len(keep) == len(items):
        return False
    changes = {"clientes": keep}
    if activo() == cid:
        changes["cliente"] = ""
    config.save(changes)
    if cid.isalnum() and dir_for(cid).exists():
        shutil.rmtree(dir_for(cid), ignore_errors=True)
    return True


def activar(cid: str) -> str:
    if cid and not any(c["id"] == cid for c in listar()):
        raise ValueError("No encuentro ese cliente")
    config.save({"cliente": cid or ""})
    return cid or ""


def nombre(cid: str) -> str:
    return next((c["name"] for c in listar() if c["id"] == cid), "")
