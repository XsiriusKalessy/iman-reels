"""Sube tu vídeo → cómo lo editas → tu reel."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import ai, brand, copystyle, effects, media, segment
from .config import ai_config
from .captions import STYLES, _ts, build_ass
from .models import EditPlan, Word
from .rhythm import RHYTHMS, detect_retakes, is_filler, keep_spans, phrases, remap_words

WATERMARK = (
    "Dialogue: 9,0:00:00.00,{end},Sub,,0,0,0,,"
    "{{\\an2\\pos(540,1840)\\fs40\\bord2\\shad0\\alpha&H40&}}Hecho con Imán · prueba gratis"
)


@dataclass
class EditOptions:
    rhythm: str = "rapido"
    style: str = "impacto"
    size: str = "1080"  # 1080 | 4k
    fit: str = "recortar"  # recortar | fondo
    hook: bool = True
    hook_title: str = ""  # si lo escribe el creador, manda sobre la IA
    hook_template: str = ""
    instructions: str = ""
    captions: bool = True
    voice: bool = True  # limpiar y nivelar la voz
    auto_zoom: bool = True  # alternar plano normal y cerrado en cada corte
    effects: bool = True  # lista animada, palabra gigante y zoom de énfasis
    watermark: bool = False  # reels de prueba sin licencia
    brand: bool = True  # aplicar el kit de marca guardado (colores, logo y cierre)
    pack: str = ""  # sector: viajes, cursos, productos, empresas (vacío = general)
    mode: str = "camara"  # camara (hablas a cámara) | voz (solo tu voz, sobre tus vídeos o un fondo)


@dataclass
class EditResult:
    video: Path
    plan: EditPlan
    duration_in: float
    duration_out: float
    removed_words: list[str] = field(default_factory=list)
    cuts: int = 0

    def summary(self) -> dict:
        return {
            "video": self.video.name,
            "plan": self.plan.to_dict(),
            "duration_in": round(self.duration_in, 2),
            "duration_out": round(self.duration_out, 2),
            "removed_words": self.removed_words,
            "cuts": self.cuts,
        }


Progress = Callable[[str, float], None]


def _source_time(spans, t: float) -> float:
    """Segundo de la toma original que se ve en el segundo `t` del reel."""
    acc = 0.0
    for sp in spans:
        if t < acc + sp.duration:
            return sp.start + (t - acc)
        acc += sp.duration
    return spans[-1].end if spans else 0.0


def broll_files(workdir: Path) -> list[Path]:
    """Vídeos y fotos de apoyo que el creador ha subido con su toma (1, 2, 3…)."""
    d = workdir / "apoyo"
    return sorted(p for p in d.glob("*") if p.suffix.lower() in effects.MEDIA_EXT) if d.exists() else []


def broll_prompt(names: list[str]) -> str:
    if not names:
        return ""
    lines = "\n".join(f"{i + 1}: {n}" for i, n in enumerate(names))
    return f"VÍDEOS DE APOYO que ha subido el creador (úsalos con el efecto \"apoyo\"):\n{lines}"


def visual_cuts(words: list[Word], every: float = 3.0) -> list[float]:
    """Dónde cambiar de plano en un reel de solo voz: cada ~3 s, mejor en una pausa o fin de frase."""
    cuts, last = [], 0.0
    for prev, w in zip(words, words[1:]):
        since = w.start - last
        natural = prev.text.rstrip()[-1:] in ".,;:?!" or w.start - prev.end > 0.25
        if (since >= every * 0.8 and natural) or since >= every * 1.4:
            last = max(prev.end, w.start - 0.08)
            cuts.append(round(last, 3))
    return cuts


def _transcribe(src: Path, workdir: Path, cfg: dict, progress: Progress) -> list[Word]:
    transcript_file = workdir / "transcript.json"
    if transcript_file.exists():
        return [Word(**w) for w in json.loads(transcript_file.read_text())]
    progress("Escuchando lo que dices", 0.10)
    from .transcribe import transcribe

    audio = media.extract_audio(src, workdir / "audio.wav")
    words = transcribe(
        audio, cfg.get("transcriber", "local"), cfg.get("language") or None,
        cfg.get("whisper_model", "small"), cfg.get("openai_key") or None,
    )
    transcript_file.write_text(json.dumps([w.__dict__ for w in words], ensure_ascii=False, indent=1))
    return words


def long_video_clips(src: Path, workdir: Path, cfg: dict, progress: Progress = lambda m, p: None,
                     n: int = 4) -> tuple[list[Word], list[dict]]:
    """Vídeo largo → los mejores momentos para reels (la IA los elige; sin IA, trozos de ~40 s)."""
    workdir.mkdir(parents=True, exist_ok=True)
    words = _transcribe(src, workdir, cfg, progress)
    progress("Buscando los mejores momentos", 0.5)
    picks: list[dict] = []
    aicfg = ai_config(cfg)
    if aicfg.enabled and words:
        try:
            picks = ai.pick_clips(aicfg, words, n)
        except Exception:  # la IA es un extra: si falla, cortamos por frases
            picks = []
    return words, picks or ai.fallback_clips(words, n)


def clip_source(src: Path, words: list[Word], pick: dict, workdir: Path) -> tuple[Path, list[Word]]:
    """Recorta el trozo elegido del vídeo largo y deja sus palabras con los tiempos del trozo."""
    workdir.mkdir(parents=True, exist_ok=True)
    a, b = pick["from"], pick["to"]
    t0, t1 = max(0.0, words[a].start - 0.25), words[b].end + 0.4
    dst = media.cut(src, workdir / "original.mp4", t0, t1)
    sub = [Word(w.text, round(w.start - t0, 3), round(w.end - t0, 3)) for w in words[a:b + 1]]
    (workdir / "transcript.json").write_text(json.dumps([w.__dict__ for w in sub], ensure_ascii=False, indent=1))
    return dst, sub


def review(words: list[Word], plan: EditPlan, rhythm_key: str) -> list[dict]:
    """Las frases de la toma, si se quedan o se van y por qué ("Revisa lo que dices")."""
    rhythm = RHYTHMS[rhythm_key]
    _, drops = keep_spans(words, words[-1].end if words else 0, rhythm, plan.drop + plan.cut, plan.restore,
                          plan.pauses)
    why: dict[int, str] = {}
    if rhythm.cut:
        if rhythm.remove_retakes:
            for a, b in detect_retakes(words):
                why.update({k: "Frase repetida" for k in range(a, b + 1)})
        if rhythm.remove_fillers:
            why.update({i: "Muletilla" for i in range(len(words)) if is_filler(words, i)})
        for (a, b), r in zip(plan.drop, plan.drop_reasons + [""] * len(plan.drop)):
            why.update({k: (r or "Toma falsa").capitalize() for k in range(a, b + 1)})
    for a, b in plan.cut:
        why.update({k: "La quitaste tú" for k in range(a, b + 1)})
    return [{"from": p.a, "to": p.b, "text": p.text, "start": round(p.start, 2), "end": round(p.end, 2),
             "state": p.state, "reason": p.reason if p.dropped else ""}
            for p in phrases(words, drops, why)]


def run(
    src: Path,
    workdir: Path,
    opts: EditOptions,
    cfg: dict,
    progress: Progress = lambda msg, pct: None,
    words: list[Word] | None = None,
    plan: EditPlan | None = None,
) -> EditResult:
    workdir.mkdir(parents=True, exist_ok=True)
    copystyle.register()  # los estilos copiados de otros reels
    if opts.style not in STYLES:
        opts.style = "impacto"
    progress("Preparando tu vídeo", 0.03)
    voice_only = opts.mode == "voz"
    clips = broll_files(workdir)
    if voice_only:
        # Sin cámara: primero te escucho y luego monto tu voz sobre tus vídeos (o un fondo) cambiando de plano.
        if words is None:
            words = _transcribe(src, workdir, cfg, progress)
        canvas = workdir / "lienzo.mp4"
        if not canvas.exists():
            progress("Montando tus vídeos con tu voz", 0.25)
            kit0 = brand.load() if opts.brand else None
            bg = kit0.primary if kit0 is not None and kit0.active and brand.is_hex(kit0.primary or "") else "#141518"
            media.voice_canvas(src, canvas, visual_cuts(words), clips, bg)
        src = canvas
    info = media.probe(src)
    if not info.has_audio:
        raise ValueError("El vídeo no tiene audio: Imán necesita oírte para editar")
    if words is None:
        words = _transcribe(src, workdir, cfg, progress)
    transcript_file = workdir / "transcript.json"
    if not transcript_file.exists():
        transcript_file.write_text(json.dumps([w.__dict__ for w in words], ensure_ascii=False, indent=1))

    progress("Buscando fallos y el mejor gancho", 0.40)
    aicfg = ai_config(cfg)
    if plan is not None:
        pass  # plan ya decidido (p. ej. tras un cambio pedido por chat)
    elif aicfg.enabled and words:
        plan = EditPlan()
        try:
            plan = ai.plan_edit(aicfg, words, opts.instructions, opts.hook_template, opts.pack)
        except Exception as e:  # la IA es un extra: si falla, seguimos
            plan.drop_reasons.append(f"IA no disponible: {e}")
    else:
        plan = EditPlan()
    if opts.hook_title:
        plan.hook_title = opts.hook_title

    progress("Cortando silencios y tomas falsas", 0.55)
    rhythm = RHYTHMS[opts.rhythm]
    spans, drops = keep_spans(words, info.duration, rhythm, plan.drop + plan.cut, plan.restore, plan.pauses)
    zooms_wanted = plan.zooms if opts.effects else []
    spans = effects.split_spans(spans, words, zooms_wanted)
    zoom = effects.zoom_flags(spans, words, zooms_wanted, opts.auto_zoom and rhythm.cut)
    kept, kept_idx = remap_words(words, spans, drops)
    out_duration = sum(s.duration for s in spans)
    if not plan.hook_title and kept:
        plan.hook_title = ai.fallback_hook(kept)
    if voice_only:  # no hay cara que poner en el círculo ni persona que recortar
        plan.effects = [fx for fx in plan.effects if fx.get("type") not in effects.PERSON_TYPES]
    else:
        plan.effects = effects.auto_broll(plan.effects, kept_idx, len(clips))
    (workdir / "plan.json").write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=1))

    active = [fx for fx in plan.effects if not fx.get("off")]  # los que el creador ha apagado no salen
    kit = brand.load() if opts.brand else None
    style = brand.apply(STYLES[opts.style], kit) if kit else STYLES[opts.style]
    # El cierre de marca va DESPUÉS de lo que dices, para no taparte la llamada a la acción.
    tail = effects.END_CARD if kit is not None and kit.active and kit.end_card and out_duration > 1 else 0.0
    total = out_duration + tail
    end_lines, end_window = effects.end_card_events(kit, style, total)
    ass_path = None
    if opts.captions or opts.hook or opts.watermark or end_lines:
        emphasis_out = {j for j, i in enumerate(kept_idx) if i in set(plan.emphasis)}
        fx_lines, fx_windows = ([], [])
        if opts.effects:
            fx_lines, fx_windows = effects.build_effects(
                active, effects.WordClock(kept, kept_idx), style, out_duration, info.duration
            )
        ass = build_ass(
            kept if opts.captions else [], style, total,
            plan.hook_title if opts.hook else "", emphasis_out,
            extra_events=fx_lines + end_lines + ([WATERMARK.format(end=_ts(total))] if opts.watermark else []),
            hide=fx_windows + ([end_window] if end_window else []),
        )
        ass_path = workdir / "subs.ass"
        ass_path.write_text(ass, encoding="utf-8")

    progress("Montando tu reel", 0.65)
    out = workdir / "reel.mp4"
    overlays = []
    if opts.effects:
        overlays = effects.video_ops(active, effects.WordClock(kept, kept_idx), out_duration,
                                     lambda t: _source_time(spans, t),
                                     {str(i + 1): str(p) for i, p in enumerate(clips)})
    overlays += effects.brand_ops(kit, total)
    clock = effects.WordClock(kept, kept_idx)
    segs = effects.seg_ops(active, clock, out_duration) if opts.effects else []
    if segs and segment.available():
        # Dos pasadas: primero el reel limpio, luego la persona recortada encima de lo que va detrás.
        base = media.render(src, workdir / "base.mp4", spans, info, None, opts.size, opts.fit, opts.voice, zoom,
                            preset="veryfast", tail=tail)
        progress("Recortándote del fondo", 0.80)
        mask = segment.person_masks(base, workdir / "mask.mp4", [(o.start, o.end) for o in segs])
        behind = workdir / "behind.ass"
        behind.write_text(build_ass([], style, total,
                                    extra_events=effects.behind_events(active, clock, style,
                                                                       out_duration)), encoding="utf-8")
        progress("Montando tu reel", 0.90)
        media.composite(base, mask, src, out, behind, ass_path, segs, overlays, opts.size)
    else:
        media.render(src, out, spans, info, ass_path, opts.size, opts.fit, opts.voice, zoom, overlays=overlays, tail=tail)
    media.thumbnail(out, workdir / "reel.jpg", min(0.6, out_duration / 2))
    progress("Listo", 1.0)
    return EditResult(
        video=out, plan=plan, duration_in=info.duration, duration_out=total,
        removed_words=[words[i].text for i in sorted(drops)],
        cuts=sum(1 for a, b in zip(spans, spans[1:]) if abs(a.end - b.start) > 1e-3),
    )
