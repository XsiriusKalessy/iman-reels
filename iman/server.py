"""Servidor web local: `iman web` y abre http://localhost:8765"""

from __future__ import annotations

import io
import json
import logging
import shutil
import threading
import time
import uuid
from dataclasses import asdict, fields, replace
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai, brand, config, copystyle, effects, jsonfile, license, media, musica, packs, pipeline, portable, redes, updates
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


def _set(job_id: str, **kw) -> None:
    with _lock:
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
        (d / "job.json").write_text(json.dumps({k: v for k, v in job.items() if k != "trial"}, ensure_ascii=False), encoding="utf-8")


def _job(job_id: str) -> dict | None:
    if job_id in JOBS:
        return JOBS[job_id]
    if not job_id.isalnum():
        return None
    f = JOBS_DIR / job_id / "job.json"
    if not f.exists():
        return None
    job = json.loads(f.read_text(encoding="utf-8"))
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
                    "duration": r.get("duration_out", 0), "pack": (job.get("options") or {}).get("pack", "")})
    return {"reels": sorted(out, key=lambda r: -r["created"])}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    job = _job(job_id)
    if not job or job["status"] == "working":
        raise HTTPException(404, "No encuentro ese reel o aún se está editando")
    shutil.rmtree(JOBS_DIR / job_id, ignore_errors=True)
    JOBS.pop(job_id, None)
    return {"ok": True}


