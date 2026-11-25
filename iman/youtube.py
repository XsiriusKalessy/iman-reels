"""Traer un vídeo tuyo de YouTube para sacarle reels (modo «vídeo largo → varios reels»).

Solo para tu propio contenido (o con permiso de quien lo grabó): la app lo pide marcar antes. Se descarga en tu
ordenador con yt-dlp (licencia libre «Unlicense»), en 1080 como mucho, y se usa como si lo hubieras subido.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import media

URL = re.compile(r"^https?://(www\.|m\.|music\.)?(youtube\.com/(watch\?|shorts/|live/|embed/)|youtu\.be/)\S+$", re.I)
MAX_SECONDS = 3 * 3600


def valid(url: str) -> bool:
    return bool(URL.match((url or "").strip()))


def available() -> bool:
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return False
    return True


def download(url: str, folder: Path, progress=lambda pct: None) -> Path:
    """Descarga el vídeo a `folder/original.mp4` y devuelve la ruta."""
    if not valid(url):
        raise ValueError("Ese enlace no es de un vídeo de YouTube")
    import yt_dlp

    folder.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if d.get("status") == "downloading" and d.get("total_bytes"):
            progress(min(1.0, d.get("downloaded_bytes", 0) / d["total_bytes"]))

    def short_enough(info, *, incomplete):
        dur = info.get("duration")
        if dur and dur > MAX_SECONDS:
            return "El vídeo dura más de 3 horas: córtalo o súbelo por partes"
        return None

    opts = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(folder / "original.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "match_filter": short_enough,
        "ffmpeg_location": str(Path(media.FFMPEG).parent) if Path(media.FFMPEG).parent != Path(".") else None,
    }
    with yt_dlp.YoutubeDL({k: v for k, v in opts.items() if v is not None}) as y:
        y.download([url.strip()])
    out = next((p for p in sorted(folder.glob("original.*")) if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")),
               None)
    if out is None:
        raise ValueError("No he podido descargar ese vídeo de YouTube (¿es privado o tiene restricción de edad?)")
    return out
