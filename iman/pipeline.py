"""Sube tu vídeo → cómo lo editas → tu reel."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from . import ai, brand, captions, copystyle, effects, fondos, ganchos, gestos, hands, jsonfile, limpiar, media, musica, packfx, packs, pexels, redes, segment, seguir, sfx, viral
from .config import ai_config
from .captions import STYLES, _ts, build_ass
from .models import EditPlan, Span, Word
from .rhythm import RHYTHMS, detect_retakes, detect_take_retakes, is_filler, keep_spans, phrases, remap_words, take_ranges

log = logging.getLogger(__name__)

WATERMARK = (
    "Dialogue: 9,0:00:00.00,{end},Sub,,0,0,0,,"
    "{{\\an2\\pos(540,1840)\\fs40\\bord2\\shad0\\alpha&H40&}}Hecho con Imán · prueba gratis"
)


@dataclass
class EditOptions:
    rhythm: str = "rapido"
    style: str = "auto"  # "auto": el que recomienda la IA para este vídeo
    size: str = "1080"  # 1080 | 4k
    fit: str = "recortar"  # recortar | fondo
    hook: bool = True
    hook_title: str = ""  # si lo escribe el creador, manda sobre la IA
    hook_template: str = ""
    # Gancho visual de los primeros 3 s (iman/ganchos.py): "auto" = el que recomienda la IA; o una clave.
    gancho: str = "auto"
    instructions: str = ""
    captions: bool = True
    voice: bool = True  # limpiar y nivelar la voz
    ruido: bool = False  # quitar ruido fuerte de fondo (calle, tráfico, viento): iman/limpiar.py
    auto_zoom: bool = True  # alternar plano normal y cerrado en cada corte
    effects: bool = True  # lista animada, palabra gigante y zoom de énfasis
    watermark: bool = False  # reels de prueba sin licencia
    brand: bool = True  # aplicar el kit de marca guardado (colores, logo y cierre)
    pack: str = ""  # sector: viajes, cursos, productos, empresas (vacío = general)
    gestures: bool = True  # efectos que siguen tus manos (si se ven en el vídeo)
    mode: str = "camara"  # camara (hablas a cámara) | voz (solo tu voz, sobre tus vídeos o un fondo)
    # Fondo de todo el reel, recortándote: "" (el tuyo), desenfoque, color (el de tu marca) o foto (fondo.jpg).
    background: str = ""
    sfx: bool = True  # golpe de sonido en el gancho y un sonido en cada efecto
    # Música de fondo, que baja cuando hablas: "" sin música, "mia" la tuya (musica.* en la carpeta del reel)
    # o un estilo de Imán ("epica", "tranquila"…). True es lo mismo que "mia" (reels de versiones anteriores).
    music: bool | str = "auto"
    punch: bool = True  # zoom rápido de entrada en el primer medio segundo
    barra: bool = False  # barra de progreso arriba que se llena hasta el final (retención)
    transiciones: bool = True  # whip y glitch en uno de cada dos cortes
    # Reel que responde a un comentario: la burbuja con el comentario sale al principio (estilo "respondiendo a").
    comentario: str = ""
    comentario_de: str = ""
    red: str = "instagram"  # para qué red es (iman/redes.py): instagram, tiktok, youtube, anuncio
    ligero: bool = False  # ordenador sencillo: sin los efectos más pesados ni 4K (iman/equipo.py)
    letra: str = "normal"  # tamaño de los subtítulos: normal, grande o enorme (captions.SIZES)
    idioma: str = ""  # subtítulos y textos en otro idioma ("en", "fr"…): la voz se queda, los textos se traducen
    look: str = "auto"  # "auto" = el que recomienda la IA; o color y textura de un clic (media.LOOKS): "calido", "teal", "cine", "grano", "retro", "bn"…
    directo: bool = False  # vídeo largo que es un directo: los momentos se eligen también por la energía del audio
    # Varias tomas unidas en orden: [{"nombre", "inicio", "fin"}] en segundos del vídeo unido (server._join_then).
    tomas: list = field(default_factory=list)
    # Cuánto espectáculo: "alta" (un efecto cada 3-5 s, los más vistosos primero), "media" o "baja" (solo si aportan).
    intensidad: str = "alta"
    circulo: bool = False  # tu cara en un círculo sobre los vídeos de apoyo, el mapa y las tarjetas (tapaba títulos)


@dataclass
class EditResult:
    video: Path
    plan: EditPlan
    duration_in: float
    duration_out: float
    removed_words: list[str] = field(default_factory=list)
    cuts: int = 0
    ai_warning: str = ""
    notices: list[str] = field(default_factory=list)  # avisos: algo se ha quitado para que el reel salga
    checks: list[dict] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)  # «Revisado y arreglado solo»: lo que Imán ha decidido por ti
    viral: dict = field(default_factory=dict)  # nota de viralidad (iman/viral.py)

    def summary(self) -> dict:
        return {
            "video": self.video.name,
            "plan": self.plan.to_dict(),
            "duration_in": round(self.duration_in, 2),
            "duration_out": round(self.duration_out, 2),
            "removed_words": self.removed_words,
            "cuts": self.cuts,
            "ai_warning": self.ai_warning,
            "notices": self.notices,
            "checks": self.checks,
            "fixes": self.fixes,
            "viral": self.viral,
        }


Progress = Callable[[str, float], None]


def _publish(tmp: Path, dst: Path) -> Path:
    """Pone el reel recién montado en su sitio. En Windows el archivo puede estar abierto un momento
    (el reproductor de la app lo está leyendo): se reintenta y, si no, se copia encima."""
    for suf in (".filters.txt", ".composite.txt"):  # los filtros usados, junto al reel, por si hay que revisarlos
        side = tmp.with_suffix(suf)
        if side.exists():
            os.replace(side, dst.with_suffix(suf))
    for _ in range(20):
        try:
            os.replace(tmp, dst)
            return dst
        except PermissionError:
            time.sleep(0.15)
    shutil.copyfile(tmp, dst)
    tmp.unlink(missing_ok=True)
    return dst


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


INTENSIDADES = ("alta", "media", "baja")
INTENSITY_NOTE = {
    "alta": ("INTENSIDAD ALTA (el estilo de los reels que más enganchan): pon un efecto cada 3 a 5 segundos (en un "
             "reel de 60 s, de 12 a 18), empezando fuerte en el primer segundo, y que nunca pasen más de 5 s sin "
             "un cambio en pantalla. Prioriza los más vistosos: detras, titular, palabra, cifra, texto3d, hueca, "
             "color, lluvia, lista, bocadillo, notificaciones; los sutiles (foco, marco, progreso) solo de "
             "acompañamiento. Textos cortos y grandes, con las palabras exactas que dice. De 6 a 10 zooms."),
    "media": "",
    "baja": ("INTENSIDAD BAJA: pocos efectos, uno cada 10 a 15 segundos y solo si aportan de verdad; textos "
             "discretos. De 2 a 4 zooms."),
}
DEDUPE_GAP = {"alta": 0.6, "media": 1.0, "baja": 1.5}


def takes_prompt(tomas: list[dict]) -> str:
    """Varias tomas unidas: la IA sabe dónde empieza y acaba cada una (y cómo se llamaba el archivo), para que
    «en la toma 2 pon el texto…» o «el vídeo del templo» caigan en el tramo correcto."""
    if len(tomas) < 2:
        return ""
    lines = "\n".join(f"Toma {i + 1} «{t['nombre']}»: del segundo {t['inicio']:.1f} al {t['fin']:.1f}"
                       for i, t in enumerate(tomas))
    return ("EL VÍDEO SON VARIAS TOMAS UNIDAS, en el orden que ha elegido el creador (no lo cambies):\n" + lines +
            "\nSi el creador habla de la toma 1, 2… o del vídeo por su nombre, se refiere a ese tramo de tiempo: "
            "sus textos y efectos van dentro de ese tramo. Si pide un texto para cada toma, pon un texto por toma, "
            "en su orden. Si una toma repite lo que dice otra, es una toma falsa: quita entera la versión fallida "
            "(normalmente la primera) y deja la buena.")


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


BACKGROUNDS = ("", "desenfoque", "color", "foto", "marca_degradado", "marca_bokeh", "marca_logo")


def _background_op(opts: EditOptions, workdir: Path, kit, duration: float):
    """El fondo elegido para todo el reel, como un efecto de recorte que dura de principio a fin."""
    if opts.background == "desenfoque":
        return effects.SegOp("desenfoque", 0.0, duration)
    if opts.background in fondos.VARIANTS:
        # Fondo de marca diseñado (base oscura con la luz del color de la marca), no un color liso.
        primary = kit.primary if kit is not None and brand.is_hex(kit.primary or "") else "#FF5547"
        secondary = kit.secondary if kit is not None and brand.is_hex(kit.secondary or "") else ""
        logo = kit.logo_path if kit is not None else None
        key = hashlib.sha1(f"{opts.background}{primary}{secondary}{logo and logo.stat().st_mtime}".encode()).hexdigest()[:10]
        img = workdir / f"fondo-marca-{key}.jpg"
        if not img.exists():
            fondos.render(opts.background, primary, secondary, img, logo)
        return effects.SegOp("foto", 0.0, duration, path=str(img))
    photo = workdir / "fondo.jpg"
    if opts.background == "foto" and photo.exists():
        return effects.SegOp("foto", 0.0, duration, path=str(photo))
    return None


def _transcribe(src: Path, workdir: Path, cfg: dict, progress: Progress) -> list[Word]:
    transcript_file = workdir / "transcript.json"
    cached = jsonfile.load(transcript_file)
    if cached is not None:
        return [Word(**w) for w in cached]
    progress("Escuchando lo que dices", 0.10)
    from .transcribe import transcribe

    audio = media.extract_audio(src, workdir / "audio.wav")
    words = transcribe(
        audio, cfg.get("transcriber", "local"), cfg.get("language") or None,
        cfg.get("whisper_model", "small"), cfg.get("openai_key") or None,
        on_progress=lambda f: progress("Escuchando lo que dices", round(0.10 + 0.25 * f, 3)),
    )
    jsonfile.save(transcript_file, [w.__dict__ for w in words], indent=1)
    return words


def long_video_clips(src: Path, workdir: Path, cfg: dict, progress: Progress = lambda m, p: None,
                     n: int = 4, directo: bool = False) -> tuple[list[Word], list[dict]]:
    """Vídeo largo → los mejores momentos para reels (la IA los elige; sin IA, trozos de ~40 s).
    Con `directo`, también se mide la energía del audio (risas, subidas de voz) y se le pasa a la IA."""
    workdir.mkdir(parents=True, exist_ok=True)
    words = _transcribe(src, workdir, cfg, progress)
    if jsonfile.load(workdir / "transcript.json") is None:  # para el método cascada, más tarde
        jsonfile.save(workdir / "transcript.json", [w.__dict__ for w in words], indent=1)
    hints = ""
    if directo:
        progress("Buscando los momentos con más energía", 0.45)
        from . import energia

        hints = energia.hint(src)
    progress("Buscando los mejores momentos", 0.5)
    picks: list[dict] = []
    aicfg = ai_config(cfg)
    if aicfg.enabled and words:
        try:
            picks = ai.pick_clips(aicfg, words, n, hints)
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
    jsonfile.save(workdir / "transcript.json", [w.__dict__ for w in sub], indent=1)
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



AUTO_LOOK = {"viajes": "teal"}
AUTO_MUSIC = {"viajes": "aventura", "viajero": "documental", "cursos": "corporativa", "productos": "alegre", "empresas": "corporativa"}


def pre_publish(opts: "EditOptions", plan: EditPlan, kept: list[Word], total: float, active: list[dict],
                kit, has_music: bool) -> list[dict]:
    """Revisión antes de publicar: lo que hace que un reel retenga, comprobado sobre este reel."""
    first = kept[0].start if kept else 0.0
    cta = any(fx.get("type") == "cta" for fx in active) or bool(kit and kit.active and kit.end_card)
    effects_n = len(active)
    out = [
        {"ok": bool(opts.hook and plan.hook_title), "text": "Gancho en pantalla desde el primer segundo",
         "tip": "Activa el gancho o escribe uno en «Gancho»."},
        {"ok": first < 0.6, "text": "Empiezas a hablar enseguida",
         "tip": f"Tardas {first:.1f} s en hablar: prueba el ritmo «Más rápido»."},
        {"ok": 7 <= total <= 90, "text": f"Duración buena para reels ({total:.0f} s)",
         "tip": "Lo ideal es entre 15 y 60 segundos." if total > 90 else "Es muy corto: cuenta algo más."},
        {"ok": opts.captions, "text": "Subtítulos (la mayoría lo ve sin sonido)", "tip": "Activa los subtítulos."},
        {"ok": effects_n >= max(2, int(total / 10)), "text": f"Algo cambia en pantalla a menudo ({effects_n} efectos)",
         "tip": "Pide más efectos en «Dímelo como a tu editor»."},
        {"ok": cta, "text": "Llamada a la acción al final",
         "tip": "Di qué hacer al final (seguirte, comentar, reservar) o activa el cierre en «Mi marca»."},
        {"ok": has_music or opts.music == "", "text": "Música de fondo", "tip": "Elige una música en «Música»."},
        {"ok": True, "text": "Volumen listo para Instagram, TikTok y YouTube (-14 LUFS)", "tip": ""},
        {"ok": True, "text": "Textos fuera de las zonas que tapan los botones de la app", "tip": ""},
    ]
    return out


AUDIO_EXT = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac", ".opus", ".mp4", ".mov")


def _music(choice, workdir: Path, total: float, drop_at: float | None = None) -> Path | None:
    """La música del reel: la tuya (subida como musica.*) o una de Imán generada a la medida del reel."""
    if choice is True or choice == "mia":
        return next((p for p in sorted(workdir.glob("musica.*")) if p.suffix.lower() in AUDIO_EXT), None)
    if choice in musica.STYLES:
        return musica.render(choice, total, workdir / "musica_iman.wav", seed=len(choice), drop_at=drop_at)
    return None


def _face_positions(active: list[dict], src: Path, spans, clock, workdir: Path) -> None:
    """Dónde está la cara cuando empieza una lista: la lista se coloca en la otra mitad de la pantalla.
    Un fotograma y el modelo de persona (iman/segment.py); si falla, la lista va donde siempre."""
    if not segment.available():
        return
    from PIL import Image

    for fx in active:
        if fx.get("type") not in ("lista", "bloques", "paso"):
            continue
        t = clock.at(effects.word_of(fx))
        if t is None:
            continue
        try:
            still = media.thumbnail(src, workdir / "cara.tmp.jpg", _source_time(spans, t))
            with Image.open(still) as im:
                pos = segment.subject(im)
            if pos:
                fx["_face_y"] = round(pos[1] + 0.12, 2)  # coronilla + media cabeza: el centro de la cara
        except Exception:  # noqa: BLE001 - sin cara detectada, la lista va donde siempre
            log.debug("No se pudo situar la cara para la lista")
        finally:
            (workdir / "cara.tmp.jpg").unlink(missing_ok=True)


def _follow_head(active: list[dict], src: Path, info, spans, zoom, fit: str, clock, duration: float,
                 progress: Progress, frames: list[float] | None = None) -> None:
    """Etiquetas y anillos que te siguen: se busca tu cabeza en su rato y se guarda el recorrido en `_track`."""
    for fx in active:
        if fx.get("type") not in ("etiqueta", "anillo"):
            continue
        span = effects._span(fx, clock, duration, *((3.2, 1.8) if fx["type"] == "anillo" else (2.6, 1.5)))
        if not span:
            continue
        progress("Siguiendo tu cabeza", 0.62)
        try:
            fx["_track"] = seguir.track(src, info, spans, zoom, fit, *span, frames=frames)
        except Exception:  # noqa: BLE001 - sin seguimiento, la etiqueta se queda quieta sobre la cabeza
            log.exception("No se pudo seguir la cabeza")


PEXELS_NOTE = ("HAY PEXELS: puedes añadir 1 o 2 efectos \"pexels\" (planos de apoyo de 1-2 s de Pexels que "
               "ilustran lo que dice; text: la búsqueda EN INGLÉS, 2 a 4 palabras concretas, p. ej. "
               "\"kyoto temple autumn\", \"airplane window clouds\"). Solo para complementar, nunca en el gancho.")


def _pexels(active: list[dict], assets: dict[str, str], key: str, progress: Progress) -> None:
    """Baja los planos de Pexels que pide el plan y los deja como vídeos de apoyo (`_file`)."""
    for k, fx in enumerate(active):
        if fx.get("type") != "pexels" or fx.get("off"):
            continue
        progress("Buscando planos de apoyo en Pexels", 0.64)
        try:
            p = pexels.clip(str(fx.get("text", "")), key)
        except Exception:  # noqa: BLE001 - sin internet o sin resultados, el reel sale sin ese plano
            log.exception("Pexels no ha respondido")
            p = None
        if p:
            assets[f"pexels{k}"] = str(p)
            fx["_file"] = f"pexels{k}"


def _fixes(dur_in: float, dur_out: float, drops, beats, active: list[dict], clock) -> list[str]:
    """Lo que Imán ha revisado y arreglado por su cuenta, en frases: para que la persona sepa qué ha decidido
    la máquina y lo cambie si no le convence."""
    out = []
    saved = dur_in - dur_out
    if saved >= 1.0:
        out.append(f"He quitado {saved:.0f} s de silencios, muletillas y tomas repetidas"
                   + (f" ({len(drops)} palabras fuera)." if drops else "."))
    if beats:
        out.append(f"En {len(beats)} momentos no cambiaba nada en pantalla: he metido un cambio de plano al ritmo "
                   "de la música.")
    names = {"anillo": "Anillo", "lluvia": "Lluvia", "detras": "Detrás de ti", "fondo": "Fondo", "desenfoque": "Desenfoque",
             "bruto": "Toma en bruto", "pagina": "Página", "viaje": "Itinerario", "titular": "Titular", "cifra": "Cifra",
             "bocadillo": "Bocadillo", "hueca": "Palabra hueca", "marco": "Marco", "lista": "Lista", "paso": "Paso",
             "progreso": "Barra de progreso", "congelado": "Congelado", "moviles": "Móviles", "mosaico": "Mosaico"}
    defaults = {**{k: v[0] for k, v in effects.SEG_KINDS.items()}, **{k: v[0] for k, v in effects.VIDEO_KINDS.items()}}
    for fx in active:
        start, nxt = clock.at(effects.word_of(fx)), fx.get("_next")
        if start is None or nxt is None:
            continue
        want = defaults.get(fx.get("type"), 2.0)
        room = nxt - start - 0.05
        if room < want - 0.3:
            out.append(f"«{names.get(fx.get('type'), fx.get('type'))}» del segundo {start:.1f} duraba {want:.1f} s y solo "
                       f"cabían {room:.1f} s antes del siguiente efecto: lo he acortado para que no se pisen.")
    return out[:8]


def _snap(spans: list, fps: float) -> list:
    """Los cortes, en el reloj de fotogramas: ffmpeg recorta el vídeo por fotogramas enteros y el audio por
    muestras; si el corte cae entre dos fotogramas, cada corte suma hasta uno de más y los subtítulos y efectos
    se van desincronizando poco a poco (casi un segundo en un reel con cien cortes)."""
    fps = fps if fps and fps > 1 else 30.0
    out = []
    for s in spans:
        s.start = round(s.start * fps) / fps
        s.end = round(s.end * fps) / fps
        if out and s.start < out[-1].end:
            s.start = out[-1].end
        if s.end - s.start >= 1.5 / fps:
            out.append(s)
    return out or spans


def _music_grid(choice, workdir: Path, duration: float, drop_at: float | None) -> list[float]:
    """Golpes de la música elegida en segundos del reel (vacío sin música o si tu canción no tiene pulso claro)."""
    if choice in musica.STYLES:
        return musica.style_grid(choice, duration, drop_at)
    song = _music(choice, workdir, duration) if (choice is True or choice == "mia") else None
    if song is None:
        return []
    try:
        return musica.beat_grid(song, duration)
    except Exception:  # noqa: BLE001 - sin golpes, los cortes van como siempre
        log.exception("No se pudo sacar el ritmo de la canción")
        return []


def _hush_windows(silence: list[int], words: list[Word], clock: effects.WordClock) -> list[tuple[float, float]]:
    """Tramos de silencio dramático en el reel: desde justo antes de la frase clave hasta que termina."""
    out = []
    for i in silence:
        a = clock.at(i)
        if a is None or a < 3.0:
            continue
        j = i
        while j < min(len(words) - 1, i + 14) and not words[j].text.rstrip().endswith((".", "!", "?", "…")):
            j += 1
        b = clock.end_of(j)
        if b is not None and b > a:
            out.append((max(0.0, a - 0.15), min(b + 0.1, a + 6.0)))
    return out


def _sfx_events(active: list[dict], clock: effects.WordClock, hook: bool, beats: set[float],
                spans, hush: list[tuple[float, float]] | None = None) -> list[tuple[float, str, float]]:
    """Dónde suena cada efecto: golpe al empezar, un sonido al entrar cada efecto y aire en los cambios."""
    events: list[tuple[float, str, float]] = []
    if hook:
        events += [(0.0, "hit", 1.0), (0.0, "whoosh", 0.5)]  # el gancho se oye desde el milisegundo cero
    for fx in active:
        name = sfx.FOR_EFFECT.get(str(fx.get("type")))
        items = [it for it in fx.get("items") or [] if isinstance(it, dict)]
        if items:  # listas: un pop por cada punto que aparece
            for it in items:
                t = clock.at(int(it.get("at_word", -1)))
                if t is not None:
                    events.append((t, "pop", 0.45))
            continue
        t = clock.at(int(fx.get("word", -1))) if fx.get("word") is not None else None
        if fx.get("type") in ("notificaciones", "chat") and t is not None:  # un "ding" por aviso o mensaje
            n = len([x for x in str(fx.get("text", "")).replace("›", "|").split("|") if x.strip()][:4])
            events += [(t + k * 0.45, "pop", 0.5) for k in range(n)]
            continue
        if name and t is not None:
            events.append((max(0.0, t - (0.25 if name in ("whoosh", "riser") else 0.0)), name, 0.5))
    # Un roce suave en cada cambio de plano, para que el corte se sienta.
    out_t, acc = [], 0.0
    for sp in spans[:-1]:
        acc += sp.duration
        out_t.append(acc)
    beat_out = [t for t, sp in zip(out_t, spans[1:]) if any(abs(sp.start - b) < 1e-3 for b in beats)]
    events += [(t, "air", 0.25) for t in beat_out]
    hush = hush or []
    # En el silencio dramático no suena nada más que la voz, y al acabar vuelve todo con un golpe.
    events = [e for e in events if not any(a - 0.4 <= e[0] < b for a, b in hush)]
    events += [(b, "hit", 0.9) for _, b in hush]
    return sorted(events)


def _preview_async(src: Path, workdir: Path, spans: list[tuple[float, float]]) -> None:
    """Monta en segundo plano una versión pequeña y rápida solo con los cortes (previa.mp4). Si falla, no pasa
    nada: el reel de verdad sigue su camino y la app simplemente no enseña la previa."""
    import threading

    def go():
        try:
            media.rough_cut(src, spans, workdir / "previa.mp4", width=480, crf=30, preset="ultrafast")
        except Exception:  # noqa: BLE001
            log.exception("No se pudo montar la vista previa")

    threading.Thread(target=go, daemon=True).start()


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
    if opts.style != "auto" and opts.style not in STYLES:
        opts.style = "auto"
    progress("Preparando tu vídeo", 0.03)
    (workdir / "previa.mp4").unlink(missing_ok=True)  # la vista previa es de este montaje, no del anterior
    voice_only = opts.mode == "voz"
    notices = []
    if opts.ruido:
        progress("Quitando el ruido de fondo de tu voz", 0.04)
        try:
            src = limpiar.clean_source(src, workdir)
        except Exception:  # noqa: BLE001 - sin limpieza el reel sale igual, con la voz original
            log.exception("No se pudo quitar el ruido")
            notices.append("No he podido quitar el ruido de fondo de este vídeo; tu voz va como estaba.")
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
            media.voice_canvas(src, canvas, visual_cuts(words), clips, bg, size=opts.size)
        src = canvas
    info = media.probe(src)
    if not info.has_audio:
        raise ValueError("El vídeo no tiene audio: Imán necesita oírte para editar")
    if words is None:
        words = _transcribe(src, workdir, cfg, progress)
    transcript_file = workdir / "transcript.json"
    if jsonfile.load(transcript_file) is None:
        jsonfile.save(transcript_file, [w.__dict__ for w in words], indent=1)

    progress("Buscando fallos y el mejor gancho", 0.40)
    aicfg = ai_config(cfg)
    ai_warning = ""
    if plan is not None:
        pass  # plan ya decidido (p. ej. tras un cambio pedido por chat)
    elif aicfg.enabled and words:
        plan = EditPlan()
        try:
            wants = opts.instructions
            if opts.brand and brand.load().copy_prompt():  # el "cta" y los titulares, con tu tono y tus frases
                wants = f"{wants}\n\n{brand.load().copy_prompt()}".strip()
            if cfg.get("pexels_key") and not voice_only:
                wants = f"{wants}\n\n{PEXELS_NOTE}".strip()
            if redes.get(opts.red).note:
                wants = f"{wants}\n\n{redes.get(opts.red).note}".strip()
            if INTENSITY_NOTE.get(opts.intensidad):
                wants = f"{wants}\n\n{INTENSITY_NOTE[opts.intensidad]}".strip()
            plan = ai.plan_edit(aicfg, words, wants, opts.hook_template, opts.pack,
                                takes=take_ranges(words, opts.tomas))
        except Exception as e:  # la IA es un extra: si falla, seguimos y lo avisamos
            ai_warning = ai.error_message(e)
    else:
        plan = EditPlan()
    if opts.hook_title:
        plan.hook_title = opts.hook_title
    if not plan.hook_title and words:
        plan.hook_title = ai.fallback_hook(words)
    # Gancho visual: el efecto de arranque, la entrada de cámara y si el título se pinta.
    has_person = not voice_only and opts.mode == "camara" and not opts.ligero and segment.available()
    if opts.hook and opts.effects:
        key = opts.gancho if opts.gancho in ganchos.GANCHOS else (
            plan.gancho or ganchos.pick(plan.hook_title, opts.pack, opts.comentario, has_person))
        plan.gancho = ganchos.apply(plan, key, has_person, opts.comentario)
        plan.gancho_options = ganchos.alternatives(plan.gancho, opts.pack, has_person)
    else:
        plan.gancho, plan.punch, plan.hook_shown, plan.gancho_options = "", "suave", True, []
    if opts.comentario and opts.effects and not any(fx.get("type") == "comentario" for fx in plan.effects):
        plan.effects.insert(0, {"type": "comentario", "word": 0, "text": opts.comentario[:140],
                                "title": opts.comentario_de, "subtitle": "", "look": "", "until_word": None})
    for kind in ("capitulo", "paso"):  # capítulos y pasos numerados en orden
        numbered = sorted((fx for fx in plan.effects if fx.get("type") == kind), key=lambda fx: int(fx.get("word", 0)))
        for k, fx in enumerate(numbered, 1):
            fx["_n"] = k
    if opts.brand and brand.load().no_emojis:  # marca sin emojis: ni pegatinas ni emojis en los textos
        plan.effects = [fx for fx in plan.effects if fx.get("type") != "objeto"]
        for fx in plan.effects:
            if isinstance(fx.get("text"), str):
                fx["text"] = brand.strip_emojis(fx["text"])
    if opts.ligero:  # ordenador sencillo: fuera lo que recorta o sigue a la persona en cada fotograma
        from .equipo import HEAVY_EFFECTS

        if any(fx.get("type") in HEAVY_EFFECTS for fx in plan.effects):
            notices.append("Modo ligero: he dejado fuera los textos detrás de ti, el anillo y la lluvia para que "
                           "salga rápido en este ordenador. Si quieres todo, en Ajustes pon «Modo ligero» en «no».")
        plan.effects = [fx for fx in plan.effects if fx.get("type") not in HEAVY_EFFECTS]
    if opts.red == "anuncio":  # estilo casero: fuera los efectos más llamativos
        plan.effects = [fx for fx in plan.effects if fx.get("type") not in redes.ANUNCIO_FUERA]

    progress("Cortando silencios y tomas falsas", 0.55)
    rhythm = RHYTHMS[opts.rhythm]
    if len(opts.tomas) > 1 and rhythm.remove_retakes:
        # Una toma grabada aparte que repite otra posterior es una toma falsa: fuera entera, se queda la última.
        for a, b in detect_take_retakes(words, take_ranges(words, opts.tomas)):
            if (a, b) not in plan.drop:
                plan.drop.append((a, b))
                plan.drop_reasons.append("Toma repetida: me quedo con la última")
    spans, drops = keep_spans(words, info.duration, rhythm, plan.drop + plan.cut, plan.restore, plan.pauses)
    if plan.gancho == "mano" and spans and not voice_only:  # la mano tapa el objetivo: fuera el tramo a oscuras
        uncovered = media.dark_start(src)
        if uncovered and spans[0].start < uncovered < spans[0].end - 0.3:
            spans[0] = Span(uncovered, spans[0].end)
    zooms_wanted = plan.zooms if opts.effects else []
    spans = _snap(effects.split_spans(spans, words, zooms_wanted), info.fps)
    choice = opts.music
    if choice == "auto":  # la que recomienda la IA; sin IA, una según el sector
        choice = plan.music if plan.music in musica.STYLES else AUTO_MUSIC.get(opts.pack, "inspiracional")
        plan.music = choice  # para que la app muestre cuál ha elegido
    # Con gancho siempre hay título (si la IA no lo da, sale de tus palabras): la música "explota" al irse.
    drop_at = 2.8 if opts.hook and (plan.hook_title or words) else None
    beats: set[float] = set()
    if opts.auto_zoom and rhythm.cut and not voice_only:
        # Un cambio de plano cada 2-3 s, y a ser posible justo en un golpe de la música.
        pre = sum(s.duration for s in spans)
        grid = _music_grid(choice, workdir, pre, min(drop_at, pre) if drop_at else None)
        spans, beats = effects.beat_spans(spans, words, grid=grid)
        spans = _snap(spans, info.fps)
    zoom = effects.zoom_flags(spans, words, zooms_wanted, opts.auto_zoom and rhythm.cut, beats)
    kept, kept_idx = remap_words(words, spans, drops)
    # Los tramos que se quedan, para la pestaña «Sin silencios» (tu vídeo tal cual, solo con los cortes).
    jsonfile.save(workdir / "tramos.json", [[round(s.start, 3), round(s.end, 3)] for s in spans])
    (workdir / "sin-silencios.mp4").unlink(missing_ok=True)
    if not voice_only:  # vista previa al instante: tu vídeo ya cortado, pequeño, mientras se monta el reel entero
        _preview_async(src, workdir, [(s.start, s.end) for s in spans])
    out_duration = sum(s.duration for s in spans)
    if not plan.hook_title and kept:
        plan.hook_title = ai.fallback_hook(kept)
    hand_frames: list[dict] = []
    found: list = []
    if opts.effects and opts.gestures and not voice_only and hands.available():
        progress("Mirando tus manos", 0.58)
        try:
            hand_frames = gestos.reel_frames(hands.track(src, workdir / "manos.json"), spans, zoom, info, opts.fit)
            found = gestos.gestures(hand_frames)
        except Exception:  # las manos son un extra: si falla el modelo, los efectos salen sin seguirlas
            hand_frames, found = [], []
        plan.effects = gestos.auto_effects(plan.effects, found, effects.WordClock(kept, kept_idx))
    if voice_only:  # no hay cara que poner en el círculo ni persona que recortar
        plan.effects = [fx for fx in plan.effects if fx.get("type") not in effects.PERSON_TYPES]
    else:
        plan.effects = effects.auto_broll(plan.effects, kept_idx, len(clips))
    if plan.caption_style not in STYLES:
        plan.caption_style = packs.get(opts.pack).style or "impacto"  # sin IA, el del sector
    jsonfile.save(workdir / "plan.json", plan.to_dict(), indent=1)

    active = [dict(fx) for fx in plan.effects if not fx.get("off")]  # los que el creador ha apagado no salen
    active = effects.dedupe_overlaps(active, effects.WordClock(kept, kept_idx),  # nunca dos a la vez
                                     DEDUPE_GAP.get(opts.intensidad, 1.0))
    if not voice_only:
        _face_positions(active, src, spans, effects.WordClock(kept, kept_idx), workdir)
    gestos.attach(active, found, hand_frames, effects.WordClock(kept, kept_idx))
    effects.assign_next(active, effects.WordClock(kept, kept_idx))
    frames = None
    if opts.fit == "recortar" and not voice_only:
        try:
            frames = seguir.framing(src, info, spans)  # vídeo horizontal: el recorte vertical te sigue
        except Exception:  # noqa: BLE001 - sin encuadre inteligente, recorte centrado como siempre
            log.exception("No se pudo encuadrar")
    if opts.effects and not voice_only:
        _follow_head(active, src, info, spans, zoom, opts.fit, effects.WordClock(kept, kept_idx), out_duration,
                     progress, frames)
        for fx in active:  # con el recorte de persona, la mitad de atrás del anillo pasa por detrás de ti
            if fx.get("type") in ("anillo", "lluvia") and segment.available():
                fx["_behind"] = True
    kit = brand.load() if opts.brand else None
    style_key = opts.style if opts.style in STYLES else plan.caption_style
    style = brand.apply(STYLES[style_key], kit) if kit else STYLES[style_key]
    style = captions.sized(style, opts.letra)
    red = redes.get(opts.red)
    if red.caption_y and style.y > red.caption_y:  # la zona de abajo la tapa el texto de la red
        style = replace(style, y=red.caption_y)
    # El cierre de marca va DESPUÉS de lo que dices, para no taparte la llamada a la acción.
    tail = effects.END_CARD if kit is not None and kit.active and kit.end_card and out_duration > 1 else 0.0
    total = out_duration + tail
    end_lines, end_window = effects.end_card_events(kit, style, total)
    ass_path = None

    # Subtítulos en otro idioma: las palabras (misma línea de tiempo), el gancho y los textos de los efectos.
    sub_words, sub_hook, sub_active = kept, plan.hook_title, active
    if opts.idioma and aicfg.enabled and kept:
        progress("Traduciendo los textos", 0.62)
        try:
            from . import traducir

            sub_words, sub_hook, sub_active = traducir.localized(aicfg, kept, plan.hook_title, active, opts.idioma)
        except Exception as e:  # noqa: BLE001 - sin traducción, el reel sale en el idioma original
            notices.append(f"No he podido traducir los textos: {ai.error_message(e)}")

    def write_subs() -> Path:
        emphasis_out = {j for j, i in enumerate(kept_idx) if i in set(plan.emphasis)} if sub_words is kept else set()
        fx_lines, fx_windows = ([], [])
        if opts.effects:
            fx_lines, fx_windows = effects.build_effects(
                sub_active, effects.WordClock(kept, kept_idx), style, out_duration, info.duration
            )
        ass = build_ass(
            sub_words if opts.captions else [], style, total,
            sub_hook if (opts.hook and plan.hook_shown) else "", emphasis_out,
            extra_events=fx_lines + end_lines + ([WATERMARK.format(end=_ts(total))] if opts.watermark else [])
            + (packfx.progress_bar_events(out_duration, style) if opts.barra else []),
            hide=fx_windows + ([end_window] if end_window else []),
        )
        p = workdir / "subs.ass"
        p.write_text(ass, encoding="utf-8")
        return p

    if opts.captions or opts.hook or opts.watermark or end_lines or opts.barra:
        ass_path = write_subs()

    progress("Montando tu reel", 0.65)
    final = workdir / "reel.mp4"
    # Cada montaje escribe sus intermedios con nombre propio: si otro montaje (o el reproductor) tiene abiertos
    # los del anterior, no se mezclan ni se leen a medio escribir.
    run_id = uuid.uuid4().hex[:8]
    out = workdir / f"reel-{run_id}.tmp.mp4"
    overlays = []
    if opts.effects:
        assets = {str(i + 1): str(p) for i, p in enumerate(clips)}
        if cfg.get("pexels_key") and not voice_only:
            _pexels(active, assets, cfg["pexels_key"], progress)
        overlays = effects.video_ops(active, effects.WordClock(kept, kept_idx), out_duration,
                                     lambda t: _source_time(spans, t), assets, style.accent, face=opts.circulo)
    overlays += effects.brand_ops(kit, total)
    clock = effects.WordClock(kept, kept_idx)
    segs = effects.seg_ops(active, clock, out_duration, {str(i + 1): str(p) for i, p in enumerate(clips)}) if opts.effects else []
    whole = _background_op(opts, workdir, kit, out_duration) if opts.mode == "camara" else None
    if whole:
        segs = [whole, *segs]  # va primero: los efectos de fondo del plan se pintan encima
    hush = _hush_windows(plan.silence, words, clock) if (opts.sfx or opts.music) else []
    trans = media.transition_plan(spans) if opts.transiciones and not voice_only else {}
    sound = None
    if opts.sfx:
        evs = _sfx_events(active if opts.effects else [], clock, bool(opts.hook and plan.hook_title), beats, spans,
                          hush)
        starts = [sum(sp.duration for sp in spans[:i]) for i in range(len(spans))]
        evs = sorted(evs + [(starts[i], "whoosh" if k == "whip" else "click", 0.45) for i, k in trans.items()])
        if evs:
            sound = sfx.bed(evs, total, workdir / "sfx.wav")
    # La música "explota" justo cuando se va el texto del gancho.
    music = _music(choice, workdir, total, min(drop_at, out_duration) if drop_at else None)
    # El zoom de entrada necesita medio segundo; el gancho decide si es suave, seco o ninguno.
    punch: bool | str = opts.punch and not voice_only and out_duration > 1.0
    if punch:
        punch = (plan.punch if plan.gancho else "suave") or False
    look = opts.look
    if look == "auto":
        look = plan.color if plan.color in media.LOOKS else AUTO_LOOK.get(opts.pack, "natural")
        plan.color = look
    av = dict(sfx_bed=sound, music=music, punch=punch, hush=hush, look=look, transitions=trans, framing=frames)
    # En un ordenador sencillo, x264 «faster» tarda la mitad que «medium» y la diferencia no se ve en el móvil.
    final_preset = "faster" if opts.ligero else "medium"
    warnings = notices
    done = False
    if segs and segment.available():
        # Dos pasadas: primero el reel limpio, luego la persona recortada encima de lo que va detrás.
        base, mask = workdir / f"base-{run_id}.tmp.mp4", workdir / f"mask-{run_id}.tmp.mp4"
        try:
            media.render(src, base, spans, info, None, opts.size, opts.fit, opts.voice, zoom,
                         preset="veryfast", tail=tail, **av)
            progress("Recortándote del fondo", 0.80)
            segment.person_masks(base, mask, [(o.start, o.end) for o in segs])
            behind = workdir / "behind.ass"
            behind.write_text(build_ass([], style, total,
                                        extra_events=effects.behind_events(active, clock, style,
                                                                           out_duration)), encoding="utf-8")
            progress("Montando tu reel", 0.90)
            media.composite(base, mask, src, out, behind, ass_path, segs, overlays, opts.size, preset=final_preset)
            done = True
        except Exception as e:  # noqa: BLE001 - sin los efectos de detrás, el reel sale igual
            log.warning("Falla la pasada con la persona recortada: %s", e)
            warnings.append("No he podido recortarte del fondo en este vídeo; el reel sale sin el cambio de fondo.")
            # El anillo y el confeti vuelven enteros delante: el ASS se hizo con la mitad de atrás aparte.
            if any(fx.pop("_behind", None) for fx in active) and ass_path is not None:
                ass_path = write_subs()
        finally:
            for p in (base, mask):
                p.unlink(missing_ok=True)
    if not done:
        try:
            media.render(src, out, spans, info, ass_path, opts.size, opts.fit, opts.voice, zoom, overlays=overlays,
                         preset=final_preset, tail=tail, **av)
        except Exception as e:  # noqa: BLE001 - se reintenta sin los efectos de vídeo, que son lo más delicado
            if not (overlays or trans):
                raise
            log.warning("Falla el montaje con efectos de vídeo: %s", e)
            warnings.append("Un efecto de vídeo ha fallado y lo he quitado para que tu reel salga.")
            media.render(src, out, spans, info, ass_path, opts.size, opts.fit, opts.voice, zoom, overlays=[],
                         preset=final_preset, tail=tail, **{**av, "transitions": None})
    if red.loop:
        try:
            looped = redes.loop(out, out.with_name(f"bucle-{out.name}"))
            if looped != out:
                out.unlink(missing_ok=True)
                out = looped
        except Exception as e:  # noqa: BLE001 - sin bucle, el reel sale igual
            log.warning("No sale el bucle: %s", e)
    out = _publish(out, final)
    media.thumbnail(out, workdir / "reel.jpg", min(0.6, out_duration / 2))
    progress("Listo", 1.0)
    return EditResult(
        video=out, plan=plan, duration_in=info.duration, duration_out=total,
        removed_words=[words[i].text for i in sorted(drops)],
        cuts=sum(1 for a, b in zip(spans, spans[1:]) if abs(a.end - b.start) > 1e-3),
        ai_warning=ai_warning,
        notices=warnings,
        checks=pre_publish(opts, plan, kept, total, active, kit, music is not None),
        fixes=_fixes(info.duration, out_duration, drops, beats, active, clock),
        viral=viral.score(plan, kept, total, active, captions=opts.captions, music=music is not None, hook=opts.hook,
                          cta=any(fx.get("type") == "cta" for fx in active) or bool(kit and kit.active and kit.end_card)),
    )
