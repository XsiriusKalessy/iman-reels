"""Servidor de la IA incluida en la licencia de Imán.

La app de escritorio le manda la transcripción (nunca el vídeo) y él llama a
Claude con la clave de Imán. Comprueba la licencia en Lemon Squeezy y limita
el uso diario por licencia para que nadie lo use como proxy gratis.

Arranque:  ANTHROPIC_API_KEY=... IMAN_LEMON_PRODUCT_ID=... uvicorn iman_cloud.app:app
"""

from __future__ import annotations

import os
import threading
import time
from datetime import date

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from iman import ai, license
from iman.models import EditPlan, Word

DAILY_LIMIT = int(os.environ.get("IMAN_DAILY_LIMIT", "40"))
TRIAL_LIMIT = int(os.environ.get("IMAN_TRIAL_LIMIT", "6"))  # llamadas al día sin licencia, por IP
MAX_WORDS = 4000  # unos 25 minutos hablando

app = FastAPI(title="Imán Cloud")
_lock = threading.Lock()
_valid_until: dict[str, float] = {}
_usage: dict[tuple[str, str], int] = {}


def _cfg() -> ai.AIConfig:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(503, "Servidor sin configurar")
    return ai.AIConfig(provider="claude", anthropic_key=key,
                       claude_model=os.environ.get("IMAN_CLAUDE_MODEL", ai.CLAUDE_MODEL))


def _count(bucket: str, limit: int, msg: str) -> None:
    with _lock:
        k = (bucket, date.today().isoformat())
        _usage[k] = _usage.get(k, 0) + 1
        if _usage[k] > limit:
            raise HTTPException(429, msg)


def _check(key: str, instance: str, request: Request) -> None:
    if not key:
        # Prueba gratis: unas pocas ediciones al día por IP para que se vea la IA en acción.
        ip = request.headers.get("fly-client-ip") or (request.client.host if request.client else "?")
        _count("trial:" + ip, TRIAL_LIMIT, "Has agotado la prueba gratis de hoy. Activa tu licencia para seguir.")
        return
    now = time.time()
    if _valid_until.get(key, 0) < now:
        res = license.validate({"license_key": key, "license_instance": instance, "license_checked": 0})
        if not res.get("license_valid"):
            raise HTTPException(403, "Licencia no válida o caducada")
        _valid_until[key] = now + 3600
    _count(key, DAILY_LIMIT, f"Has llegado al límite de {DAILY_LIMIT} ediciones con IA por hoy")


def _words(raw: list[dict]) -> list[Word]:
    if len(raw) > MAX_WORDS:
        raise HTTPException(413, "El vídeo es demasiado largo para editarlo de una vez")
    return [Word(str(w["text"])[:40], float(w["start"]), float(w["end"])) for w in raw]


class PlanIn(BaseModel):
    words: list[dict]
    instructions: str = Field("", max_length=2000)
    hook_template: str = Field("", max_length=200)
    pack: str = Field("", max_length=20)


class ReviseIn(BaseModel):
    words: list[dict]
    plan: dict
    message: str = Field(..., max_length=2000)
    rhythm: str = "rapido"
    style: str = "impacto"


class IdeasIn(BaseModel):
    topic: str = Field(..., max_length=500)
    audience: str = Field("", max_length=300)
    voice_samples: str = Field("", max_length=6000)
    n: int = Field(3, ge=1, le=5)


@app.post("/v1/plan")
def plan(request: Request, body: PlanIn, x_iman_license: str = Header(""), x_iman_instance: str = Header("")):
    _check(x_iman_license, x_iman_instance, request)
    return ai.plan_edit_raw(_cfg(), _words(body.words), body.instructions, body.hook_template, body.pack)


@app.post("/v1/revise")
def revise(request: Request, body: ReviseIn, x_iman_license: str = Header(""), x_iman_instance: str = Header("")):
    _check(x_iman_license, x_iman_instance, request)
    return ai.revise_plan_raw(_cfg(), _words(body.words), EditPlan.from_dict(body.plan),
                              body.message, body.rhythm, body.style)


@app.post("/v1/ideas")
def ideas(request: Request, body: IdeasIn, x_iman_license: str = Header(""), x_iman_instance: str = Header("")):
    _check(x_iman_license, x_iman_instance, request)
    return {"ideas": ai.generate_ideas(_cfg(), body.topic, body.audience, body.voice_samples, body.n)}


class CascadeIn(BaseModel):
    transcript: str = Field(..., max_length=60000)


@app.post("/v1/cascada")
def cascada(request: Request, body: CascadeIn, x_iman_license: str = Header(""), x_iman_instance: str = Header("")):
    _check(x_iman_license, x_iman_instance, request)
    words = [Word(t, 0.0, 0.0) for t in body.transcript.split()]
    return ai.cascade_texts(_cfg(), words)


class BrandIn(BaseModel):
    description: str = Field(..., max_length=400)


@app.post("/v1/brand")
def brand(request: Request, body: BrandIn, x_iman_license: str = Header(""), x_iman_instance: str = Header("")):
    _check(x_iman_license, x_iman_instance, request)
    return ai.brand_copy(_cfg(), body.description)


class PostIn(BaseModel):
    transcript: str = Field(..., max_length=6000)
    hook: str = Field("", max_length=200)
    pack: str = Field("", max_length=20)
    cta: str = Field("", max_length=60)
    handle: str = Field("", max_length=60)


@app.post("/v1/post")
def post(request: Request, body: PostIn, x_iman_license: str = Header(""), x_iman_instance: str = Header("")):
    _check(x_iman_license, x_iman_instance, request)
    return ai.post_copy(_cfg(), body.transcript, body.hook, body.pack, body.cta, body.handle)


class KitIn(BaseModel):
    transcript: str = Field(..., max_length=6000)
    hook: str = Field("", max_length=200)
    pack: str = Field("", max_length=20)
    cta: str = Field("", max_length=60)
    current: dict = Field(default_factory=dict)
    message: str = Field("", max_length=1000)


@app.post("/v1/kit")
def kit(request: Request, body: KitIn, x_iman_license: str = Header(""), x_iman_instance: str = Header("")):
    _check(x_iman_license, x_iman_instance, request)
    return ai.kit_copy_raw(_cfg(), body.transcript, body.hook, body.pack, body.cta, body.current, body.message)


class StyleIn(BaseModel):
    frames: list[str] = Field(..., max_length=8)
    extra: str = Field("", max_length=300)


@app.post("/v1/style")
def style(request: Request, body: StyleIn, x_iman_license: str = Header(""), x_iman_instance: str = Header("")):
    import base64

    _check(x_iman_license, x_iman_instance, request)
    frames = [base64.b64decode(f) for f in body.frames]
    if any(len(f) > 600_000 for f in frames):
        raise HTTPException(413, "Fotogramas demasiado grandes")
    return ai.style_from_frames(_cfg(), frames, body.extra)


@app.get("/health")
def health():
    return {"ok": True}


class ClipsIn(BaseModel):
    transcript: str = Field(..., max_length=120000)
    n: int = Field(4, ge=1, le=8)


@app.post("/v1/clips")
def clips(request: Request, body: ClipsIn, x_iman_license: str = Header(""), x_iman_instance: str = Header("")):
    _check(x_iman_license, x_iman_instance, request)
    return ai.pick_clips_raw(_cfg(), body.transcript, body.n)
