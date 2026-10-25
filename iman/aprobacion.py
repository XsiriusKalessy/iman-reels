"""Modo equipo: un reel pasa por alguien antes de publicarse.

Quien edita lo marca «pendiente de aprobación» con una nota; quien revisa lo aprueba o pide cambios. Todo queda
en la carpeta del reel (job.json) y se ve en la biblioteca. Para mandárselo a la otra persona están las
descargas de siempre («Para WhatsApp»); los nombres del equipo se guardan en los ajustes.
"""
from __future__ import annotations

import time

ESTADOS = {"borrador": "Borrador", "pendiente": "Pendiente de aprobación", "aprobado": "Aprobado", "cambios": "Pide cambios"}


def set_state(job: dict, estado: str, por: str = "", nota: str = "") -> dict:
    if estado not in ESTADOS:
        raise ValueError("Estado no válido")
    por = " ".join((por or "").split())[:40]
    nota = " ".join((nota or "").split())[:300]
    hist = list((job.get("revision") or {}).get("historial") or [])[-19:]
    hist.append({"estado": estado, "por": por, "nota": nota, "fecha": time.time()})
    job["revision"] = {"estado": estado, "por": por, "nota": nota, "fecha": time.time(), "historial": hist}
    return job["revision"]


def badge(job: dict) -> str:
    """Lo que sale en la tarjeta de la biblioteca ("" si no está en revisión)."""
    r = job.get("revision") or {}
    e = r.get("estado")
    return {"pendiente": "⏳ Pendiente", "aprobado": "✅ Aprobado", "cambios": "✏️ Cambios"}.get(e, "")


def team(cfg: dict) -> list[str]:
    return [str(n)[:40] for n in (cfg.get("equipo") or []) if str(n).strip()][:10]
