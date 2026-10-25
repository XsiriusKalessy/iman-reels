"""Servidor web local: `iman web` y abre http://localhost:8765"""

from __future__ import annotations

import io
import json
import logging
import math
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, fields, replace
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai, aprobacion, brand, clientes, config, copystyle, effects, equipo, ganchos, inspiracion, jsonfile, license, logros, media, musica, packs, pipeline, plantillas, portable, promo, redes, resultados, tendencias, updates
from . import captions as captions_mod
from .captions import STYLES
from .models import EditPlan, Word
from .rhythm import RHYTHMS

WEB = Path(__file__).parent / "web"
JOBS_DIR = config.HOME / "jobs"

app = FastAPI(title="Imán")
log = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def _any_error(request, e: Exception):
    import traceback

    traceback.print_exception(e)  # va a ~/.iman/registro.txt en la app de escritorio
    return JSONResponse({"detail": ai.error_message(e)}, status_code=500)
JOBS: dict[str, dict] = {}
_lock = threading.Lock()
_cfg_lock = threading.Lock()  # los contadores de ajustes se tocan de uno en uno
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}


@app.middleware("http")
async def _solo_local(request, call_next):
    """Imán solo atiende a este ordenador: una web abierta en el navegador no puede darle órdenes (DNS rebinding,
    peticiones cruzadas)."""
    from urllib.parse import urlparse

    if (request.url.hostname or "").lower() not in _LOCAL_HOSTS:
        return JSONResponse({"detail": "Imán solo responde desde este ordenador"}, status_code=403)
    origin = request.headers.get("origin")
    if origin and request.method not in ("GET", "HEAD", "OPTIONS") \
            and (urlparse(origin).hostname or "").lower() not in _LOCAL_HOSTS:
        return JSONResponse({"detail": "Petición rechazada"}, status_code=403)
    return await call_next(request)


def _dir(job_id: str) -> Path:
    """Carpeta del reel; 404 si el id no tiene la pinta de un id de Imán."""
    if not job_id.isalnum():
        raise HTTPException(404)
    return JOBS_DIR / job_id


def _child(base: Path, name: str) -> Path:
    """Archivo dentro de una carpeta del reel; 404 si el nombre intenta salir de ella (también en Windows)."""
    if not name or ".." in name or any(c in name for c in "/\\:\0") or name.startswith("."):
        raise HTTPException(404)
    p = base / name
    try:
        p.resolve().relative_to(base.resolve())
    except ValueError:
        raise HTTPException(404) from None
    if not p.is_file():
        raise HTTPException(404)
    return p


def _original(workdir: Path) -> Path:
    src = next(workdir.glob("original.*"), None)
    if src is None:
        raise HTTPException(409, "Falta el vídeo original de ese reel: súbelo otra vez")
    return src


def _done_job(job_id: str) -> dict:
    """Un reel terminado con su plan (los vídeos largos se reparten en reels: hay que elegir uno)."""
    job = _job(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "No encuentro ese reel")
    if not (job.get("result") or {}).get("plan"):
        raise HTTPException(409, "Ese vídeo largo se ha repartido en varios reels: elige uno de ellos")
    return job


def _count_trial(delta: int) -> None:
    with _cfg_lock:
        used = int(config.load().get("free_reels_used") or 0)
        config.save({"free_reels_used": max(0, used + delta)})


MAX_VIDEO = 6 * 1024 ** 3
MAX_MEDIA = 1024 ** 3
MAX_PHOTO = 60 * 1024 ** 2
VIDEO_TYPES = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp", ".mts")


def _save_upload(up: UploadFile, dst: Path, limit: int) -> None:
    """Copia la subida a trozos y corta si pasa del límite (sin cargarla entera en memoria)."""
    total = 0
    with dst.open("wb") as f:
        while chunk := up.file.read(1 << 20):
            total += len(chunk)
            if total > limit:
                f.close()
                dst.unlink(missing_ok=True)
                raise HTTPException(413, f"El archivo es demasiado grande (máximo {limit // 1024 ** 2} MB)")
            f.write(chunk)


def _read_upload(up: UploadFile, limit: int) -> bytes:
    data = up.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"El archivo es demasiado grande (máximo {limit // 1024 ** 2} MB)")
    return data


_file_locks: dict[Path, threading.Lock] = {}


def _lock_for(path: Path) -> threading.Lock:
    """Un candado por archivo generado: dos pestañas no lanzan el mismo ffmpeg a la vez."""
    with _lock:
        return _file_locks.setdefault(path, threading.Lock())


def _set(job_id: str, **kw) -> None:
    with _lock:
        if kw.get("status") == "done":
            kw.setdefault("finished", time.time())
        JOBS[job_id].update(kw)
        if JOBS[job_id].get("status") != "working":
            _save_job(JOBS[job_id])


def _claim(job_id: str, **kw) -> None:
    """Marca el reel como «editándose» solo si nadie lo está montando ya (dos montajes a la vez sobre los mismos
    archivos los estropean)."""
    with _lock:
        job = JOBS.get(job_id)
        if not job or job.get("status") == "working":
            raise HTTPException(409, "Ese reel ya se está editando: espera a que termine")
        job["prev_options"] = job.get("options")
        job.update(status="working", **kw)


def _friendly(e: Exception) -> str:
    """El error en palabras para el creador (el detalle técnico va al registro)."""
    msg = str(e)
    if "ffmpeg" in msg.lower() or "Invalid" in msg or "NAL" in msg:
        return ("No he podido montar el vídeo. Vuelve a intentarlo; si se repite, sube otra vez el vídeo original "
                "(puede que el archivo se haya copiado mal).")
    if len(msg) > 300:
        return "Algo ha fallado al editar. Vuelve a intentarlo y, si se repite, avísanos."
    return msg


def _save_job(job: dict) -> None:
    """Guarda el estado del reel en disco para que siga en la biblioteca al reiniciar Imán."""
    d = JOBS_DIR / job["id"]
    if d.exists():
        jsonfile.save(d / "job.json", {k: v for k, v in job.items() if k != "trial"})


def _job(job_id: str) -> dict | None:
    if job_id in JOBS:
        return JOBS[job_id]
    if not job_id.isalnum():
        return None
    job = jsonfile.load(JOBS_DIR / job_id / "job.json")
    if not isinstance(job, dict) or job.get("id") != job_id:
        return None
    if job.get("status") == "working":  # Imán se cerró a mitad
        job.update(status="error", error="La edición se interrumpió. Vuelve a aplicar los cambios.")
    with _lock:
        JOBS[job_id] = job
    return job


@app.get("/api/reels")
def reels():
    """Biblioteca: tus reels, del más nuevo al más antiguo."""
    out = []
    for f in JOBS_DIR.glob("*/job.json") if JOBS_DIR.exists() else []:
        job = _job(f.parent.name)
        if not job or job.get("status") != "done" or "clips" in (job.get("result") or {}):
            continue
        r = job.get("result") or {}
        out.append({"id": job["id"], "created": job.get("created", 0), "title": (r.get("plan") or {}).get("hook_title", ""),
                    "duration": r.get("duration_out", 0), "pack": (job.get("options") or {}).get("pack", ""),
                    "resultados": job.get("resultados") or {}, "revision": aprobacion.badge(job),
                    "revision_estado": (job.get("revision") or {}).get("estado", ""), "cliente": job.get("cliente", "")})
    return {"reels": sorted(out, key=lambda r: -r["created"])}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    job = _job(job_id)
    if not job or job["status"] == "working":
        raise HTTPException(404, "No encuentro ese reel o aún se está editando")
    if (VERSIONS.get(job_id) or {}).get("status") == "working" or (CASCADES.get(job_id) or {}).get("status") == "working":
        raise HTTPException(409, "Espera a que terminen las versiones o la cascada de ese reel")
    shutil.rmtree(JOBS_DIR / job_id, ignore_errors=True)
    with _lock:
        JOBS.pop(job_id, None)
    VERSIONS.pop(job_id, None)
    CASCADES.pop(job_id, None)
    return {"ok": True}


@app.get("/api/options")
def options():
    return {
        "rhythms": [{"key": r.key, "label": r.label, "description": r.description} for r in RHYTHMS.values()],
        "styles": _styles(),
        "hook_templates": HOOK_TEMPLATES,
        "ganchos": ganchos.catalogue(),
        "redes": [{"key": r.key, "label": r.label, "description": r.description} for r in redes.REDES.values()],
        "packs": [{"key": p.key, "label": p.label, "description": p.description, "style": p.style,
                   "hooks": list(p.hooks)} for p in packs.PACKS.values()],
    }


@app.get("/api/update")
def update_check(force: bool = False):
    if force:
        updates.latest(force=True)
    return {**updates.check(), "install": updates.install_status()}


@app.post("/api/update/install")
def update_install():
    info = updates.check()
    if not info.get("available"):
        raise HTTPException(400, "No hay ninguna versión nueva")
    if not info.get("covered"):
        raise HTTPException(402, "Esta versión salió después de que caducara tu licencia. Renueva para tenerla.")
    updates.start_install(info)
    return updates.install_status()


def _styles() -> list[dict]:
    copystyle.register()
    mine = copystyle.custom()
    return [{"key": s.key, "label": s.label, "mine": s.key in mine, "rhythm": mine.get(s.key, {}).get("rhythm", ""),
             "notes": mine.get(s.key, {}).get("notes", ""), "look": _style_look(s)} for s in STYLES.values()]


def _hex(ass: str) -> str:
    """'&H00BBGGRR' -> '#RRGGBB' para pintar la vista previa del estilo."""
    h = (ass or "").replace("&H", "").replace("&", "")[-6:].rjust(6, "0")
    return f"#{h[4:6]}{h[2:4]}{h[0:2]}"


