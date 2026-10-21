"""Todo lo que toca ffmpeg: analizar, extraer audio y renderizar el reel."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import Span

FONTS_DIR = Path(__file__).parent / "assets" / "fonts"
HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}


@dataclass
class MediaInfo:
    width: int
    height: int
    duration: float
    fps: float
    has_audio: bool
    hdr: bool


def probe(path: Path) -> MediaInfo:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if v is None:
        raise ValueError("El archivo no tiene pista de vídeo")
    w, h = int(v["width"]), int(v["height"])
    rotation = 0
    for sd in v.get("side_data_list", []):
        if "rotation" in sd:
            rotation = abs(int(sd["rotation"]))
    if rotation in (90, 270):
        w, h = h, w
    num, _, den = v.get("avg_frame_rate", "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    return MediaInfo(
        width=w,
        height=h,
        duration=float(data["format"].get("duration") or v.get("duration") or 0),
        fps=fps or 30.0,
        has_audio=any(s["codec_type"] == "audio" for s in data["streams"]),
        hdr=v.get("color_transfer") in HDR_TRANSFERS,
    )


def extract_audio(src: Path, dst: Path) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(dst)],
        check=True,
    )
    return dst


VOICE_CHAIN = (
    "highpass=f=80,lowpass=f=14000,afftdn=nr=12:nf=-40:tn=1,"
    "equalizer=f=3000:t=q:w=1.2:g=2.5,"
    "acompressor=threshold=-20dB:ratio=3:attack=8:release=120:makeup=2"
)

SIZES = {"1080": (1080, 1920), "4k": (2160, 3840)}


def _filter_path(p: Path) -> str:
    # Escapado para usar rutas dentro de un filtergraph.
    return str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def build_filtergraph(
    spans: list[Span], info: MediaInfo, ass_path: Path | None, size: str = "1080", fit: str = "recortar",
    voice: bool = True,
) -> str:
    W, H = SIZES[size]
    parts = []
    labels = []
    for i, sp in enumerate(spans):
        d = sp.duration
        fade = min(0.012, d / 4)
        parts.append(f"[0:v]trim=start={sp.start:.3f}:end={sp.end:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(
            f"[0:a]atrim=start={sp.start:.3f}:end={sp.end:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:d={fade:.3f},afade=t=out:st={d - fade:.3f}:d={fade:.3f}[a{i}]"
        )
        labels.append(f"[v{i}][a{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(spans)}:v=1:a=1[vc][ac]")

    chain = "[vc]"
    if info.hdr:
        # Mapeo de tonos HDR (iPhone) -> SDR BT.709.
        chain += (
            "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
            "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,"
        )
    if fit == "fondo":
        parts.append(f"{chain}split[bg0][fg0]")
        parts.append(
            f"[bg0]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:2,eq=brightness=-0.08[bg]"
        )
        parts.append(f"[fg0]scale={W}:{H}:force_original_aspect_ratio=decrease[fg]")
        parts.append("[bg][fg]overlay=(W-w)/2:(H-h)/2[vf]")
    else:
        parts.append(f"{chain}scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}[vf]")
    tail = "[vf]fps=30,setsar=1"
    if ass_path is not None:
        tail += f",ass=filename='{_filter_path(ass_path)}':fontsdir='{_filter_path(FONTS_DIR)}'"
    parts.append(tail + ",format=yuv420p[vout]")
    audio = "[ac]"
    if voice:
        # Voz más limpia: fuera graves y zumbidos, menos ruido de fondo, nivel más estable.
        audio += VOICE_CHAIN + ","
    parts.append(f"{audio}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
    return ";\n".join(parts)


def render(
    src: Path,
    dst: Path,
    spans: list[Span],
    info: MediaInfo,
    ass_path: Path | None,
    size: str = "1080",
    fit: str = "recortar",
    voice: bool = True,
    preset: str = "medium",
) -> Path:
    graph = build_filtergraph(spans, info, ass_path, size, fit, voice)
    script = dst.with_suffix(".filters.txt")
    script.write_text(graph)
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-filter_complex_script", str(script),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", preset, "-crf", "18", "-profile:v", "high",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falló:\n{res.stderr[-2000:]}")
    return dst


def thumbnail(src: Path, dst: Path, t: float = 0.5) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-q:v", "3", str(dst)],
        check=True,
    )
    return dst
