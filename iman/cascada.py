"""Método cascada: de una grabación larga, en un clic, todo lo que se puede publicar.

Los reels ya salen del modo «vídeo largo». Aquí se saca el resto:
- el vídeo largo limpio (sin silencios ni tomas falsas), para YouTube;
- el audio para el podcast (voz nivelada a -16 LUFS, el estándar de los podcasts), en MP3;
- un carrusel de citas con tu marca (frases tuyas que se guardan y se comparten);
- la newsletter y el texto del episodio del podcast.
Todo en un zip. Sin IA, las citas y la newsletter salen de tus propias frases.
"""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

from . import ai, brand, kit, media
from .config import ai_config
from .models import Word
from .rhythm import RHYTHMS, keep_spans, phrases


def fallback_texts(words: list[Word]) -> dict:
    rows = [p.text.strip() for p in phrases(words, set()) if 6 <= len(p.text.split()) <= 25]
    quotes = sorted(rows, key=lambda r: -len(r))[:5]
    body = "\n\n".join(rows[:12])
    first = rows[0] if rows else "Mi nuevo vídeo"
    return {"quotes": quotes, "title": "Frases para guardar", "subject": first[:70],
            "newsletter": f"Hola:\n\nEsta semana he grabado un vídeo y te dejo lo más importante.\n\n{body}\n\n"
                          "Si te ha servido, respóndeme a este correo y cuéntame.",
            "podcast": f"{first[:70]}\n\nEpisodio sacado de mi último vídeo."}


def podcast_audio(src: Path, dst: Path) -> Path:
    """Voz limpia y nivelada para podcast: filtro de graves, compresión suave y -16 LUFS con pico a -1,5 dB."""
    subprocess.run([media.FFMPEG, "-v", "error", "-y", "-i", str(src), "-vn",
                    "-af", "highpass=f=70,acompressor=threshold=-20dB:ratio=2.5:attack=10:release=200,"
                           "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "128k", str(dst)], check=True)
    return dst


def render(src: Path, words: list[Word], outdir: Path, cfg: dict, progress=lambda msg, pct: None) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    progress("Limpiando el vídeo largo", 0.05)
    info = media.probe(src)
    spans, _ = keep_spans(words, info.duration, RHYTHMS["natural"])
    largo = media.rough_cut(src, [(s.start, s.end) for s in spans], outdir / "video-largo.mp4", width=0, crf=19,
                            preset="veryfast")
    progress("Preparando el audio del podcast", 0.45)
    podcast_audio(largo, outdir / "podcast.mp3")
    progress("Escribiendo las citas y la newsletter", 0.6)
    texts = {}
    aicfg = ai_config(cfg)
    if aicfg.enabled and words:
        try:
            texts = ai.cascade_texts(aicfg, words)
        except Exception:  # noqa: BLE001 - sin IA, con tus frases
            texts = {}
    if not texts.get("quotes"):
        texts = {**fallback_texts(words), **{k: v for k, v in texts.items() if v}}
    quotes = [" ".join(q.split()) for q in texts["quotes"] if q.strip()][:6]
    progress("Dibujando el carrusel de citas", 0.75)
    frames = [media.thumbnail(src, outdir / f"frame-{k}.jpg", info.duration * f)
              for k, f in enumerate((0.15, 0.35, 0.55, 0.75))]
    b = brand.load()
    slides = [{"title": texts.get("title") or "Frases para guardar", "body": ""}]
    slides += [{"title": f"«{q}»", "body": ""} for q in quotes]
    slides.append({"title": b.cta.strip() or "Guárdalo para después", "body": "Y compártelo con quien lo necesite."})
    names = kit.render({"carousel": slides, "stories": []}, outdir / "citas", b, frames)
    for f in frames:
        f.unlink(missing_ok=True)
    (outdir / "newsletter.txt").write_text(f"Asunto: {texts.get('subject', '')}\n\n{texts.get('newsletter', '')}\n",
                                           encoding="utf-8")
    (outdir / "podcast.txt").write_text(texts.get("podcast", "") + "\n", encoding="utf-8")
    progress("Juntándolo todo", 0.95)
    files = ["video-largo.mp4", "podcast.mp3", "podcast.txt", "newsletter.txt"]
    with zipfile.ZipFile(outdir / "cascada.zip", "w") as z:
        for n in files:
            z.write(outdir / n, n, compress_type=zipfile.ZIP_STORED if n.endswith((".mp4", ".mp3")) else
                    zipfile.ZIP_DEFLATED)
        for n in names["carousel"]:
            z.write(outdir / "citas" / n, f"carrusel-citas/{n}")
    return {"files": files, "carousel": names["carousel"], "quotes": quotes, "subject": texts.get("subject", ""),
            "duration": round(media.probe(largo).duration, 1)}
