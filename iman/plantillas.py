"""Tus propias plantillas: guarda cómo quedó un reel y vuelve a montar los siguientes igual, con un clic.

Una plantilla es el conjunto de decisiones de un reel ya hecho (ritmo, estilo de subtítulos, gancho visual,
música, look, letra, red, sector, sonidos, barra, transiciones, fondo…). Si una opción iba en «auto», se guarda
lo que Imán eligió de verdad para ese reel, así la plantilla reproduce el resultado y no la suerte.
Se guardan en la carpeta de Imán del creador (plantillas.json); nunca salen de su ordenador.
"""
from __future__ import annotations

import time
import uuid

from . import config, jsonfile

# Opciones del reel que viajan con la plantilla (lo demás, como el título del gancho o el vídeo, es de cada reel).
FIELDS = ("rhythm", "style", "fit", "size", "hook", "gancho", "pack", "sfx", "punch", "barra", "transiciones",
          "look", "letra", "red", "music", "background", "idioma", "intensidad", "circulo")
MAX = 30


def _file():
    return config.HOME / "plantillas.json"


def listar() -> list[dict]:
    data = jsonfile.load(_file()) if _file().exists() else None
    items = data.get("plantillas") if isinstance(data, dict) else None
    return [p for p in items or [] if isinstance(p, dict) and p.get("id") and isinstance(p.get("options"), dict)]


def _guardar(items: list[dict]) -> None:
    jsonfile.save(_file(), {"plantillas": items[-MAX:]})


def from_job(options: dict, plan: dict | None = None) -> dict:
    """Las opciones de un reel hecho, con los «auto» resueltos a lo que se usó de verdad."""
    plan = plan or {}
    out = {k: options[k] for k in FIELDS if k in options}
    if out.get("style") in ("auto", "", None) and plan.get("caption_style"):
        out["style"] = plan["caption_style"]
    if out.get("music") == "auto" and plan.get("music"):
        out["music"] = plan["music"]
    if out.get("music") is True:
        out["music"] = "mia"
    if out.get("gancho") in ("auto", "", None) and plan.get("gancho"):
        out["gancho"] = plan["gancho"]
    if out.get("look") in ("auto", "", None) and plan.get("look"):
        out["look"] = plan["look"]
    if out.get("background") == "foto":  # la foto del fondo es de aquel reel, no de la plantilla
        out["background"] = ""
    return out


def crear(name: str, options: dict, plan: dict | None = None) -> dict:
    name = " ".join((name or "").split())[:40] or f"Plantilla {len(listar()) + 1}"
    item = {"id": uuid.uuid4().hex[:8], "name": name, "created": time.time(), "options": from_job(options, plan),
            "resumen": resumen(from_job(options, plan))}
    items = [p for p in listar() if p.get("name", "").lower() != name.lower()]  # el mismo nombre la sustituye
    items.append(item)
    _guardar(items)
    return item


def borrar(pid: str) -> bool:
    items = listar()
    keep = [p for p in items if p["id"] != pid]
    if len(keep) == len(items):
        return False
    _guardar(keep)
    return True


def resumen(options: dict) -> str:
    """Una línea para la tarjeta: «Rápido · Hormozi · Zoom seco · épica · instagram»."""
    bits = []
    labels = {"rapido": "Rápido", "dinamico": "Dinámico", "natural": "Natural", "sin_tocar": "Sin tocar"}
    if options.get("rhythm"):
        bits.append(labels.get(options["rhythm"], options["rhythm"]))
    for k in ("style", "gancho", "music", "look"):
        v = options.get(k)
        if v and v not in ("auto", True):
            bits.append(str(v).replace("_", " "))
    if options.get("red"):
        bits.append(options["red"])
    return " · ".join(bits)


def apply(options: dict, pid: str) -> dict:
    """Las opciones de un montaje con las de la plantilla encima (lo que no esté en ella se queda como viene)."""
    for p in listar():
        if p["id"] == pid:
            return {**options, **{k: v for k, v in p["options"].items() if k in FIELDS}}
    return options