@app.get("/api/options")
def options():
    return {
        "rhythms": [{"key": r.key, "label": r.label, "description": r.description} for r in RHYTHMS.values()],
        "styles": _styles(),
        "hook_templates": HOOK_TEMPLATES,
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
            raise HTTPException(502, f"La IA no ha podido analizar el reel: {e}")
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
    anthropic_key: str | None = None
    openai_key: str | None = None
    pexels_key: str | None = None
    transcriber: str | None = None
    whisper_model: str | None = None
    language: str | None = None


@app.post("/api/settings")
def set_settings(body: SettingsIn):
    data = {k: v for k, v in body.model_dump().items() if v is not None and v != ""}
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
        got = portable.import_(await file.read())
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
        raise HTTPException(502, f"La IA no ha podido preparar tu marca: {e}")
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


def _voice_samples() -> str:
    """Transcripciones de reels anteriores, para que las ideas suenen a ti."""
    texts = []
    for t in sorted(JOBS_DIR.glob("*/transcript.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
        texts.append(" ".join(w["text"] for w in json.loads(t.read_text(encoding="utf-8"))))
    return "\n---\n".join(texts)


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
    with dst.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
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
    if not dst.exists():
        musica.render(key, 20, dst, seed=len(key))
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
    red: str = Form("instagram"),
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
    saved = config.memory_prompt(config.load())
    if saved:
        instructions = f"{saved}\n\n{instructions}".strip()
    job_id = uuid.uuid4().hex[:10]
    workdir = JOBS_DIR / job_id
    workdir.mkdir(parents=True, exist_ok=True)
    takes = []
    for k, up in enumerate(video[:MAX_TAKES]):
        suffix = Path(up.filename or "video.mp4").suffix or ".mp4"
        take = workdir / (f"original{suffix}" if len(video) == 1 else f"toma-{k + 1:02d}{suffix}")
        with take.open("wb") as f:
            shutil.copyfileobj(up.file, f)
        takes.append(take)
    src = takes[0] if len(takes) == 1 else workdir / "original.mp4"
    names = _save_broll(workdir, broll or [])
    if background == "foto":
        if not background_photo or not _save_background(workdir, await background_photo.read()):
            background = ""  # sin foto válida, se queda el fondo de verdad
    music = "mia" if music_file and _save_music(workdir, music_file) else \
        (music_style if music_style in musica.STYLES or music_style == "auto" else "")
    if names and mode == "camara":  # en "solo voz" los vídeos ya son la imagen de todo el reel
        instructions = f"{instructions}\n\n{pipeline.broll_prompt(names)}".strip()
    opts = pipeline.EditOptions(rhythm, style, size, fit, hook, hook_title, hook_template, instructions,
                                voice=voice, ruido=ruido, watermark=watermark, brand=use_brand, pack=pack,
                                mode="voz" if mode == "voz" else "camara", background=background,
                                sfx=sfx, music=music, punch=punch, barra=barra, transiciones=transiciones,
                                look=look if look in media.LOOKS or look == "auto" else "",
                                red=red if red in redes.REDES else "instagram")
    JOBS[job_id] = {"id": job_id, "status": "working", "step": "En cola", "progress": 0.0, "mode": mode,
                    "options": asdict(opts), "created": time.time(), "trial": watermark and mode != "largo"}
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
                                                 lambda msg, pct: _set(job_id, step=msg, progress=pct * 0.3))
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
            JOBS[cid] = {"id": cid, "status": "working", "step": "En cola", "progress": 0.0, "from_long": job_id,
                         "options": asdict(copts), "created": time.time(), "trial": opts.watermark}
            _work(cid, csrc, cdir, copts)
            if JOBS[cid]["status"] == "done":
                r = JOBS[cid]["result"]
                made.append({"id": cid, "title": r["plan"].get("hook_title", ""), "why": pick["why"],
                             "duration": r["duration_out"]})
        if not made:
            raise ValueError(next((JOBS[c]["error"] for c in JOBS if JOBS[c].get("from_long") == job_id
                                   and JOBS[c].get("error")), "No he podido editar ningún reel"))
        _set(job_id, status="done", progress=1.0, result={"clips": made})
    except Exception as e:
        _set(job_id, status="error", error=str(e))


def _save_broll(workdir: Path, files: list[UploadFile]) -> list[str]:
    """Guarda los vídeos y fotos de apoyo como apoyo/01.mp4, 02.jpg… y devuelve sus nombres originales."""
    names = []
    for up in files[:12]:
        ext = Path(up.filename or "").suffix.lower()
        if not up.filename or ext not in effects.MEDIA_EXT:
            continue
        d = workdir / "apoyo"
        d.mkdir(exist_ok=True)
        with (d / f"{len(names) + 1:02d}{ext}").open("wb") as f:
            shutil.copyfileobj(up.file, f)
        names.append(Path(up.filename).stem[:60])
    return names


def _work(job_id: str, src: Path, workdir: Path, opts: pipeline.EditOptions, plan=None) -> None:
    try:
        res = pipeline.run(src, workdir, opts, config.load(),
                           progress=lambda msg, pct: _set(job_id, step=msg, progress=pct), plan=plan)
        if JOBS[job_id].pop("trial", False):
            cfg = config.load()
            config.save({"free_reels_used": int(cfg.get("free_reels_used") or 0) + 1})
        _set(job_id, status="done", result=res.summary())
    except Exception as e:
        log.exception("Falla la edición de %s", job_id)
        try:
            (workdir / "error.log").write_text(f"{e}\n", encoding="utf-8")
        except OSError:
            pass
        prev = JOBS[job_id].get("result")
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
    src = next(workdir.glob("original.*"))
    known = {f.name for f in fields(pipeline.EditOptions)}
    merged = {**job["options"], **{k: v for k, v in body.items() if k in known}}
    opts = pipeline.EditOptions(**merged)
    _claim(job_id, step="Aplicando cambios", progress=0.0, options=asdict(opts), error=None)
    plan_file = workdir / "plan.json"
    saved = jsonfile.load(plan_file)  # si se guardó mal, se vuelve a planificar desde cero
    plan = EditPlan.from_dict(saved) if saved is not None else None
    if plan is not None and "hook_title" in body:
        plan.hook_title = body["hook_title"]
    threading.Thread(target=_work, args=(job_id, src, workdir, opts, plan), daemon=True).start()
    return JOBS[job_id]


class ChatIn(BaseModel):
    message: str
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
        raise HTTPException(502, f"La IA no ha podido aplicar el cambio: {e}")
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
    _claim(job_id, step="Aplicando tus cambios", progress=0.0, options=asdict(opts),
         error=None, chat=history)
    src = next(workdir.glob("original.*"))
    threading.Thread(target=_work, args=(job_id, src, workdir, opts, new_plan), daemon=True).start()
    return JOBS[job_id]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = _job(job_id)
    if job is None:
        raise HTTPException(404, "No encuentro ese reel")
    return job


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
    _claim(job_id, step="Aplicando cambios", progress=0.0, options=asdict(opts), error=None)
    src = next(workdir.glob("original.*"))
    threading.Thread(target=_work, args=(job_id, src, workdir, opts, plan), daemon=True).start()
    return JOBS[job_id]


@app.post("/api/jobs/{job_id}/post")
def post_copy(job_id: str):
    """Texto de la publicación y hashtags, escritos por la IA con lo que dices en el vídeo."""
    job = _job(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "No encuentro ese reel")
    workdir = JOBS_DIR / job_id
    cached = workdir / "post.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    aicfg = config.ai_config(config.load())
    if not aicfg.enabled:
        raise HTTPException(400, "Activa la IA en Ajustes para que te escriba el texto de la publicación")
    words = _saved_words(workdir)
    b = brand.load()
    try:
        data = ai.post_copy(aicfg, " ".join(w.text for w in words), job["result"]["plan"].get("hook_title", ""),
                            job["options"].get("pack", ""), b.cta, b.handle)
    except Exception as e:
        raise HTTPException(502, f"La IA no ha podido escribir el texto: {e}")
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
            raise HTTPException(502, f"La IA no ha podido preparar el carrusel: {e}")
    else:
        data = kit.fallback(words, hook, b.cta)
    # Fotogramas limpios (sin subtítulos) de la toma original: la portada y unos cuantos más.
    src = workdir / "lienzo.mp4" if (workdir / "lienzo.mp4").exists() else next(workdir.glob("original.*"))
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
    p = JOBS_DIR / job_id / "kit" / name
    if not job_id.isalnum() or "/" in name or ".." in name or not p.exists():
        raise HTTPException(404)
    media = "application/zip" if name.endswith(".zip") else "image/png"
    return FileResponse(p, media_type=media, filename=f"{job_id}-{name}" if name.endswith(".zip") else None)


@app.post("/api/jobs/{job_id}/portadas")
def make_covers(job_id: str):
    """Tres portadas tipo YouTube (tú recortado, luz de borde, texto grande), en vertical y en horizontal."""
    from . import miniaturas

    job = _job(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "No encuentro ese reel")
    workdir = JOBS_DIR / job_id
    src = workdir / "lienzo.mp4" if (workdir / "lienzo.mp4").exists() else next(workdir.glob("original.*"))
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
    p = JOBS_DIR / job_id / "portadas" / name
    if not job_id.isalnum() or "/" in name or ".." in name or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg")


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
    p = PHOTOS_DIR / name
    if "/" in name or "\\" in name or ".." in name or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png" if name.endswith(".png") else "image/jpeg", filename=name)


@app.get("/api/jobs/{job_id}/cover.jpg")
def get_cover(job_id: str, t: float = 0.5):
    """Fotograma del reel para usarlo de portada."""
    p = JOBS_DIR / job_id / "reel.mp4"
    if not job_id.isalnum() or not p.exists():
        raise HTTPException(404)
    out = JOBS_DIR / job_id / f"cover-{int(max(0.0, t) * 10)}.jpg"
    if not out.exists():
        from . import media

        media.thumbnail(p, out, max(0.0, t))
    return FileResponse(out, media_type="image/jpeg", filename=f"portada-{job_id}.jpg")


@app.get("/api/jobs/{job_id}/reel.mp4")
def get_video(job_id: str):
    p = JOBS_DIR / job_id / "reel.mp4"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4", filename=f"reel-{job_id}.mp4")


@app.get("/api/jobs/{job_id}/sin-silencios.mp4")
def get_rough(job_id: str):
    """Pestaña «Sin silencios»: tu vídeo solo con los cortes, para revisar lo que se queda."""
    workdir = JOBS_DIR / job_id
    dst = workdir / "sin-silencios.mp4"
    if not dst.exists():
        spans = jsonfile.load(workdir / "tramos.json")
        src = next(workdir.glob("original.*"), None)
        if not spans or src is None:
            raise HTTPException(404)
        with _rough_lock:
            if not dst.exists():
                media.rough_cut(src, [tuple(s) for s in spans], dst)
    return FileResponse(dst, media_type="video/mp4")


_rough_lock = threading.Lock()


@app.get("/api/jobs/{job_id}/original")
def get_original(job_id: str):
    """Pestaña «Vídeo original»: lo que subiste, tal cual."""
    src = next((JOBS_DIR / job_id).glob("original.*"), None)
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
        src = next(workdir.glob("original.*"))
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
    p = JOBS_DIR / job_id / "versiones" / name
    if not job_id.isalnum() or "/" in name or ".." in name or not p.exists():
        raise HTTPException(404)
    media_type = "application/zip" if name.endswith(".zip") else "video/mp4"
    return FileResponse(p, media_type=media_type, filename=f"reel-{job_id}-{name}")


CASCADES: dict[str, dict] = {}


def _make_cascade(job_id: str) -> None:
    from . import cascada

    workdir = JOBS_DIR / job_id
    state = CASCADES[job_id]
    try:
        src = next(p for p in workdir.glob("original.*"))
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
    if job_id not in CASCADES and (JOBS_DIR / job_id / "cascada" / "cascada.zip").exists():
        return {"status": "done", "step": "", "progress": 1.0, "result": None, "error": None}
    return CASCADES.get(job_id) or {"status": "none", "step": "", "progress": 0.0, "result": None, "error": None}


@app.get("/api/jobs/{job_id}/cascada/{name:path}")
def cascade_file(job_id: str, name: str):
    base = JOBS_DIR / job_id / "cascada"
    p = base / name
    if not job_id.isalnum() or ".." in name or name.startswith("/") or not p.is_file():
        raise HTTPException(404)
    kinds = {".zip": "application/zip", ".mp4": "video/mp4", ".mp3": "audio/mpeg", ".png": "image/png",
             ".txt": "text/plain; charset=utf-8"}
    return FileResponse(p, media_type=kinds.get(p.suffix, "application/octet-stream"),
                        filename=f"{job_id}-{p.name}" if p.suffix != ".png" else None)


@app.get("/api/jobs/{job_id}/whatsapp.zip")
def get_whatsapp(job_id: str):
    """El reel en trozos de menos de 60 s (los estados de WhatsApp cortan ahí), partido entre frases."""
    import zipfile

    workdir = JOBS_DIR / job_id
    p = workdir / "reel.mp4"
    if not p.exists():
        raise HTTPException(404)
    out = workdir / "whatsapp.zip"
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
    p = JOBS_DIR / job_id / "reel.jpg"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg")


app.mount("/fonts", StaticFiles(directory=Path(__file__).parent / "assets" / "fonts"), name="fonts")
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