def _style_look(s) -> dict:
    return {"font": s.font, "size": s.size, "text": _hex(s.text), "accent": _hex(s.accent), "outline": _hex(s.outline),
            "outline_w": s.outline_w, "shadow": s.shadow, "upper": s.uppercase, "box": _hex(s.box) if s.box else "",
            "words": s.max_words, "entry": getattr(s, "entry", "pop"), "alt_font": getattr(s, "alt_font", "")}


@app.post("/api/styles/copy")
async def copy_style(file: UploadFile = File(...), name: str = Form("")):
    """Copiar el estilo de un reel: letra, colores, cuántas palabras y ritmo. Nunca el contenido."""
    aicfg = config.ai_config(config.load())
    if not aicfg.enabled:
        raise HTTPException(400, "Activa la IA en Ajustes para copiar el estilo de un reel")
    suffix = Path(file.filename or "reel.mp4").suffix.lower() or ".mp4"
    if suffix not in (".mp4", ".mov", ".m4v", ".webm", ".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(400, "Sube el reel en vídeo (MP4, MOV) o una captura")
    tmp = config.HOME / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    src = tmp / f"estilo-{uuid.uuid4().hex[:8]}{suffix}"
    try:
        with src.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            shots = copystyle.frames(src)
            rate = copystyle.cut_rate(src)
        except Exception:
            raise HTTPException(400, "No he podido leer ese archivo. Prueba con el vídeo del reel en MP4.")
        try:
            analysis = ai.style_from_frames(aicfg, shots)
        except Exception as e:
            raise HTTPException(502, f"La IA no ha podido analizar el reel. {ai.error_message(e)}")
        saved = copystyle.save(name.strip() or analysis.get("name") or "Mi estilo", analysis,
                               copystyle.rhythm_for(rate))
    finally:
        src.unlink(missing_ok=True)
    return {"key": saved["key"], "label": saved["style"]["label"], "rhythm": saved["rhythm"], "notes": saved["notes"],
            "styles": _styles()}


@app.delete("/api/styles/{key}")
def delete_style(key: str):
    if not key.startswith("mio-"):
        raise HTTPException(400, "Solo puedes borrar tus estilos")
    copystyle.remove(key)
    return {"styles": _styles()}


HOOK_TEMPLATES = [
    "El error que comete el 90% cuando…",
    "Nadie te cuenta esto sobre…",
    "Deja de hacer X si quieres Y",
    "Así conseguí X en Y días",
    "3 cosas que ojalá hubiera sabido antes de…",
    "Si haces esto, estás perdiendo dinero",
]


BROKEN_JOB = ("Este reel se guardó a medias por un fallo que ya está arreglado. Pulsa un cambio rápido "
              "(por ejemplo «Más natural») para rehacerlo y vuelve a probar.")


def _saved_words(workdir: Path) -> list[Word]:
    data = jsonfile.load(workdir / "transcript.json")
    if data is None:
        raise HTTPException(409, BROKEN_JOB)
    return [Word(**w) for w in data]


def _saved_plan(workdir: Path) -> EditPlan:
    data = jsonfile.load(workdir / "plan.json")
    if data is None:
        raise HTTPException(409, BROKEN_JOB)
    return EditPlan.from_dict(data)


@app.get("/api/settings")
def get_settings():
    return config.public(config.load())


class SettingsIn(BaseModel):
    provider: str | None = None
    ligero: str | None = None
    anthropic_key: str | None = None
    openai_key: str | None = None
    pexels_key: str | None = None
    transcriber: str | None = None
    whisper_model: str | None = None
    language: str | None = None


@app.post("/api/settings")
def set_settings(body: SettingsIn):
    data = {k: v for k, v in body.model_dump().items() if v is not None and v != ""}
    if data.get("ligero", "auto") not in ("auto", "si", "no"):
        raise HTTPException(400, "Modo ligero: auto, si o no")
    if data.get("provider", "iman") not in ("iman", "claude", "openai", "none") \
            or data.get("transcriber", "local") not in ("local", "openai") \
            or data.get("whisper_model", "small") not in ("tiny", "base", "small", "medium", "large-v3") \
            or not re.fullmatch(r"[a-z]{2}", data.get("language", "es")):
        raise HTTPException(400, "Opción no válida")
    for k in ("anthropic_key", "openai_key", "pexels_key"):
        if k in data:
            data[k] = data[k].strip()[:300]
    with _cfg_lock:
        return config.public(config.save(data))


class KeyTestIn(BaseModel):
    provider: str
    key: str = ""


@app.post("/api/settings/test-key")
def test_key(body: KeyTestIn):
    """Prueba la clave escrita, o la guardada si la casilla está vacía."""
    cfg = config.load()
    key = body.key or cfg.get("anthropic_key" if body.provider == "claude" else "openai_key") or ""
    if not key:
        return {"ok": False, "message": "Pega primero tu clave en la casilla."}
    try:
        who = ai.test_key(body.provider, key)
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    except Exception as e:  # noqa: BLE001 - se lo explicamos a la persona
        return {"ok": False, "message": ai.error_message(e)}
    return {"ok": True, "message": f"✓ Funciona. Tu clave de {who} está lista y tiene saldo."}


@app.get("/api/settings/export")
def export_settings(claves: bool = False):
    return Response(portable.export(claves), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="mis-ajustes.iman"'})


@app.post("/api/settings/import")
async def import_settings(file: UploadFile = File(...)):
    try:
        got = portable.import_(_read_upload(file, portable.MAX_SIZE))
    except portable.ImportError_ as e:
        raise HTTPException(400, str(e))
    return {"got": got, "settings": config.public(config.load())}


@app.get("/api/memory")
def get_memory():
    return {"memory": config.load().get("memory", [])}


class MemoryIn(BaseModel):
    text: str


@app.post("/api/memory")
def add_memory(body: MemoryIn):
    if not body.text.strip():
        raise HTTPException(400, "Escribe lo que quieres que recuerde")
    return {"memory": config.remember(body.text)}


@app.delete("/api/memory/{index}")
def delete_memory(index: int):
    mem = list(config.load().get("memory", []))
    if 0 <= index < len(mem):
        mem.pop(index)
        config.save({"memory": mem})
    return {"memory": mem}


# --- Tus propias plantillas: cómo quedó un reel, para montar los siguientes igual ---
@app.get("/api/plantillas")
def list_templates():
    return {"plantillas": plantillas.listar()}


class TemplateIn(BaseModel):
    name: str = ""
    job_id: str = ""


@app.post("/api/plantillas")
def create_template(body: TemplateIn):
    job = _job(body.job_id)
    if not job or job.get("status") != "done" or not job.get("result"):
        raise HTTPException(404, "Primero termina un reel: la plantilla se guarda a partir de uno hecho")
    item = plantillas.crear(body.name, job.get("options") or {}, (job.get("result") or {}).get("plan") or {})
    return {"plantilla": item, "plantillas": plantillas.listar()}


@app.delete("/api/plantillas/{pid}")
def delete_template(pid: str):
    if not plantillas.borrar(pid):
        raise HTTPException(404, "No encuentro esa plantilla")
    return {"plantillas": plantillas.listar()}


# --- Aprende de tus resultados: apunta cómo le fue a cada reel ---
def _reels_with_results() -> list[dict]:
    out = []
    for f in JOBS_DIR.glob("*/job.json") if JOBS_DIR.exists() else []:
        job = _job(f.parent.name)
        if not job or job.get("status") != "done" or not job.get("resultados"):
            continue
        r = job.get("result") or {}
        out.append({"id": job["id"], "title": (r.get("plan") or {}).get("hook_title", ""), "duration": r.get("duration_out", 0),
                    "options": job.get("options") or {}, "plan": r.get("plan") or {}, "resultados": job["resultados"]})
    return out


@app.get("/api/resultados")
def get_insights():
    return resultados.insights(_reels_with_results())


@app.post("/api/jobs/{job_id}/resultados")
def set_results(job_id: str, body: dict):
    job = _job(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "No encuentro ese reel")
    data = resultados.normalize(body if isinstance(body, dict) else {})
    with _lock:
        if data:
            JOBS[job_id]["resultados"] = {**data, "updated": time.time()}
        else:
            JOBS[job_id].pop("resultados", None)
        _save_job(JOBS[job_id])
    return {"resultados": JOBS[job_id].get("resultados"), "insights": resultados.insights(_reels_with_results())}


# --- Tanda 7: ideas en tendencia, reel antes/después, modo equipo y logros ---
@app.get("/api/tendencias")
def get_trends(pack: str = "", geo: str = "ES", force: bool = False):
    """Lo que se mueve hoy (Google Trends o Wikipedia, sin clave) convertido en ideas para tu sector."""
    data = tendencias.topics(geo, force=force)
    if not data.get("topics"):
        raise HTTPException(503, "No he podido leer las tendencias de hoy. Comprueba la conexión y vuelve a probar.")
    key = pack if pack in packs.PACKS else "general"
    cached = (data.get("ideas") or {}).get(key)
    if cached is None or force:
        cfg = config.ai_config(config.load())
        try:
            cached = tendencias.ideas(cfg, data["topics"], pack, _voice_samples()) if cfg.enabled else []
        except Exception as e:  # noqa: BLE001 - sin IA se enseñan los temas tal cual
            log.warning("Tendencias sin ideas de la IA: %s", e)
            cached = []
        if cached:
            tendencias.remember_ideas(key, cached)
    return {"topics": data["topics"], "source": data.get("source", ""), "fetched": data.get("fetched", 0),
            "geo": data.get("geo", geo), "ideas": cached, "ai": config.ai_config(config.load()).enabled}


@app.post("/api/jobs/{job_id}/antes-despues")
def make_before_after(job_id: str):
    """Reel «antes y después»: 4 s de tu toma y, de un latigazo, el reel montado. Para enseñar tu proceso."""
    job = _job(job_id)
    if not job or job.get("status") != "done" or not (job.get("result") or {}).get("video"):
        raise HTTPException(404, "Primero termina el reel")
    workdir = _dir(job_id)
    src = next(workdir.glob("original.*"), None)
    reel = workdir / job["result"]["video"]
    if src is None or not reel.exists():
        raise HTTPException(404, "No encuentro el vídeo original o el reel")
    dst = workdir / "antes-despues.mp4"
    with _lock_for(dst):
        if not dst.exists() or dst.stat().st_mtime < reel.stat().st_mtime:
            promo.before_after(src, reel, dst, accent=brand.load().primary or "#FFD60A")
    return {"file": dst.name, "version": int(dst.stat().st_mtime)}


@app.get("/api/jobs/{job_id}/antes-despues.mp4")
def get_before_after(job_id: str):
    p = _dir(job_id) / "antes-despues.mp4"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4", filename=f"antes-despues-{job_id}.mp4")


class ReviewIn(BaseModel):
    estado: str = Field(..., max_length=20)
    por: str = Field("", max_length=40)
    nota: str = Field("", max_length=300)


@app.post("/api/jobs/{job_id}/revision")
def set_review(job_id: str, body: ReviewIn):
    """Modo equipo: pendiente de aprobación, aprobado o pide cambios, con quién y una nota."""
    job = _job(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "No encuentro ese reel")
    if body.estado not in aprobacion.ESTADOS:
        raise HTTPException(400, "Estado no válido")
    with _lock:
        rev = aprobacion.set_state(JOBS[job_id], body.estado, body.por, body.nota)
        _save_job(JOBS[job_id])
    if body.por.strip():  # el nombre se guarda para el equipo
        names = aprobacion.team(config.load())
        if body.por.strip()[:40] not in names:
            config.save({"equipo": (names + [body.por.strip()[:40]])[-10:]})
    return {"revision": rev, "equipo": aprobacion.team(config.load())}


@app.get("/api/equipo")
def get_team():
    return {"equipo": aprobacion.team(config.load()), "estados": aprobacion.ESTADOS}


@app.get("/api/logros")
def get_achievements():
    jobs = []
    for f in JOBS_DIR.glob("*/job.json") if JOBS_DIR.exists() else []:
        job = _job(f.parent.name)
        if job and job.get("status") == "done" and "clips" not in (job.get("result") or {}):
            jobs.append(job)
    return logros.compute(jobs)


# --- Multi-cliente (Pro): una marca por cliente ---
@app.get("/api/clientes")
def list_clients():
    cfg = config.load()
    return {"clientes": clientes.listar(), "activo": clientes.activo(), "pro": license.has(cfg, "clientes")}


class ClientIn(BaseModel):
    name: str = Field("", max_length=40)
    id: str = Field("", max_length=20)


@app.post("/api/clientes")
def create_client(body: ClientIn):
    if not license.has(config.load(), "clientes"):
        raise HTTPException(402, "Varios clientes con su marca es una función de la licencia Pro")
    try:
        item = clientes.crear(body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    clientes.activar(item["id"])
    return {"cliente": item, **list_clients()}


@app.post("/api/clientes/activo")
def activate_client(body: ClientIn):
    try:
        clientes.activar(body.id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {**list_clients(), "brand": _brand_out(brand.load())}


@app.delete("/api/clientes/{cid}")
def delete_client(cid: str):
    if not cid.isalnum() or not clientes.borrar(cid):
        raise HTTPException(404, "No encuentro ese cliente")
    return list_clients()


# --- Zona Inspiración: analizar un reel de otra persona (forma, nunca contenido) ---
@app.get("/api/inspiracion")
def list_inspiration():
    return {"items": [{k: v for k, v in it.items() if k != "style"} for it in inspiracion.listar()]}


@app.post("/api/inspiracion")
async def analyze_reel(file: UploadFile = File(...), pack: str = Form("")):
    aicfg = config.ai_config(config.load())
    if not aicfg.enabled:
        raise HTTPException(400, "Activa la IA en Ajustes para analizar un reel")
    suffix = Path(file.filename or "reel.mp4").suffix.lower() or ".mp4"
    if suffix not in VIDEO_TYPES:
        raise HTTPException(400, "Sube el reel en vídeo (MP4, MOV)")
    iid = uuid.uuid4().hex[:8]
    work = config.HOME / "tmp" / f"inspiracion-{iid}"
    work.mkdir(parents=True, exist_ok=True)
    src = work / f"reel{suffix}"
    try:
        with src.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            shots = copystyle.frames(src, 8)
        except Exception:
            raise HTTPException(400, "No he podido leer ese archivo. Prueba con el vídeo del reel en MP4.")
        words = []
        try:
            if media.probe(src).has_audio:
                words = pipeline._transcribe(src, work, config.load(), lambda m, p: None)
        except Exception:  # noqa: BLE001 - sin voz se analiza con los fotogramas
            log.exception("No se pudo transcribir el reel ajeno")
        m = inspiracion.metrics(src, words)
        sector = packs.PACKS[pack].label if pack in packs.PACKS else ""
        try:
            analysis = inspiracion.analyze(aicfg, shots, words, m, sector)
        except Exception as e:
            raise HTTPException(502, f"La IA no ha podido analizar el reel. {ai.error_message(e)}")
        style = None
        try:
            style = ai.style_from_frames(aicfg, shots)
        except Exception:  # noqa: BLE001 - el estilo de letra es un extra
            log.exception("No se pudo leer el estilo del reel ajeno")
        item = inspiracion.save({"title": analysis.get("title") or Path(file.filename or "reel").stem[:60],
                                 "file": Path(file.filename or "reel").name[:80], "metrics": m, "analysis": analysis,
                                 "style": style, "has_voice": bool(words)})
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {k: v for k, v in item.items() if k != "style"}


class InspirationIn(BaseModel):
    name: str = Field("", max_length=40)


@app.post("/api/inspiracion/{iid}/plantilla")
def inspiration_template(iid: str, body: InspirationIn):
    item = inspiracion.get(iid)
    if not item:
        raise HTTPException(404, "No encuentro ese análisis")
    t = inspiracion.as_template(item, body.name or item.get("title") or "Inspiración")
    return {"plantilla": t}


@app.delete("/api/inspiracion/{iid}")
def delete_inspiration(iid: str):
    if not inspiracion.borrar(iid):
        raise HTTPException(404, "No encuentro ese análisis")
    return list_inspiration()


def _learned_prompt() -> str:
    try:
        return resultados.prompt(resultados.insights(_reels_with_results()))
    except Exception:  # noqa: BLE001 - un job.json raro no puede parar un montaje
        log.exception("No se pudo leer lo aprendido de los resultados")
        return ""


class LicenseIn(BaseModel):
    key: str


@app.post("/api/license")
def activate_license(body: LicenseIn):
    try:
        data = license.activate(body.key)
    except license.LicenseError as e:
        raise HTTPException(400, str(e))
    return config.public(config.save(data))


@app.delete("/api/license")
def remove_license():
    cfg = config.load()
    license.deactivate(cfg)
    return config.public(config.save({"license_key": "", "license_instance": "", "license_valid": False}))


def _refresh_license() -> dict:
    cfg = config.load()
    upd = license.validate(cfg)
    return config.save(upd) if upd else cfg


def _brand_out(b: brand.Brand) -> dict:
    fonts = brand.fonts()
    return {**asdict(b), "has_logo": b.logo_path is not None, "fonts": list(fonts),
            "my_font": fonts.get(brand.MINE, "")}


@app.get("/api/brand")
def get_brand():
    return _brand_out(brand.load())


class BrandIn(BaseModel):
    name: str | None = None
    description: str | None = Field(None, max_length=300)
    company: str | None = Field(None, max_length=120)
    phrases: list[dict] | None = None
    voice: str | None = Field(None, max_length=600)
    voice_examples: str | None = Field(None, max_length=3000)
    avoid: str | None = Field(None, max_length=1000)
    no_emojis: bool | None = None
    primary: str | None = None
    secondary: str | None = None
    font: str | None = None
    handle: str | None = None
    cta: str | None = None
    contact: str | None = None
    sector: str | None = None
    logo_corner: bool | None = None
    end_card: bool | None = None


@app.post("/api/brand")
def set_brand(body: BrandIn):
    b = brand.load()
    for k, v in body.model_dump().items():
        if v is None:
            continue
        if k in ("primary", "secondary") and v and not brand.is_hex(v):
            raise HTTPException(400, "El color tiene que ser tipo #FF5547")
        if k == "sector" and v and v not in packs.PACKS:
            raise HTTPException(400, "Sector no válido")
        if k == "font" and v and v not in brand.fonts():
            raise HTTPException(400, "Fuente no válida")
        if k == "phrases":
            v = brand.clean_phrases(v)
        setattr(b, k, v.strip() if isinstance(v, str) else v)
    return _brand_out(brand.save(b))


@app.post("/api/brand/logo")
async def upload_logo(logo: UploadFile = File(...)):
    data = await logo.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "El logo pesa demasiado (máximo 10 MB)")
    try:
        return _brand_out(brand.set_logo(data))
    except Exception:
        raise HTTPException(400, "No he podido leer esa imagen. Prueba con un PNG o JPG.")


@app.delete("/api/brand/logo")
def delete_logo():
    return _brand_out(brand.remove_logo())


@app.post("/api/brand/font")
async def upload_font(font: UploadFile = File(...)):
    data = await font.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "La fuente pesa demasiado (máximo 15 MB)")
    try:
        brand.set_font(font.filename or "fuente.ttf", data)
    except Exception:
        raise HTTPException(400, "No he podido leer esa fuente. Sube un archivo .ttf u .otf.")
    b = brand.load()
    b.font = brand.MINE
    return _brand_out(brand.save(b))


@app.delete("/api/brand/font")
def delete_font():
    brand.remove_font()
    b = brand.load()
    if b.font == brand.MINE:
        b.font = ""
    return _brand_out(brand.save(b))


@app.get("/api/brand/font")
def get_font():
    from . import textfit

    mine = textfit.user_fonts()
    if not mine:
        raise HTTPException(404)
    return FileResponse(next(iter(mine.values())))


@app.get("/api/brand/logo.png")
def get_logo():
    p = brand.load().logo_path
    if p is None:
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png")


class BrandAutoIn(BaseModel):
    description: str


@app.post("/api/brand/auto")
def brand_auto(body: BrandAutoIn):
    """La IA rellena nombre, cierre y fuente a partir de una frase sobre el negocio."""
    cfg = config.ai_config(config.load())
    if not cfg.enabled:
        raise HTTPException(400, "Activa la IA en Ajustes para que rellene tu marca")
    try:
        data = ai.brand_copy(cfg, body.description[:400])
    except Exception as e:
        raise HTTPException(502, f"La IA no ha podido preparar tu marca. {ai.error_message(e)}")
    b = brand.load()
    b.name = b.name or data.get("name", "")
    b.cta = data.get("cta") or b.cta
    if data.get("font") in brand.FONTS:
        b.font = data["font"]
    if data.get("sector") in packs.PACKS:
        b.sector = data["sector"]
    return _brand_out(brand.save(b))


class IdeasIn(BaseModel):
    topic: str
    audience: str = ""
    n: int = 3


@app.post("/api/ideas")
def ideas(body: IdeasIn):
    cfg = config.ai_config(config.load())
    if not cfg.enabled:
        raise HTTPException(400, "Configura Claude o ChatGPT en Ajustes para usar el agente de ideas")
    return {"ideas": ai.generate_ideas(cfg, body.topic, body.audience, _voice_samples(), body.n)}


class AgencyIn(BaseModel):
    destination: str = Field(..., max_length=200)
    dates: str = Field("", max_length=80)
    price: str = Field("", max_length=60)
    seats: str = Field("", max_length=40)
    includes: str = Field("", max_length=600)
    audience: str = Field("", max_length=200)


@app.post("/api/agencia")
def agencia(body: AgencyIn):
    """Modo agencia de viajes: destino y fechas → ganchos, guion, planos que grabar, ruta para el mapa y textos."""
    cfg = config.ai_config(config.load())
    if not cfg.enabled:
        raise HTTPException(400, "Configura Claude o ChatGPT en Ajustes para usar el modo agencia")
    data = ai.agency_plan(cfg, body.destination, body.dates, body.price, body.seats, body.includes, body.audience,
                          _voice_samples())
    data["route_text"] = ai.route_text(data.get("route", []))
    return data


class CalendarIn(BaseModel):
    pack: str = Field("general", max_length=20)
    topic: str = Field("", max_length=300)
    key_dates: str = Field("", max_length=1200)
    weeks: int = Field(2, ge=1, le=6)
    per_week: int = Field(3, ge=1, le=7)


@app.post("/api/calendario")
def calendario(body: CalendarIn):
    """Calendario de contenido: qué reel grabar cada día, por sector y fechas clave (salidas, Black Friday…)."""
    import datetime as _dt

    cfg = config.ai_config(config.load())
    if not cfg.enabled:
        raise HTTPException(400, "Configura Claude o ChatGPT en Ajustes para usar el calendario")
    pack = body.pack if body.pack in packs.PACKS else "general"
    items = ai.content_calendar(cfg, pack, body.topic, body.key_dates, body.weeks, body.per_week,
                                _dt.date.today().isoformat(), _voice_samples())
    return {"items": items}


@app.post("/api/comentario")
def comment_to_reel(texto: str = Form(""), autor: str = Form(""), captura: UploadFile | None = File(None)):
    """Reel desde un comentario: respuesta para el seguidor y guion de un reel nuevo que le responde."""
    image = None
    if captura is not None and captura.filename:
        from PIL import Image, ImageOps

        try:
            with Image.open(captura.file) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((1400, 1400))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=88)
                image = buf.getvalue()
        except Exception:  # noqa: BLE001
            raise HTTPException(400, "No puedo abrir esa captura. Prueba con una imagen JPG o PNG.") from None
    texto, autor = texto.strip()[:3000], autor.strip().lstrip("@")[:60]
    if not texto and image is None:
        raise HTTPException(400, "Pega el comentario o sube una captura")
    cfg = config.ai_config(config.load())
    if cfg.enabled:
        try:
            out = ai.comment_reel(cfg, texto, autor, image, _voice_samples())
            if brand.load().no_emojis:
                out = {k: brand.strip_emojis(v) if isinstance(v, str) else v for k, v in out.items()}
            return {**out, "ai": True}
        except Exception as e:  # noqa: BLE001
            if not texto:
                raise HTTPException(502, f"La IA no ha podido leer la captura: {ai.error_message(e)}") from None
    elif not texto:
        raise HTTPException(400, "Para leer la captura necesito tu IA conectada en Ajustes. Mientras, pega el texto.")
    return {**ai.comment_fallback(texto, autor), "ai": False}


def _voice_samples() -> str:
    """Transcripciones de reels anteriores, para que las ideas suenen a ti."""
    texts = []
    for t in sorted(JOBS_DIR.glob("*/transcript.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
        words = jsonfile.load(t)
        if isinstance(words, list):
            texts.append(" ".join(str(w.get("text", "")) for w in words if isinstance(w, dict)))
    voice = brand.load().copy_prompt()
    return "\n\n".join(p for p in (voice, "\n---\n".join(texts)) if p)


def _save_background(workdir: Path, raw: bytes) -> bool:
    """Guarda la foto de fondo como JPG vertical. Pasa por Pillow: solo entra una imagen de verdad."""
    from PIL import Image, ImageOps

    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception:  # noqa: BLE001 - no es una imagen
        return False
    im.thumbnail((2160, 3840))
    im.save(workdir / "fondo.jpg", quality=92)
    return True


MUSIC_TYPES = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac", ".opus")


def _save_music(workdir: Path, upload: UploadFile) -> bool:
    """Tu música de fondo: se guarda como musica.* solo si ffprobe ve una pista de audio de verdad."""
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in MUSIC_TYPES:
        return False
    dst = workdir / f"musica{suffix}"
    _save_upload(upload, dst, MAX_MEDIA)
    try:
        streams = media.probe_streams(dst)
    except Exception:  # noqa: BLE001 - archivo roto
        streams = []
    if not any(st.get("codec_type") == "audio" for st in streams):
        dst.unlink(missing_ok=True)
        return False
    return True


@app.get("/api/music")
def music_styles():
    return [{"key": k, "label": st.label} for k, st in musica.STYLES.items()]


@app.get("/api/music/{key}.wav")
def music_preview(key: str):
    """20 segundos del estilo para escucharlo antes de elegir (se guarda en caché)."""
    if key not in musica.STYLES:
        raise HTTPException(404, "Ese estilo no existe")
    dst = config.HOME / "cache" / "musica" / f"{key}-v3.wav"  # v3: si cambia el sonido, no sirve la vieja
    with _lock_for(dst):
        if not dst.exists():
            cine = musica.STYLES[key].cine  # los de tráiler: el golpe a los 4 s, como tras un gancho
            musica.render(key, 20, dst, seed=len(key), drop_at=4.0 if cine else None)
    return FileResponse(dst, media_type="audio/wav")


@app.post("/api/jobs")
async def create_job(
    video: list[UploadFile] = File(...),
    rhythm: str = Form("rapido"),
    style: str = Form("auto"),
    size: str = Form("1080"),
    fit: str = Form("recortar"),
    hook: bool = Form(True),
    hook_title: str = Form(""),
    hook_template: str = Form(""),
    gancho: str = Form("auto"),
    instructions: str = Form(""),
    voice: bool = Form(True),
    ruido: bool = Form(False),
    use_brand: bool = Form(True),
    pack: str = Form(""),
    remember: bool = Form(False),
    broll: list[UploadFile] | None = File(None),
    mode: str = Form("camara"),
    background: str = Form(""),
    background_photo: UploadFile | None = File(None),
    music_file: UploadFile | None = File(None),
    music_style: str = Form("auto"),
    sfx: bool = Form(True),
    punch: bool = Form(True),
    barra: bool = Form(False),
    transiciones: bool = Form(True),
    look: str = Form("auto"),
    letra: str = Form("normal"),
    red: str = Form("instagram"),
    comentario: str = Form(""),
    comentario_de: str = Form(""),
    plantilla: str = Form(""),
    directo: bool = Form(False),
):
    if (pack and pack not in packs.PACKS) or mode not in ("camara", "voz", "largo") \
            or background not in pipeline.BACKGROUNDS:
        raise HTTPException(400, "Opción no válida")
    copystyle.register()
    if rhythm not in RHYTHMS or (style != "auto" and style not in STYLES) or size not in ("1080", "4k") or fit not in ("recortar", "fondo"):
        raise HTTPException(400, "Opción no válida")
    allowed, watermark = license.can_edit(_refresh_license())
    if not allowed:
        raise HTTPException(402, "Has usado tus reels de prueba. Activa tu licencia en Ajustes para seguir editando.")
    if remember and instructions.strip():
        config.remember(instructions)
        instructions = ""  # ya va en las preferencias guardadas
    saved = "\n\n".join(p for p in (config.memory_prompt(config.load()), _learned_prompt()) if p)
    if saved:
        instructions = f"{saved}\n\n{instructions}".strip()
    if plantilla:
        form = plantillas.apply({}, plantilla)
        rhythm, style, fit, size = form.get("rhythm", rhythm), form.get("style", style), form.get("fit", fit), form.get("size", size)
        hook, gancho, pack = bool(form.get("hook", hook)), form.get("gancho", gancho), form.get("pack", pack)
        sfx, punch, barra = bool(form.get("sfx", sfx)), bool(form.get("punch", punch)), bool(form.get("barra", barra))
        transiciones, look, letra, red = bool(form.get("transiciones", transiciones)), form.get("look", look), form.get("letra", letra), form.get("red", red)
        if not background and mode == "camara":
            background = form.get("background", "") if form.get("background", "") in pipeline.BACKGROUNDS else ""
        if music_style == "auto" and music_file is None:
            music_style = form.get("music", "auto") if form.get("music", "auto") != "mia" else "auto"
        if pack and pack not in packs.PACKS:
            pack = ""
        if rhythm not in RHYTHMS or (style != "auto" and style not in STYLES) or size not in ("1080", "4k") or fit not in ("recortar", "fondo"):
            raise HTTPException(400, "Esa plantilla tiene una opción que ya no existe: bórrala y guárdala de nuevo")
    job_id = uuid.uuid4().hex[:10]
    workdir = JOBS_DIR / job_id
    workdir.mkdir(parents=True, exist_ok=True)
    takes = []
    try:
        for k, up in enumerate(video[:MAX_TAKES]):
            suffix = Path(up.filename or "video.mp4").suffix.lower()
            suffix = suffix if suffix in VIDEO_TYPES else ".mp4"
            take = workdir / (f"original{suffix}" if len(video) == 1 else f"toma-{k + 1:02d}{suffix}")
            _save_upload(up, take, MAX_VIDEO)
            takes.append(take)
        names = _save_broll(workdir, broll or [])
        if background == "foto":
            if not background_photo or not _save_background(workdir, _read_upload(background_photo, MAX_PHOTO)):
                background = ""  # sin foto válida, se queda el fondo de verdad
    except HTTPException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    src = takes[0] if len(takes) == 1 else workdir / "original.mp4"
    music = "mia" if music_file and _save_music(workdir, music_file) else \
        (music_style if music_style in musica.STYLES or music_style == "auto" else "")
    if names and mode == "camara":  # en "solo voz" los vídeos ya son la imagen de todo el reel
        instructions = f"{instructions}\n\n{pipeline.broll_prompt(names)}".strip()
    light = equipo.ligero(config.load().get("ligero", "auto"))
    if light:
        size = "1080"  # en un ordenador sencillo, el 4K tarda demasiado
    gancho = gancho if gancho in ganchos.GANCHOS else "auto"
    opts = pipeline.EditOptions(rhythm, style, size, fit, hook, hook_title, hook_template, gancho, instructions,
                                voice=voice, ruido=ruido, watermark=watermark, brand=use_brand, pack=pack,
                                mode="voz" if mode == "voz" else "camara", background=background,
                                sfx=sfx, music=music, punch=punch, barra=barra, transiciones=transiciones,
                                look=look if look in media.LOOKS or look == "auto" else "",
                                letra=letra if letra in captions_mod.SIZES else "normal",
                                red=red if red in redes.REDES else "instagram",
                                comentario=" ".join(comentario.split())[:140],
                                comentario_de=comentario_de.strip().lstrip("@")[:40], ligero=light,
                                gestures=not light, directo=bool(directo) and mode == "largo")
    if watermark:  # el reel de prueba se cuenta al crearlo (si falla, se devuelve)
        _count_trial(+1)
    with _lock:
        JOBS[job_id] = {"id": job_id, "status": "working", "step": "En cola", "progress": 0.0, "mode": mode,
                        "options": asdict(opts), "created": time.time(), "trial": watermark, "cliente": clientes.activo()}
    target = _work_long if mode == "largo" else _work
    if len(takes) > 1:
        threading.Thread(target=_join_then, args=(target, takes, job_id, src, workdir, opts), daemon=True).start()
    else:
        threading.Thread(target=target, args=(job_id, src, workdir, opts), daemon=True).start()
    return JOBS[job_id]


MAX_TAKES = 10


def _join_then(target, takes: list[Path], job_id: str, src: Path, workdir: Path, opts) -> None:
    """Varias tomas: se unen en orden con el color igualado a la primera y luego se edita como un vídeo."""
    try:
        _set(job_id, step=f"Uniendo tus {len(takes)} tomas e igualando el color", progress=0.02)
        media.join_takes(takes, src)
        for t in takes:
            t.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001
        log.exception("No se pudieron unir las tomas")
        (workdir / "error.log").write_text(str(e), encoding="utf-8")
        _set(job_id, status="error", error="No he podido unir tus tomas. Prueba con vídeos en mp4 o mov "
                                           "grabados con el móvil, o súbelos de uno en uno.")
        return
    target(job_id, src, workdir, opts)


def _work_long(job_id: str, src: Path, workdir: Path, opts: pipeline.EditOptions) -> None:
    """Vídeo largo → varios reels: cada momento elegido es un reel normal que aparece en la biblioteca."""
    try:
        cfg = config.load()
        words, picks = pipeline.long_video_clips(src, workdir, cfg,
                                                 lambda msg, pct: _set(job_id, step=msg, progress=pct * 0.3),
                                                 directo=opts.directo)
        if not picks:
            raise ValueError("No he encontrado momentos de al menos 12 segundos en los que hables")
        made = []
        for k, pick in enumerate(picks):
            _set(job_id, step=f"Editando el reel {k + 1} de {len(picks)}", progress=0.3 + 0.7 * k / len(picks))
            cid = uuid.uuid4().hex[:10]
            cdir = JOBS_DIR / cid
            csrc, sub = pipeline.clip_source(src, words, pick, cdir)
            for m in workdir.glob("musica.*"):  # cada reel del vídeo largo lleva tu música
                shutil.copy(m, cdir / m.name)
            copts = replace(opts, hook_title=opts.hook_title or pick["title"])
            with _lock:
                JOBS[cid] = {"id": cid, "status": "working", "step": "En cola", "progress": 0.0, "from_long": job_id,
                             "options": asdict(copts), "created": time.time(), "cliente": JOBS[job_id].get("cliente", "")}
            _work(cid, csrc, cdir, copts)
            if JOBS[cid]["status"] == "done":
                r = JOBS[cid]["result"]
                made.append({"id": cid, "title": r["plan"].get("hook_title", ""), "why": pick["why"],
                             "duration": r["duration_out"]})
        if not made:
            with _lock:
                errors = [j.get("error") for j in list(JOBS.values()) if j.get("from_long") == job_id and j.get("error")]
            raise ValueError(errors[0] if errors else "No he podido editar ningún reel")
        JOBS[job_id].pop("trial", None)
        _set(job_id, status="done", progress=1.0, result={"clips": made})
    except Exception as e:
        log.exception("Falla el vídeo largo %s", job_id)
        if JOBS[job_id].pop("trial", False):
            _count_trial(-1)
        _set(job_id, status="error", error=_friendly(e))


def _save_broll(workdir: Path, files: list[UploadFile]) -> list[str]:
    """Guarda los vídeos y fotos de apoyo como apoyo/01.mp4, 02.jpg… y devuelve sus nombres originales."""
    names = []
    for up in files[:12]:
        ext = Path(up.filename or "").suffix.lower()
        if not up.filename or ext not in effects.MEDIA_EXT:
            continue
        d = workdir / "apoyo"
        d.mkdir(exist_ok=True)
        _save_upload(up, d / f"{len(names) + 1:02d}{ext}", MAX_MEDIA)
        names.append(Path(up.filename).stem[:60])
    return names


def _work(job_id: str, src: Path, workdir: Path, opts: pipeline.EditOptions, plan=None) -> None:
    try:
        res = pipeline.run(src, workdir, opts, config.load(),
                           progress=lambda msg, pct: _set(job_id, step=msg, progress=pct), plan=plan)
        JOBS[job_id].pop("trial", None)
        _set(job_id, status="done", result=res.summary())
    except Exception as e:
        log.exception("Falla la edición de %s", job_id)
        try:
            (workdir / "error.log").write_text(f"{e}\n", encoding="utf-8")
        except OSError:
            pass
        prev = JOBS[job_id].get("result")
        if JOBS[job_id].pop("trial", False) and not prev:
            _count_trial(-1)
        if prev:
            # Un cambio que falla no se lleva el reel que ya estaba hecho.
            _set(job_id, status="done", error=None, options=JOBS[job_id].get("prev_options") or JOBS[job_id]["options"],
                 result={**prev, "notices": [f"No he podido aplicar el último cambio. {_friendly(e)}"]})
        else:
            _set(job_id, status="error", error=_friendly(e))


@app.post("/api/jobs/{job_id}/reedit")
def reedit(job_id: str, body: dict):
    """Vuelve a montar con otras opciones sin volver a transcribir."""
    job = _job(job_id)
    if not job or job["status"] == "working":
        raise HTTPException(404, "No encuentro ese reel o aún se está editando")
    workdir = JOBS_DIR / job_id
    src = _original(workdir)
    merged = {**job["options"], **_edit_fields(body)}
    opts = pipeline.EditOptions(**merged)
    _claim(job_id, step="Aplicando cambios", progress=0.0, options=asdict(opts), error=None)
    plan_file = workdir / "plan.json"
    saved = jsonfile.load(plan_file)  # si se guardó mal, se vuelve a planificar desde cero
    plan = EditPlan.from_dict(saved) if saved is not None else None
    if plan is not None and "hook_title" in body:
        plan.hook_title = body["hook_title"]
    threading.Thread(target=_work, args=(job_id, src, workdir, opts, plan), daemon=True).start()
    return JOBS[job_id]


def _edit_fields(body: dict) -> dict:
    """Solo las opciones que existen, con el tipo que toca (un texto donde iba un sí/no rompería el montaje)."""
    out = {}
    for f in fields(pipeline.EditOptions):
        if f.name not in body:
            continue
        v = body[f.name]
        if f.type in ("bool", bool):
            out[f.name] = bool(v)
        elif f.type in ("str", str):
            out[f.name] = str(v if v is not None else "")[:2000]
        elif f.type in ("int", int, "float", float) and isinstance(v, (int, float)) and math.isfinite(v):
            out[f.name] = v
    return out


class ChatIn(BaseModel):
    message: str = Field(..., max_length=2000)
    remember: bool = False


@app.post("/api/jobs/{job_id}/chat")
def chat(job_id: str, body: ChatIn):
    """"Dímelo como a tu editor": cambios en lenguaje natural sobre el reel ya montado."""
    job = _job(job_id)
    if not job or job["status"] == "working":
        raise HTTPException(404, "No encuentro ese reel o aún se está editando")
    aicfg = config.ai_config(config.load())
    if not aicfg.enabled:
        raise HTTPException(400, "Conecta Claude o ChatGPT en Ajustes para pedir cambios por chat")
    workdir = JOBS_DIR / job_id
    words = _saved_words(workdir)
    plan = _saved_plan(workdir)
    opts = pipeline.EditOptions(**job["options"])
    try:
        new_plan, settings, reply = ai.revise_plan(aicfg, words, plan, body.message, opts.rhythm,
                                                     opts.style if opts.style in STYLES else plan.caption_style)
    except Exception as e:
        raise HTTPException(502, f"La IA no ha podido aplicar el cambio. {ai.error_message(e)}")
    # Lo que el creador decidió a mano en "Revisa lo que dices" se mantiene.
    new_plan.cut, new_plan.restore = plan.cut, plan.restore
    if body.remember:
        config.remember(body.message)
    if settings.get("rhythm") in RHYTHMS:
        opts.rhythm = settings["rhythm"]
    if settings.get("style") in STYLES:
        opts.style = settings["style"]
    opts.hook_title = ""  # el gancho lo decide ahora el plan revisado
    history = job.get("chat", []) + [{"role": "user", "text": body.message}, {"role": "iman", "text": reply}]
    src = _original(workdir)
    _claim(job_id, step="Aplicando tus cambios", progress=0.0, options=asdict(opts),
         error=None, chat=history)
    threading.Thread(target=_work, args=(job_id, src, workdir, opts, new_plan), daemon=True).start()
    return JOBS[job_id]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = _job(job_id)
    if job is None:
        raise HTTPException(404, "No encuentro ese reel")
    if job.get("status") == "working":
        return {**job, "preview": (JOBS_DIR / job_id / "previa.mp4").exists()}
    return job


@app.get("/api/jobs/{job_id}/previa.mp4")
def get_preview(job_id: str):
    """Vista previa al instante: tu vídeo ya con los cortes, pequeño, mientras Imán monta el reel entero."""
    p = _dir(job_id) / "previa.mp4"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4")


class PhraseIn(BaseModel):
    start: int = Field(alias="from")
    to: int
    keep: bool


class PlanEditIn(BaseModel):
    effects_off: list[int] | None = None
    hook_title: str | None = None
    phrases: list[PhraseIn] | None = None


def _without(ranges, a: int, b: int) -> list[tuple[int, int]]:
    return [(x, y) for x, y in ranges if y < a or x > b]


@app.get("/api/jobs/{job_id}/review")
def review(job_id: str):
    """"Revisa lo que dices": cada frase, si se queda o se va, y por qué.

    Mientras se edita por primera vez ya responde en cuanto Imán te ha escuchado (`draft`: aún sin las
    decisiones del director, solo silencios, repeticiones y muletillas); antes, una lista vacía."""
    job = _job(job_id)
    workdir = JOBS_DIR / job_id
    if not job:
        raise HTTPException(404, "No encuentro ese reel")
    draft = not (workdir / "plan.json").exists()
    if draft and (job["status"] != "working" or jsonfile.load(workdir / "transcript.json") is None):
        if job["status"] != "working":
            raise HTTPException(404, "No encuentro ese reel")
        return {"phrases": [], "draft": True}
    words = _saved_words(workdir)
    plan = EditPlan() if draft else _saved_plan(workdir)
    return {"phrases": pipeline.review(words, plan, job["options"]["rhythm"]), "draft": draft}


@app.post("/api/jobs/{job_id}/plan")
def edit_plan(job_id: str, body: PlanEditIn):
    """Encender o apagar efectos del plan y cambiar el gancho, sin pasar por la IA."""
    job = _job(job_id)
    if not job or job["status"] == "working":
        raise HTTPException(404, "No encuentro ese reel o aún se está editando")
    workdir = JOBS_DIR / job_id
    plan = _saved_plan(workdir)
    if body.effects_off is not None:
        off = set(body.effects_off)
        plan.effects = [{**fx, "off": i in off} for i, fx in enumerate(plan.effects)]
    for ph in body.phrases or []:
        a, b = ph.start, ph.to
        if not 0 <= a <= b:
            continue
        plan.cut, plan.restore = _without(plan.cut, a, b), _without(plan.restore, a, b)
        (plan.restore if ph.keep else plan.cut).append((a, b))
    opts = pipeline.EditOptions(**job["options"])
    if body.hook_title is not None:
        plan.hook_title = body.hook_title.strip()[:80]
        opts.hook_title = plan.hook_title
        opts.hook = bool(plan.hook_title)
    src = _original(workdir)
    _claim(job_id, step="Aplicando cambios", progress=0.0, options=asdict(opts), error=None)
    threading.Thread(target=_work, args=(job_id, src, workdir, opts, plan), daemon=True).start()
    return JOBS[job_id]


@app.post("/api/jobs/{job_id}/guia")
def make_guide(job_id: str, nuevo: bool = False):
    """Guía en PDF sacada del vídeo, para regalarla a cambio de un contacto («escríbeme GUÍA y te la mando»)."""
    from . import guia

    job = _done_job(job_id)
    workdir = JOBS_DIR / job_id
    pdf, meta = workdir / "guia.pdf", workdir / "guia.json"
    if pdf.exists() and not nuevo and (saved := jsonfile.load(meta)):
        return saved
    words = _saved_words(workdir)
    b = brand.load()
    hook = job["result"]["plan"].get("hook_title", "")
    pack = job["options"].get("pack", "") or b.sector
    data, used_ai = None, False
    aicfg = config.ai_config(config.load())
    if aicfg.enabled and words:
        try:
            data = ai.guide_copy(aicfg, " ".join(w.text for w in words), hook, pack,
                                 " — ".join(x for x in (b.name, b.description) if x), b.contact, b.cta, b.copy_prompt())
            used_ai = True
        except Exception as e:  # noqa: BLE001 - sin IA, la guía sale de tus frases
            log.warning("guía sin IA: %s", e)
    if not data or not data.get("sections"):
        data = guia.fallback(words, hook, b.cta)
    reel = workdir / "reel.mp4"
    dur = media.probe(reel).duration
    frames = [media.thumbnail(reel, workdir / f"guia-{k}.jpg", dur * f) for k, f in enumerate((0.3, 0.65))]
    try:
        guia.render(data, pdf, frames, b)
    finally:
        for f in frames:
            f.unlink(missing_ok=True)
    out = {"title": data.get("title", ""), "sections": len(data.get("sections") or []), "ai": used_ai,
           "url": f"/api/jobs/{job_id}/guia.pdf"}
    jsonfile.save(meta, out)
    return out


@app.get("/api/jobs/{job_id}/guia.pdf")
def get_guide(job_id: str):
    p = _dir(job_id) / "guia.pdf"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="application/pdf", filename=f"guia-{job_id}.pdf")


@app.post("/api/jobs/{job_id}/post")
def post_copy(job_id: str, nuevo: bool = False):
    """Texto de la publicación y hashtags, escritos por la IA con lo que dices en el vídeo."""
    job = _done_job(job_id)
    workdir = JOBS_DIR / job_id
    cached = workdir / "post-redes.json"
    if not nuevo and (saved := jsonfile.load(cached)):
        return saved
    aicfg = config.ai_config(config.load())
    if not aicfg.enabled:
        raise HTTPException(400, "Activa la IA en Ajustes para que te escriba el texto de la publicación")
    words = _saved_words(workdir)
    b = brand.load()
    try:
        data = ai.post_copy(aicfg, " ".join(w.text for w in words), job["result"]["plan"].get("hook_title", ""),
                            job["options"].get("pack", "") or b.sector, b.cta, b.handle, b.description, b.contact,
                            b.name, b.copy_prompt())
    except Exception as e:
        raise HTTPException(502, f"La IA no ha podido escribir el texto. {ai.error_message(e)}")
    if b.no_emojis:
        for d in data["platforms"].values():
            d["text"], d["title"] = brand.strip_emojis(d["text"]), brand.strip_emojis(d.get("title", ""))
        data["caption"] = brand.strip_emojis(data.get("caption", ""))
    cached.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


class KitIn(BaseModel):
    message: str = ""
    cover_t: float | None = None


@app.post("/api/jobs/{job_id}/kit")
def make_kit(job_id: str, body: KitIn):
    """Portada, carrusel e historias del reel, con tu marca. Con `message` se cambia algo con una frase."""
    from . import kit, media

    job = _job(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "No encuentro ese reel")
    workdir = JOBS_DIR / job_id
    outdir = workdir / "kit"
    words = _saved_words(workdir)
    hook = job["result"]["plan"].get("hook_title", "")
    b = brand.load()
    current = json.loads((outdir / "kit.json").read_text(encoding="utf-8")) if (outdir / "kit.json").exists() else None
    aicfg = config.ai_config(config.load())
    if body.message.strip() and not aicfg.enabled:
        raise HTTPException(400, "Activa la IA en Ajustes para cambiar el carrusel con una frase")
    if aicfg.enabled:
        try:
            data = ai.kit_copy(aicfg, " ".join(w.text for w in words), hook, job["options"].get("pack", ""), b.cta,
                               current, body.message)
        except Exception as e:
            raise HTTPException(502, f"La IA no ha podido preparar el carrusel. {ai.error_message(e)}")
    else:
        data = kit.fallback(words, hook, b.cta)
    # Fotogramas limpios (sin subtítulos) de la toma original: la portada y unos cuantos más.
    src = workdir / "lienzo.mp4" if (workdir / "lienzo.mp4").exists() else _original(workdir)
    dur = float(job["result"]["duration_in"])
    first = words[0].start if words else 0.5
    t0 = body.cover_t if body.cover_t is not None else first + 0.4
    frames = [media.thumbnail(src, workdir / f"kit-frame-{k}.jpg", max(0.0, min(t, dur - 0.1))) if k == 0 else
              _sharpest(src, workdir, k, t, dur)
              for k, t in enumerate([t0, dur * 0.25, dur * 0.45, dur * 0.65, dur * 0.85])]
    names = kit.render(data, outdir, b, frames)
    return {**names, "reply": data.get("reply", ""), "version": int(time.time())}


def _sharpest(src: Path, workdir: Path, k: int, t: float, dur: float) -> Path:
    """De tres fotogramas seguidos, el más nítido (sin movimiento ni media palabra borrosa)."""
    from PIL import Image, ImageFilter, ImageStat

    best, score = None, -1.0
    for j, dt in enumerate((-0.3, 0.0, 0.3)):
        p = media.thumbnail(src, workdir / f"kit-frame-{k}-{j}.jpg", max(0.0, min(t + dt, dur - 0.1)))
        with Image.open(p) as im:
            sc = ImageStat.Stat(im.convert("L").resize((270, 480)).filter(ImageFilter.FIND_EDGES)).var[0]
        if sc > score:
            best, score = p, sc
    out = workdir / f"kit-frame-{k}.jpg"
    shutil.copyfile(best, out)
    return out


@app.get("/api/jobs/{job_id}/kit/{name}")
def kit_file(job_id: str, name: str):
    p = _child(_dir(job_id) / "kit", name)
    media = "application/zip" if name.endswith(".zip") else "image/png"
    return FileResponse(p, media_type=media, filename=f"{job_id}-{name}" if name.endswith(".zip") else None)


@app.post("/api/jobs/{job_id}/portadas")
def make_covers(job_id: str):
    """Tres portadas tipo YouTube (tú recortado, luz de borde, texto grande), en vertical y en horizontal."""
    from . import miniaturas

    job = _done_job(job_id)
    workdir = JOBS_DIR / job_id
    src = workdir / "lienzo.mp4" if (workdir / "lienzo.mp4").exists() else _original(workdir)
    dur = float(job["result"]["duration_in"])
    frames = [media.thumbnail(src, workdir / f"portada-frame-{k}.jpg", max(0.0, min(dur * f, dur - 0.1)))
              for k, f in enumerate((0.08, 0.2, 0.32, 0.45, 0.58, 0.7, 0.85))]
    b = brand.load()
    accent = b.primary if brand.is_hex(b.primary or "") else "#FF5547"
    title = job["result"]["plan"].get("hook_title", "") or "Mira esto"
    outdir = workdir / "portadas"
    for old in outdir.glob("*.jpg"):
        old.unlink()
    names = miniaturas.render_all(frames, title, outdir, accent, b.secondary or "",
                                  brand.font_family(b.font) or "Anton")
    for f in frames:
        f.unlink(missing_ok=True)
    return {"files": names, "variants": miniaturas.VARIANTS, "version": int(time.time())}


@app.get("/api/jobs/{job_id}/portadas/{name}")
def cover_file(job_id: str, name: str):
    return FileResponse(_child(_dir(job_id) / "portadas", name), media_type="image/jpeg")


PHOTOS_DIR = config.HOME / "fotos"


@app.post("/api/imagen")
def photo_tool(foto: UploadFile = File(...), accion: str = Form("mejorar"), luz: str = Form("estudio"),
               lado: str = Form("izquierda")):
    """Herramientas de foto: quitar el fondo (PNG transparente), mejorar o reiluminar."""
    from . import imagen

    if accion not in ("fondo", "mejorar", "luz"):
        raise HTTPException(400, "Herramienta desconocida")
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    raw = foto.file.read()
    if len(raw) > 40 * 1024 * 1024:
        raise HTTPException(413, "La foto es demasiado grande (máx. 40 MB)")
    try:
        img = imagen.load(io.BytesIO(raw))
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "No puedo abrir esa imagen. Prueba con un JPG o PNG.") from None
    try:
        if accion == "fondo":
            out = imagen.quitar_fondo(img)
        elif accion == "luz":
            out = imagen.reiluminar(img, luz if luz in imagen.LIGHTS else "estudio",
                                    "derecha" if lado == "derecha" else "izquierda")
        else:
            out = imagen.mejorar(img)
    except imagen.NoPerson as e:
        raise HTTPException(422, str(e)) from None
    stem = Path(foto.filename or "foto").stem[:40] or "foto"
    stem = "".join(c if c.isalnum() or c in "-_" else "-" for c in stem)
    png = out.mode == "RGBA"
    name = f"{stem}-{accion}-{uuid.uuid4().hex[:6]}.{'png' if png else 'jpg'}"
    if png:
        out.save(PHOTOS_DIR / name)
    else:
        out.convert("RGB").save(PHOTOS_DIR / name, quality=93)
    return {"name": name, "url": f"/api/imagen/{name}", "width": out.width, "height": out.height}


@app.get("/api/imagen/{name}")
def photo_file(name: str):
    p = _child(PHOTOS_DIR, name)
    return FileResponse(p, media_type="image/png" if name.endswith(".png") else "image/jpeg", filename=name)


@app.get("/api/jobs/{job_id}/cover.jpg")
def get_cover(job_id: str, t: float = 0.5):
    """Fotograma del reel para usarlo de portada."""
    p = _dir(job_id) / "reel.mp4"
    if not p.exists():
        raise HTTPException(404)
    t = max(0.0, min(t, 3600.0)) if math.isfinite(t) else 0.5
    out = JOBS_DIR / job_id / f"cover-{int(t * 10)}.jpg"
    with _lock_for(out):
        if not out.exists():
            media.thumbnail(p, out, t)
    return FileResponse(out, media_type="image/jpeg", filename=f"portada-{job_id}.jpg")


@app.get("/api/jobs/{job_id}/reel.mp4")
def get_video(job_id: str):
    p = _dir(job_id) / "reel.mp4"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4", filename=f"reel-{job_id}.mp4")


@app.get("/api/jobs/{job_id}/sin-silencios.mp4")
def get_rough(job_id: str):
    """Pestaña «Sin silencios»: tu vídeo solo con los cortes, para revisar lo que se queda."""
    workdir = _dir(job_id)
    dst = workdir / "sin-silencios.mp4"
    if not dst.exists():
        spans = jsonfile.load(workdir / "tramos.json")
        src = next(workdir.glob("original.*"), None)
        if not spans or src is None:
            raise HTTPException(404)
        with _lock_for(dst):
            if not dst.exists():
                media.rough_cut(src, [tuple(s) for s in spans], dst)
    return FileResponse(dst, media_type="video/mp4")


@app.get("/api/jobs/{job_id}/original")
def get_original(job_id: str):
    """Pestaña «Vídeo original»: lo que subiste, tal cual."""
    src = next(_dir(job_id).glob("original.*"), None)
    if src is None:
        raise HTTPException(404)
    return FileResponse(src, media_type="video/quicktime" if src.suffix.lower() == ".mov" else "video/mp4")


VERSIONS: dict[str, dict] = {}
MAX_VERSIONS = 6


class VersionsIn(BaseModel):
    hooks: list[str] = Field(default_factory=list)
    ctas: list[str] = Field(default_factory=list)


def _version_plan(plan: EditPlan, hook: str, cta: str, n_words: int) -> EditPlan:
    p = EditPlan.from_dict(plan.to_dict())
    p.hook_title = hook or p.hook_title
    if cta:
        ctas = [fx for fx in p.effects if fx.get("type") == "cta"]
        for fx in ctas:
            fx["text"] = cta
        if not ctas:
            p.effects.append({"type": "cta", "word": max(0, n_words - 8), "text": cta, "subtitle": "", "title": "",
                              "look": "", "until_word": None})
    return p


def _make_versions(job_id: str, combos: list[tuple[str, str]]) -> None:
    import os
    import zipfile

    workdir = JOBS_DIR / job_id
    state = VERSIONS[job_id]
    try:
        words = _saved_words(workdir)
        plan = _saved_plan(workdir)
        src = _original(workdir)
        opts = pipeline.EditOptions(**JOBS[job_id]["options"])
        outdir = workdir / "versiones"
        shutil.rmtree(outdir, ignore_errors=True)
        outdir.mkdir()
        files = []
        for k, (hook, cta) in enumerate(combos, 1):
            vdir = outdir / f"v{k}"
            vdir.mkdir()
            # Lo que el montaje lee de la carpeta del reel (apoyo, música, fondo…), sin copiar vídeos grandes.
            for p in [workdir / "apoyo", workdir / "fondo.jpg", workdir / "manos.json", workdir / "lienzo.mp4",
                      *workdir.glob("musica.*")]:
                if not p.exists():
                    continue
                if p.is_dir():
                    shutil.copytree(p, vdir / p.name, copy_function=_link_or_copy)
                else:
                    _link_or_copy(p, vdir / p.name)
            vopts = replace(opts, hook_title=hook or opts.hook_title)
            pipeline.run(src, vdir, vopts, config.load(), words=words, plan=_version_plan(plan, hook, cta, len(words)))
            name = f"version-{k}.mp4"
            os.replace(vdir / "reel.mp4", outdir / name)
            shutil.rmtree(vdir, ignore_errors=True)
            files.append({"name": name, "hook": hook, "cta": cta})
            state.update(done=k, files=list(files))
        with zipfile.ZipFile(outdir / "versiones.zip", "w") as z:
            for f in files:
                z.write(outdir / f["name"], f["name"])
            z.writestr("versiones.txt", "\n".join(f"{f['name']}: gancho «{f['hook']}»" + (f", llamada «{f['cta']}»"
                                                                                       if f["cta"] else "")
                                                for f in files))
        state.update(status="done")
    except Exception as e:  # noqa: BLE001
        log.exception("Fallan las versiones de %s", job_id)
        state.update(status="error", error=_friendly(e))


def _link_or_copy(a, b):
    import os

    try:
        os.link(a, b)
    except OSError:
        shutil.copy2(a, b)
    return b


@app.post("/api/jobs/{job_id}/versiones")
def make_versions(job_id: str, body: VersionsIn):
    """Varias versiones del mismo reel (para probar anuncios): cambia el gancho y la llamada a la acción."""
    job = _job(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "No encuentro ese reel o aún se está editando")
    if VERSIONS.get(job_id, {}).get("status") == "working":
        raise HTTPException(409, "Ya estoy haciendo las versiones de este reel")
    hooks = [" ".join(h.split())[:80] for h in body.hooks if h.strip()][:MAX_VERSIONS] or [""]
    ctas = [" ".join(c.split())[:40] for c in body.ctas if c.strip()][:3] or [""]
    combos = [(h, c) for h in hooks for c in ctas][:MAX_VERSIONS]
    if len(combos) < 2:
        raise HTTPException(400, "Escribe al menos dos ganchos o dos llamadas a la acción distintas")
    VERSIONS[job_id] = {"status": "working", "done": 0, "total": len(combos), "files": [], "error": None}
    threading.Thread(target=_make_versions, args=(job_id, combos), daemon=True).start()
    return VERSIONS[job_id]


@app.get("/api/jobs/{job_id}/versiones")
def versions_state(job_id: str):
    return VERSIONS.get(job_id) or {"status": "none", "done": 0, "total": 0, "files": [], "error": None}


@app.get("/api/jobs/{job_id}/versiones/{name}")
def version_file(job_id: str, name: str):
    p = _child(_dir(job_id) / "versiones", name)
    media_type = "application/zip" if name.endswith(".zip") else "video/mp4"
    return FileResponse(p, media_type=media_type, filename=f"reel-{job_id}-{name}")


CASCADES: dict[str, dict] = {}


def _make_cascade(job_id: str) -> None:
    from . import cascada

    workdir = JOBS_DIR / job_id
    state = CASCADES[job_id]
    try:
        src = _original(workdir)
        res = cascada.render(src, _saved_words(workdir), workdir / "cascada", config.load(),
                             lambda msg, pct: state.update(step=msg, progress=pct))
        state.update(status="done", progress=1.0, result=res)
    except Exception as e:  # noqa: BLE001
        log.exception("Falla la cascada de %s", job_id)
        state.update(status="error", error=_friendly(e))


@app.post("/api/jobs/{job_id}/cascada")
def make_cascade(job_id: str):
    """Método cascada: del vídeo largo, el vídeo limpio, el podcast, el carrusel de citas y la newsletter."""
    job = _job(job_id)
    if not job or job["status"] != "done" or not (JOBS_DIR / job_id / "transcript.json").exists():
        raise HTTPException(404, "No encuentro ese vídeo")
    if CASCADES.get(job_id, {}).get("status") == "working":
        raise HTTPException(409, "Ya lo estoy preparando")
    CASCADES[job_id] = {"status": "working", "step": "Empezando", "progress": 0.0, "result": None, "error": None}
    threading.Thread(target=_make_cascade, args=(job_id,), daemon=True).start()
    return CASCADES[job_id]


@app.get("/api/jobs/{job_id}/cascada")
def cascade_state(job_id: str):
    if job_id not in CASCADES and (_dir(job_id) / "cascada" / "cascada.zip").exists():
        return {"status": "done", "step": "", "progress": 1.0, "result": None, "error": None}
    return CASCADES.get(job_id) or {"status": "none", "step": "", "progress": 0.0, "result": None, "error": None}


@app.get("/api/jobs/{job_id}/cascada/{name:path}")
def cascade_file(job_id: str, name: str):
    base = _dir(job_id) / "cascada"
    parts = name.split("/")
    p = _child(base.joinpath(*parts[:-1]), parts[-1]) if all(parts) else None
    if p is None or any(".." in q or q.startswith(".") for q in parts):
        raise HTTPException(404)
    kinds = {".zip": "application/zip", ".mp4": "video/mp4", ".mp3": "audio/mpeg", ".png": "image/png",
             ".txt": "text/plain; charset=utf-8"}
    return FileResponse(p, media_type=kinds.get(p.suffix, "application/octet-stream"),
                        filename=f"{job_id}-{p.name}" if p.suffix != ".png" else None)


def _reveal(p: Path) -> None:
    """Abre la carpeta en el explorador con el archivo marcado."""
    import platform

    system = platform.system()
    cmd = (["explorer", f"/select,{p}"] if system == "Windows" else ["open", "-R", str(p)] if system == "Darwin"
           else ["xdg-open", str(p.parent if p.is_file() else p)])
    try:
        subprocess.Popen(cmd)
    except OSError:
        raise HTTPException(500, f"No he podido abrir la carpeta. Está en {p}") from None


@app.post("/api/jobs/{job_id}/mostrar")
def show_in_folder(job_id: str):
    """Abre la carpeta del reel con el vídeo marcado, para arrastrarlo a la red que quieras."""
    p = _dir(job_id) / "reel.mp4"
    if not p.exists():
        raise HTTPException(404, "No encuentro ese reel")
    _reveal(p)
    return {"ok": True, "path": str(p)}


@app.get("/api/soporte")
def support_info():
    """Lo que hace falta para contar un fallo: versión, sistema, reels hechos y el último error."""
    import platform

    from . import __version__

    errors = sorted(JOBS_DIR.glob("*/error.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    last = ""
    if errors:
        last = errors[0].read_text(encoding="utf-8", errors="replace").strip().splitlines()
        last = (last[-1] if last else "")[:300]
    reels = sum(1 for _ in JOBS_DIR.glob("*/reel.mp4")) if JOBS_DIR.exists() else 0
    cfg = config.load()
    return {"version": __version__, "system": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "reels": reels, "last_error": last, "feedback_url": cfg.get("feedback_url", ""),
            "plan": license.status(cfg).get("plan_label", "") or "Prueba"}


@app.post("/api/soporte/registros")
def open_logs():
    """Abre la carpeta de Imán con el registro marcado, para mandarlo si algo falla."""
    log_file = config.HOME / "registro.txt"
    config.HOME.mkdir(parents=True, exist_ok=True)
    _reveal(log_file if log_file.exists() else config.HOME)
    return {"ok": True, "path": str(log_file)}


@app.get("/api/jobs/{job_id}/whatsapp.mp4")
def get_whatsapp_video(job_id: str):
    """El reel ligero para enviarlo por WhatsApp (a un grupo o a la lista de difusión) sin que lo destroce."""
    workdir = _dir(job_id)
    p = workdir / "reel.mp4"
    if not p.exists():
        raise HTTPException(404)
    out = workdir / "whatsapp.mp4"
    with _lock_for(out):
        if not out.exists() or out.stat().st_mtime < p.stat().st_mtime:
            tmp = workdir / "whatsapp.tmp.mp4"
            subprocess.run([media.FFMPEG, "-v", "error", "-y", "-i", str(p), "-vf", "scale=720:-2", "-c:v", "libx264",
                            "-preset", "veryfast", "-crf", "24", "-maxrate", "2500k", "-bufsize", "5000k",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(tmp)],
                           check=True)
            tmp.replace(out)
    return FileResponse(out, media_type="video/mp4", filename=f"reel-{job_id}-whatsapp.mp4")


@app.get("/api/jobs/{job_id}/whatsapp.zip")
def get_whatsapp(job_id: str):
    """El reel en trozos de menos de 60 s (los estados de WhatsApp cortan ahí), partido entre frases."""
    import zipfile

    workdir = _dir(job_id)
    p = workdir / "reel.mp4"
    if not p.exists():
        raise HTTPException(404)
    out = workdir / "whatsapp.zip"
    with _lock_for(out):
        if not out.exists() or out.stat().st_mtime < p.stat().st_mtime:
            dur = media.probe(p).duration
            marks = [0.0, *media.split_points(dur, media.silences(p)), dur]
            parts = []
            for k, (a, b) in enumerate(zip(marks, marks[1:])):
                parts.append(media.cut(p, workdir / f"estado-{k + 1}.mp4", a, b))
            tmp = out.with_suffix(".tmp")
            with zipfile.ZipFile(tmp, "w") as z:
                for k, part in enumerate(parts):
                    z.write(part, f"estado-{k + 1}-de-{len(parts)}.mp4")
                    part.unlink(missing_ok=True)
            tmp.replace(out)
    return FileResponse(out, media_type="application/zip", filename=f"reel-{job_id}-estados-whatsapp.zip")


@app.get("/api/jobs/{job_id}/reel.jpg")
def get_thumb(job_id: str):
    p = _dir(job_id) / "reel.jpg"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg")


app.mount("/fonts", StaticFiles(directory=Path(__file__).parent / "assets" / "fonts"), name="fonts")
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
