"""Reel «antes y después» automático: tu toma tal cual y, de un latigazo, el reel ya montado.

Para enseñar tu proceso (o el de Imán) en un reel: 4 s de la toma original, con «ANTES» encima y un poco
apagada, y de golpe 7 s del reel terminado con «DESPUÉS». Sale de la carpeta del reel, sin volver a editar nada.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import media
from .textfit import font_path

BEFORE_S = 4.0
AFTER_S = 7.0
W, H = 1080, 1920


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")


def _label(text: str, color: str, font: Path, y: int = 180) -> str:
    return (f"drawtext=fontfile='{_esc(str(font))}':text='{_esc(text)}':fontsize=110:fontcolor={color}:"
            f"borderw=6:bordercolor=black@0.85:x=(w-text_w)/2:y={y}")


def before_after(original: Path, reel: Path, dst: Path, before_s: float = BEFORE_S, after_s: float = AFTER_S,
                 accent: str = "#FFD60A") -> Path:
    d_in, d_out = media.duration_of(original), media.duration_of(reel)
    before_s = max(1.0, min(before_s, d_in or before_s))
    after_s = max(1.0, min(after_s, d_out or after_s))
    font = font_path("Anton")
    fit = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps=30,format=yuv420p")
    parts = [
        f"[0:v]trim=0:{before_s:.3f},setpts=PTS-STARTPTS,{fit},eq=saturation=0.55:brightness=-0.04,"
        f"{_label('ANTES', 'white', font)}[b]",
        f"[1:v]trim=0:{after_s:.3f},setpts=PTS-STARTPTS,{fit},{_label('DESPUÉS', accent, font)}[a]",
        f"[b][a]xfade=transition=wipeleft:duration=0.25:offset={before_s - 0.25:.3f}[v]",
        f"[0:a]atrim=0:{before_s:.3f},asetpts=PTS-STARTPTS,volume=0.9[ba]",
        f"[1:a]atrim=0:{after_s:.3f},asetpts=PTS-STARTPTS[aa]",
        "[ba][aa]acrossfade=d=0.25[a]",
    ]
    script = dst.parent / f"{dst.stem}.filters.txt"
    script.write_text(";\n".join(parts), encoding="utf-8")
    tmp = dst.with_suffix(".tmp.mp4")
    cmd = [media.FFMPEG, "-y", "-v", "error", "-i", str(original), "-i", str(reel), *media.filter_script_args(script),
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(tmp)]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    script.unlink(missing_ok=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falló:\n{res.stderr[-2000:]}")
    tmp.replace(dst)
    return dst
