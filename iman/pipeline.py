"""Sube tu vídeo → cómo lo editas → tu reel."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import ai, effects, media
from .config import ai_config
from .captions import STYLES, _ts, build_ass

WATERMARK = (
    "Dialogue: 9,0:00:00.00,{end},Sub,,0,0,0,,"
    "{{\\an2\\pos(540,1840)\\fs40\\bord2\\shad0\\alpha&H40&}}Hecho con Imán · prueba gratis"
)
from .models import EditPlan, Word
from .rhythm import RHYTHMS, keep_spans, remap_words


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
    progress("Preparando tu vídeo", 0.03)
    info = media.probe(src)
    if not info.has_audio:
        raise ValueError("El vídeo no tiene audio: Imán necesita oírte para editar")

    transcript_file = workdir / "transcript.json"
    if words is None and transcript_file.exists():
        words = [Word(**w) for w in json.loads(transcript_file.read_text())]
    if words is None:
        progress("Escuchando lo que dices", 0.10)
        from .transcribe import transcribe

        audio = media.extract_audio(src, workdir / "audio.wav")
        words = transcribe(
            audio, cfg.get("transcriber", "local"), cfg.get("language") or None,
            cfg.get("whisper_model", "small"), cfg.get("openai_key") or None,
        )
    if not transcript_file.exists():
        transcript_file.write_text(json.dumps([w.__dict__ for w in words], ensure_ascii=False, indent=1))

    progress("Buscando fallos y el mejor gancho", 0.40)
    aicfg = ai_config(cfg)
    if plan is not None:
        pass  # plan ya decidido (p. ej. tras un cambio pedido por chat)
    elif aicfg.enabled and words:
        plan = EditPlan()
        try:
            plan = ai.plan_edit(aicfg, words, opts.instructions, opts.hook_template)
        except Exception as e:  # la IA es un extra: si falla, seguimos
            plan.drop_reasons.append(f"IA no disponible: {e}")
    else:
        plan = EditPlan()
    if opts.hook_title:
        plan.hook_title = opts.hook_title

    progress("Cortando silencios y tomas falsas", 0.55)
    rhythm = RHYTHMS[opts.rhythm]
    spans, drops = keep_spans(words, info.duration, rhythm, plan.drop)
    zooms_wanted = plan.zooms if opts.effects else []
    spans = effects.split_spans(spans, words, zooms_wanted)
    zoom = effects.zoom_flags(spans, words, zooms_wanted, opts.auto_zoom and rhythm.cut)
    kept, kept_idx = remap_words(words, spans, drops)
    out_duration = sum(s.duration for s in spans)
    if not plan.hook_title and kept:
        plan.hook_title = ai.fallback_hook(kept)
    (workdir / "plan.json").write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=1))

    ass_path = None
    if opts.captions or opts.hook or opts.watermark:
        style = STYLES[opts.style]
        emphasis_out = {j for j, i in enumerate(kept_idx) if i in set(plan.emphasis)}
        fx_lines, fx_windows = ([], [])
        if opts.effects:
            fx_lines, fx_windows = effects.build_effects(
                plan.effects, effects.WordClock(kept, kept_idx), style, out_duration, info.duration
            )
        ass = build_ass(
            kept if opts.captions else [], style, out_duration,
            plan.hook_title if opts.hook else "", emphasis_out,
            extra_events=fx_lines + ([WATERMARK.format(end=_ts(out_duration))] if opts.watermark else []),
            hide=fx_windows,
        )
        ass_path = workdir / "subs.ass"
        ass_path.write_text(ass, encoding="utf-8")

    progress("Montando tu reel", 0.65)
    out = workdir / "reel.mp4"
    media.render(src, out, spans, info, ass_path, opts.size, opts.fit, opts.voice, zoom)
    media.thumbnail(out, workdir / "reel.jpg", min(0.6, out_duration / 2))
    progress("Listo", 1.0)
    return EditResult(
        video=out, plan=plan, duration_in=info.duration, duration_out=out_duration,
        removed_words=[words[i].text for i in sorted(drops)],
        cuts=sum(1 for a, b in zip(spans, spans[1:]) if abs(a.end - b.start) > 1e-3),
    )
