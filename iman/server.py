"""Servidor web local: `iman web` y abre http://localhost:8765"""

from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, config, license, pipeline
from .captions import STYLES
from .models import EditPlan, Word
from .rhythm import RHYTHMS

WEB = Path(__file__).parent / "web"
JOBS_DIR = config.HOME / "jobs"

app = FastAPI(title="Imán")
JOBS: dict[str, dict] = {}
_lock = threading.Lock()


def _set(job_id: str, **kw) -> None:
    with _lock:
        JOBS[job_id].update(kw)


@app.get("/api/options")
def options():
    return {
        "rhythms": [{"key": r.key, "label": r.label, "description": r.description} for r in RHYTHMS.values()],
        "styles": [{"key": s.key, "label": s.label} for s in STYLES.values()],
        "hook_templates": HOOK_TEMPLATES,
    }


HOOK_TEMPLATES = [
    "El error que comete el 90% cuando…",
    "Nadie te cuenta esto sobre…",
    "Deja de hacer X si quieres Y",
    "Así conseguí X en Y días",
    "3 cosas que ojalá hubiera sabido antes de…",
    "Si haces esto, estás perdiendo dinero",
]


@app.get("/api/settings")
def get_settings():
    return config.public(config.load())


class SettingsIn(BaseModel):
    provider: str | None = None
    anthropic_key: str | None = None
    openai_key: str | None = None
    transcriber: str | None = None
    whisper_model: str | None = None
    language: str | None = None


@app.post("/api/settings")
def set_settings(body: SettingsIn):
    data = {k: v for k, v in body.model_dump().items() if v is not None and v != ""}
    return config.public(config.save(data))


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


def _voice_samples() -> str:
    """Transcripciones de reels anteriores, para que las ideas suenen a ti."""
    texts = []
    for t in sorted(JOBS_DIR.glob("*/transcript.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
        texts.append(" ".join(w["text"] for w in json.loads(t.read_text())))
    return "\n---\n".join(texts)


@app.post("/api/jobs")
async def create_job(
    video: UploadFile = File(...),
    rhythm: str = Form("rapido"),
    style: str = Form("impacto"),
    size: str = Form("1080"),
    fit: str = Form("recortar"),
    hook: bool = Form(True),
    hook_title: str = Form(""),
    hook_template: str = Form(""),
    instructions: str = Form(""),
    voice: bool = Form(True),
):
    if rhythm not in RHYTHMS or style not in STYLES or size not in ("1080", "4k") or fit not in ("recortar", "fondo"):
        raise HTTPException(400, "Opción no válida")
    allowed, watermark = license.can_edit(_refresh_license())
    if not allowed:
        raise HTTPException(402, "Has usado tus reels de prueba. Activa tu licencia en Ajustes para seguir editando.")
    job_id = uuid.uuid4().hex[:10]
    workdir = JOBS_DIR / job_id
    workdir.mkdir(parents=True, exist_ok=True)
    suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
    src = workdir / f"original{suffix}"
    with src.open("wb") as f:
        shutil.copyfileobj(video.file, f)
    opts = pipeline.EditOptions(rhythm, style, size, fit, hook, hook_title, hook_template, instructions,
                                voice=voice, watermark=watermark)
    JOBS[job_id] = {"id": job_id, "status": "working", "step": "En cola", "progress": 0.0,
                    "options": asdict(opts), "created": time.time(), "trial": watermark}
    threading.Thread(target=_work, args=(job_id, src, workdir, opts), daemon=True).start()
    return JOBS[job_id]


def _work(job_id: str, src: Path, workdir: Path, opts: pipeline.EditOptions, plan=None) -> None:
    try:
        res = pipeline.run(src, workdir, opts, config.load(),
                           progress=lambda msg, pct: _set(job_id, step=msg, progress=pct), plan=plan)
        if JOBS[job_id].pop("trial", False):
            cfg = config.load()
            config.save({"free_reels_used": int(cfg.get("free_reels_used") or 0) + 1})
        _set(job_id, status="done", result=res.summary())
    except Exception as e:
        _set(job_id, status="error", error=str(e))


@app.post("/api/jobs/{job_id}/reedit")
def reedit(job_id: str, body: dict):
    """Vuelve a montar con otras opciones sin volver a transcribir."""
    job = JOBS.get(job_id)
    if not job or job["status"] == "working":
        raise HTTPException(404, "No encuentro ese reel o aún se está editando")
    workdir = JOBS_DIR / job_id
    src = next(workdir.glob("original.*"))
    merged = {**job["options"], **{k: v for k, v in body.items() if k in job["options"]}}
    opts = pipeline.EditOptions(**merged)
    _set(job_id, status="working", step="Aplicando cambios", progress=0.0, options=asdict(opts), error=None)
    plan_file = workdir / "plan.json"
    plan = EditPlan.from_dict(json.loads(plan_file.read_text())) if plan_file.exists() else None
    if plan is not None and "hook_title" in body:
        plan.hook_title = body["hook_title"]
    threading.Thread(target=_work, args=(job_id, src, workdir, opts, plan), daemon=True).start()
    return JOBS[job_id]


class ChatIn(BaseModel):
    message: str


@app.post("/api/jobs/{job_id}/chat")
def chat(job_id: str, body: ChatIn):
    """"Dímelo como a tu editor": cambios en lenguaje natural sobre el reel ya montado."""
    job = JOBS.get(job_id)
    if not job or job["status"] == "working":
        raise HTTPException(404, "No encuentro ese reel o aún se está editando")
    aicfg = config.ai_config(config.load())
    if not aicfg.enabled:
        raise HTTPException(400, "Conecta Claude o ChatGPT en Ajustes para pedir cambios por chat")
    workdir = JOBS_DIR / job_id
    words = [Word(**w) for w in json.loads((workdir / "transcript.json").read_text())]
    plan = EditPlan.from_dict(json.loads((workdir / "plan.json").read_text()))
    opts = pipeline.EditOptions(**job["options"])
    try:
        new_plan, settings, reply = ai.revise_plan(aicfg, words, plan, body.message, opts.rhythm, opts.style)
    except Exception as e:
        raise HTTPException(502, f"La IA no ha podido aplicar el cambio: {e}")
    if settings.get("rhythm") in RHYTHMS:
        opts.rhythm = settings["rhythm"]
    if settings.get("style") in STYLES:
        opts.style = settings["style"]
    opts.hook_title = ""  # el gancho lo decide ahora el plan revisado
    history = job.get("chat", []) + [{"role": "user", "text": body.message}, {"role": "iman", "text": reply}]
    _set(job_id, status="working", step="Aplicando tus cambios", progress=0.0, options=asdict(opts),
         error=None, chat=history)
    src = next(workdir.glob("original.*"))
    threading.Thread(target=_work, args=(job_id, src, workdir, opts, new_plan), daemon=True).start()
    return JOBS[job_id]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "No encuentro ese reel")
    return JOBS[job_id]


@app.get("/api/jobs/{job_id}/reel.mp4")
def get_video(job_id: str):
    p = JOBS_DIR / job_id / "reel.mp4"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4", filename=f"reel-{job_id}.mp4")


@app.get("/api/jobs/{job_id}/reel.jpg")
def get_thumb(job_id: str):
    p = JOBS_DIR / job_id / "reel.jpg"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg")


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
