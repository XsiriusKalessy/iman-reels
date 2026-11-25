"""Tráileres y anuncios de cine para lanzamientos y productos, hechos con tus imágenes.

Sin generar vídeo con IA (eso cuesta dinero o pide un ordenador muy potente): cada foto se mueve en 2.5D
(iman/paralaje.py), entre carteles de cine en negro («ESTE VERANO», «UN VIAJE»…), con música de tráiler de Imán,
golpes, latigazos y una subida antes del título. Al final, el título, la fecha y la llamada a la acción con tu
marca. Los textos los propone la IA (si la hay) o salen de lo que escribes.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import brand as brand_mod
from . import media, musica, sfx
from .textfit import font_path

log = logging.getLogger(__name__)
W, H, FPS = 1080, 1920, 30
INTRO, CARD, SHOT, TITLE, END = 0.6, 1.5, 2.2, 3.0, 2.8
ESTILOS = {"epico": "trailer", "misterio": "misterio", "emotivo": "emotiva", "accion": "phonk", "lujo": "piano_cine"}
STILL = (".jpg", ".jpeg", ".png", ".webp")

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {"type": "array", "items": {"type": "string"},
                  "description": "De 3 a 6 carteles de tráiler, de 1 a 4 palabras cada uno, que se leen seguidos."},
        "title": {"type": "string", "description": "El título final, corto."},
        "final": {"type": "string", "description": "Línea bajo el título: fecha o llamada a la acción."},
    },
    "required": ["cards", "title", "final"],
    "additionalProperties": False,
}
SCRIPT_SYSTEM = """Escribes los carteles de un tráiler de cine vertical (para reels) que anuncia un lanzamiento,
un producto, un viaje o un evento del creador. Carteles en negro entre imágenes, de 1 a 4 palabras, en mayúsculas,
que juntos forman una frase con tensión que crece ("ESTE OTOÑO" / "30 VIAJEROS" / "UN SOLO DESTINO" / ...).
Nada de datos inventados: usa solo lo que te cuentan. El título es el nombre de lo que se anuncia; "final" es la
fecha o la llamada a la acción que te dan (si no hay, una invitación corta)."""


def script(title: str, tagline: str = "", fecha: str = "", cta: str = "", idea: str = "", aicfg=None) -> dict:
    """Los carteles del tráiler: con IA si la hay; si no, salen de lo que ha escrito el creador."""
    title = " ".join(title.split())[:60] or "PRÓXIMAMENTE"
    final = " · ".join(x for x in (" ".join(fecha.split())[:40], " ".join(cta.split())[:60]) if x)
    if aicfg is not None and getattr(aicfg, "enabled", False):
        from . import ai

        try:
            user = (f"Qué se anuncia: {title}\nFrase: {tagline}\nFecha: {fecha}\nLlamada a la acción: {cta}\n"
                    f"Más contexto: {idea}")
            data = ai._ask_json(aicfg, SCRIPT_SYSTEM, user, SCRIPT_SCHEMA)
            cards = [" ".join(str(c).split())[:40].upper() for c in data.get("cards") or [] if str(c).strip()][:6]
            if len(cards) >= 2:
                return {"cards": cards, "title": str(data.get("title") or title)[:60],
                        "final": str(data.get("final") or final)[:80]}
        except Exception as e:  # noqa: BLE001
            log.warning("Sin IA para los carteles del tráiler: %s", e)
    import re

    cards = []
    for part in re.split(r"[,.;:!?…]+", tagline):  # primero por frases, luego en trozos de 2-3 palabras
        words = part.split()
        while words and len(cards) < 5:
            take = len(words) if len(words) <= 3 else 2 if len(words) == 4 else 3
            cards.append(" ".join(words[:take]).upper())
            words = words[take:]
    if not cards:
        cards = ["MUY PRONTO", "ALGO NUEVO", "LLEGA"]
    if fecha and fecha.upper() not in cards:
        cards.insert(0, fecha.upper()[:30])
    return {"cards": cards[:6], "title": title, "final": final or "MUY PRONTO"}


def _font(family: str, size: int):
    from PIL import ImageFont

    return ImageFont.truetype(str(font_path(family)), size)


def _spaced(draw, xy, text, font, fill, spacing):
    """Texto con letras separadas (como en los carteles de cine), centrado en x."""
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x, y = xy[0] - total / 2, xy[1]
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + spacing


def card(text: str, dst: Path, accent: str = "#E8C872", big: bool = False, sub: str = "", logo: Path | None = None,
         family: str = "Bebas Neue") -> Path:
    """Cartel en negro: texto en mayúsculas con brillo suave (más grande en el título)."""
    img = Image.new("RGB", (W, H), "#050506")
    glow = Image.new("RGB", (W, H), "#050506")
    gd = ImageDraw.Draw(glow)
    lines, size = [], 210 if big else 150
    while True:
        font = _font(family, size)
        words, lines, cur = text.split(), [], ""
        for w in words:
            cand = f"{cur} {w}".strip()
            if gd.textlength(cand, font=font) + 12 * len(cand) <= W - 140 or not cur:
                cur = cand
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) <= (3 if big else 2) or size < 70:
            break
        size = int(size * 0.88)
    lh = int(size * 1.02)
    y0 = (H - lh * len(lines)) // 2 - (60 if sub else 0)
    for layer, color in ((glow, accent), (img, "#F4F1EA")):
        d = ImageDraw.Draw(layer)
        for k, ln in enumerate(lines):
            _spaced(d, (W / 2, y0 + k * lh), ln, font, color, 14 if not big else 10)
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(28)), 0.35)
    d = ImageDraw.Draw(img)
    for k, ln in enumerate(lines):  # el texto nítido otra vez, encima del brillo
        _spaced(d, (W / 2, y0 + k * lh), ln, font, "#F4F1EA", 14 if not big else 10)
    if sub:
        sf = _font("Figtree SemiBold", 52)
        d.text((W / 2, y0 + lh * len(lines) + 70), sub, font=sf, fill=accent, anchor="ma")
    if logo is not None and logo.exists():
        try:
            lg = Image.open(logo).convert("RGBA")
            lg.thumbnail((260, 160))
            img.paste(lg, ((W - lg.width) // 2, H - 360), lg)
        except Exception:  # noqa: BLE001
            pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, quality=94)
    return dst


def timeline(cards: list[str], shots: list[Path]) -> list[tuple[str, object, float]]:
    """El orden del tráiler: negro, y carteles y planos alternos (los planos que sobran van seguidos al final,
    más rápidos), título y cierre. Devuelve (tipo, qué, duración)."""
    out: list[tuple[str, object, float]] = [("negro", None, INTRO)]
    shots = list(shots)
    for k, c in enumerate(cards):
        out.append(("cartel", c, CARD))
        if shots:
            out.append(("plano", shots.pop(0), SHOT))
    fast = max(0.9, SHOT * 0.55)
    for s in shots[:8]:  # el montaje rápido antes del título
        out.append(("plano", s, fast))
    out.append(("titulo", None, TITLE))
    out.append(("final", None, END))
    return out


def render(photos: list[Path], dst: Path, title: str, tagline: str = "", fecha: str = "", cta: str = "",
           idea: str = "", estilo: str = "epico", voice: Path | None = None, kit=None, aicfg=None,
           progress=lambda msg, pct: None) -> dict:
    """Monta el tráiler en `dst` (mp4 vertical) y devuelve los textos y la duración."""
    from . import paralaje

    work = dst.parent / "trailer"
    work.mkdir(parents=True, exist_ok=True)
    progress("Escribiendo los carteles", 0.05)
    sc = script(title, tagline, fecha, cta, idea, aicfg)
    accent = kit.primary if kit is not None and brand_mod.is_hex(getattr(kit, "primary", "") or "") else "#E8C872"
    logo = kit.logo_path if kit is not None and getattr(kit, "active", False) else None
    plan = timeline(sc["cards"], photos)
    inputs, chains, events, t = [], [], [], 0.0
    shots = [p for kind, p, _d in plan if kind == "plano"]
    for k, (kind, what, d) in enumerate(plan):
        progress("Moviendo tus imágenes" if kind == "plano" else "Diseñando los carteles", 0.1 + 0.6 * k / len(plan))
        i = k  # una entrada por tramo, en orden
        if kind == "negro":
            inputs += ["-f", "lavfi", "-t", f"{d:.3f}", "-i", f"color=c=black:s={W}x{H}:r={FPS}"]
            chains.append(f"[{i}:v]setsar=1,format=yuv420p[s{k}]")
        elif kind == "plano":
            p = Path(what)
            clip = paralaje.cached(p, d + 0.2) if p.suffix.lower() in STILL else p
            inputs += ["-i", str(clip)]
            chains.append(f"[{i}:v]trim=duration={d:.3f},setpts=PTS-STARTPTS,fps={FPS},scale={W}:{H}:force_original_"
                          f"aspect_ratio=increase,crop={W}:{H},setsar=1,eq=contrast=1.08:saturation=0.9,"
                          f"fade=t=in:st=0:d=0.12,fade=t=out:st={max(0.0, d - 0.12):.3f}:d=0.12,format=yuv420p[s{k}]")
            events.append((max(0.0, t - 0.2), "whoosh", 0.45))
        else:
            if kind == "cartel":
                img = card(str(what), work / f"cartel-{k:02d}.jpg", accent)
            elif kind == "titulo":
                img = card(sc["title"].upper(), work / "titulo.jpg", accent, big=True)
                events.append((max(0.0, t - 1.1), "riser", 0.7))
            else:
                img = card(sc["title"].upper(), work / "final.jpg", accent, sub=sc["final"], logo=logo)
            frames = int(round(d * FPS))
            inputs += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(img)]
            zoom = 0.0009 if kind != "final" else 0.0003
            chains.append(f"[{i}:v]scale={W}:{H},zoompan=z='1+{zoom}*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                          f"d={frames}:s={W}x{H}:fps={FPS},trim=duration={d:.3f},setsar=1,"
                          f"fade=t=in:st=0:d=0.18,fade=t=out:st={max(0.0, d - 0.25):.3f}:d=0.25,format=yuv420p[s{k}]")
            events.append((t, "hit" if kind != "final" else "impact", 0.9 if kind == "titulo" else 0.7))
        t += d
    total = t
    progress("Poniendo la música de tráiler", 0.75)
    title_at = sum(d for kind, _w, d in plan[:-2])
    music = musica.render(ESTILOS.get(estilo, "trailer"), total + 0.5, work / "musica.wav", seed=7,
                          drop_at=min(title_at, total))
    bed = sfx.bed(events, total, work / "sfx.wav")
    concat = "".join(f"[s{k}]" for k in range(len(plan)))
    graph = ";\n".join(chains + [f"{concat}concat=n={len(plan)}:v=1:a=0[vout]"])
    a_music, a_sfx = len(plan), len(plan) + 1
    inputs += ["-i", str(music), "-i", str(bed)]
    audio = (f"[{a_music}:a]atrim=duration={total:.3f},aresample=48000,aformat=channel_layouts=stereo,volume=0.5,"
             f"afade=t=in:d=0.4,afade=t=out:st={max(0.0, total - 1.2):.3f}:d=1.2[mu];"
             f"[{a_sfx}:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.6[sx]")
    if voice is not None and voice.exists():  # tu voz en off: la música se aparta cuando hablas
        a_voice = len(plan) + 2
        inputs += ["-i", str(voice)]
        audio += (f";[{a_voice}:a]adelay={int(INTRO * 1000)}|{int(INTRO * 1000)},aresample=48000,"
                  f"aformat=channel_layouts=stereo,{media.VOICE_CHAIN},asplit[vk][vs];"
                  f"[mu][vs]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=500[md];"
                  f"[vk][md][sx]amix=inputs=3:duration=longest:normalize=0[mix]")
    else:
        audio += ";[mu][sx]amix=inputs=2:duration=longest:normalize=0[mix]"
    audio += f";[mix]atrim=duration={total:.3f},loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"
    script_file = work / "trailer.filters.txt"
    script_file.write_text(graph + ";\n" + audio, encoding="utf-8")
    progress("Montando el tráiler", 0.85)
    tmp = dst.with_name(f"{dst.stem}.tmp.mp4")
    cmd = [media.FFMPEG, "-y", "-v", "error", *inputs, *media.filter_script_args(script_file), "-map", "[vout]",
           "-map", "[aout]", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(tmp)]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falló:\n{res.stderr[-2000:]}")
    tmp.replace(dst)
    media.thumbnail(dst, dst.with_suffix(".jpg"), min(total - 0.5, title_at + 0.8))
    progress("Listo", 1.0)
    return {**sc, "duration": round(total, 2), "shots": len(shots)}
