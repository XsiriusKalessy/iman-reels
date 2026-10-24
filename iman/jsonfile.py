"""Guardar y leer JSON sin dejar archivos a medias.

Si algo falla mientras se escribe (un corte de luz, un error), el archivo anterior
sigue entero: escribimos en uno temporal y lo cambiamos de golpe.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def save(path: Path, data, **dumps) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, **dumps), encoding="utf-8")
    os.replace(tmp, path)


def load(path: Path):
    """El contenido, o None si no existe o se guardó mal (vacío o cortado)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
