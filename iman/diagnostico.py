"""Diagnóstico de Imán en este ordenador: qué está bien y qué falta, en una lista que se entiende.

Para la beta: antes de preguntar «¿qué te falla?», el creador pulsa «Diagnóstico» y ve si ffmpeg está, si el
modelo que transcribe ya se descargó, si hay sitio en el disco, cuánta memoria tiene, si la IA está configurada,
si la licencia vale y si los recortes de persona y manos funcionan. Cada línea trae qué hacer si está mal.
Nunca enseña claves ni la licencia completa.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from . import config, equipo, license, media

MIN_DISK_GB = 3.0


def _item(key: str, label: str, ok: bool | None, detail: str = "", tip: str = "") -> dict:
    return {"key": key, "label": label, "ok": ok, "detail": detail, "tip": tip if not ok else ""}


def _ffmpeg_version() -> str:
    try:
        out = subprocess.run([media.FFMPEG, "-version"], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=10).stdout
        return out.split("\n", 1)[0].replace("ffmpeg version ", "")[:40]
    except Exception:  # noqa: BLE001
        return ""


def whisper_cached(model: str) -> bool:
    """Si el modelo de faster-whisper ya está descargado (sin red no se puede transcribir en local)."""
    roots = [Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub"]
    names = [f"models--Systran--faster-whisper-{model}", f"models--guillaumekln--faster-whisper-{model}"]
    return any((r / n).exists() for r in roots for n in names)


def disk_free_gb(path: Path) -> float:
    try:
        return shutil.disk_usage(str(path if path.exists() else path.parent)).free / 1024 ** 3
    except OSError:
        return -1.0


def run(cfg: dict | None = None) -> dict:
    cfg = cfg or config.load()
    items: list[dict] = []
    ver = _ffmpeg_version()
    items.append(_item("ffmpeg", "ffmpeg (monta el vídeo)", bool(ver), ver or "no encontrado",
                       "Vuelve a instalar Imán: ffmpeg viene dentro del instalador."))
    eq = equipo.info()
    items.append(_item("equipo", "Tu ordenador", not eq["weak"],
                       f"{eq['cores']} núcleos · {eq['ram_gb']} GB de memoria · {'con' if eq['gpu'] else 'sin'} aceleración gráfica",
                       "Es un ordenador sencillo: Imán usa el modo ligero (sin los efectos más pesados). Puedes forzarlo en Ajustes."))
    free = disk_free_gb(config.HOME)
    items.append(_item("disco", "Sitio en el disco", free < 0 or free >= MIN_DISK_GB,
                       f"{free:.1f} GB libres" if free >= 0 else "no se ha podido medir",
                       f"Libera espacio: cada reel ocupa unos cientos de MB mientras se monta (mínimo {MIN_DISK_GB:.0f} GB)."))
    eng = cfg.get("transcriber", "local")
    if eng == "local":
        model = str(cfg.get("whisper_model", "small"))
        cached = whisper_cached(model)
        items.append(_item("modelo", "Modelo que te escucha (en local)", cached,
                           f"«{model}» {'descargado' if cached else 'aún no descargado'}",
                           "Se descarga solo la primera vez que edites un reel (hace falta internet ese rato, unos 500 MB)."))
    else:
        items.append(_item("modelo", "Transcripción por OpenAI", bool(cfg.get("openai_key")),
                           "clave puesta" if cfg.get("openai_key") else "sin clave",
                           "Pega tu clave de OpenAI en Ajustes o cambia a la transcripción en local."))
    ai = config.ai_config(cfg)
    prov = cfg.get("provider", "")
    items.append(_item("ia", "IA que edita", bool(ai.enabled),
                       {"iman": "la de Imán (con tu licencia)", "claude": "tu Claude", "openai": "tu ChatGPT",
                        "none": "desactivada"}.get(prov, prov or "sin configurar"),
                       "En Ajustes › IA que edita elige «La de Imán» (con licencia) o pega tu propia clave; sin IA, Imán monta "
                       "igual pero sin guion ni textos."))
    st = license.status(cfg)
    items.append(_item("licencia", "Licencia", bool(st.get("licensed")),
                       st.get("plan_label") or f"prueba ({st.get('free_left', 0)} reels gratis)",
                       "Activa tu licencia en Ajustes para seguir editando sin marca de agua."))
    try:
        from . import segment

        seg_ok = segment.available()
    except Exception:  # noqa: BLE001
        seg_ok = False
    items.append(_item("recorte", "Recorte de persona (texto detrás de ti, fondos)", seg_ok,
                       "listo" if seg_ok else "no disponible",
                       "Vuelve a instalar Imán: faltan el modelo o la librería de recorte."))
    try:
        from . import hands

        hands_ok = hands.available()
    except Exception:  # noqa: BLE001
        hands_ok = False
    items.append(_item("manos", "Efectos que siguen tus manos", hands_ok, "listo" if hands_ok else "no disponible",
                       "Vuelve a instalar Imán: falta el modelo de manos."))
    jobs = config.HOME / "jobs"
    errors = sorted(jobs.glob("*/error.log"), key=lambda p: p.stat().st_mtime, reverse=True) if jobs.exists() else []
    last = ""
    if errors:
        try:
            last = errors[0].read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1][:200]
        except (OSError, IndexError):
            last = ""
    items.append(_item("errores", "Últimos reels", not errors, f"{len(errors)} con error" if errors else "sin errores",
                       f"El último error: «{last}». Si se repite, mándalo con «Enviar opinión»."))
    ok = all(i["ok"] for i in items if i["key"] not in ("licencia", "ia", "equipo", "errores"))
    from . import __version__

    return {"ok": ok, "version": __version__, "system": f"{platform.system()} {platform.release()} · Python {sys.version.split()[0]}",
            "items": items}


def as_text(d: dict) -> str:
    lines = [f"Diagnóstico de Imán {d['version']} · {d['system']}"]
    for i in d["items"]:
        mark = "OK" if i["ok"] else "AVISO"
        lines.append(f"- {mark} {i['label']}: {i['detail']}" + (f" → {i['tip']}" if i["tip"] else ""))
    return "\n".join(lines)
