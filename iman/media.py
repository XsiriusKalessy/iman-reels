"""Todo lo que toca ffmpeg: analizar, extraer audio y renderizar el reel."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .models import Span

FONTS_DIR = Path(__file__).parent / "assets" / "fonts"
HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}


def _tool(name: str) -> str:
    """Ruta a ffmpeg/ffprobe: variable de entorno, copia incluida en la app o el del sistema."""
    env = os.environ.get(f"IMAN_{name.upper()}")
    if env:
        return env
    exe = name + (".exe" if os.name == "nt" else "")
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    for cand in (base / "bin" / exe, Path(__file__).parent / "bin" / exe):
        if cand.exists():
            return str(cand)
    return shutil.which(name) or name


FFMPEG = _tool("ffmpeg")
FFPROBE = _tool("ffprobe")


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
        [FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
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
        [FFMPEG, "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(dst)],
        check=True,
    )
    return dst


VOICE_CHAIN = (
    "highpass=f=80,lowpass=f=14000,afftdn=nr=12:nf=-40:tn=1,"
    "equalizer=f=3000:t=q:w=1.2:g=2.5,"
    "acompressor=threshold=-20dB:ratio=3:attack=8:release=120:makeup=2"
)

ZOOM = 1.15  # plano cerrado: un 15 % más de cerca

SIZES = {"1080": (1080, 1920), "4k": (2160, 3840)}


def _filter_path(p: Path) -> str:
    # Escapado para usar rutas dentro de un filtergraph.
    return str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _video_overlays(parts: list[str], ops: list, W: int, H: int, cur: str = "[vx]", src: str = "[0:v]",
                    images: dict | None = None) -> str:
    """Efectos que mezclan vídeo sobre el reel ya montado (tiempos del reel, en segundos).

    - bruto: tarjeta inclinada con la toma original sin cortar, arriba a la derecha.
    - fantasma: una copia del propio reel, un instante retrasada y semitransparente.
    - pagina: el reel encogido sobre una hoja de revista color crema.
    """
    k_scale = W / 1080
    for k, op in enumerate(ops):
        a, b = op.start, op.end
        if b - a < 0.2:
            continue
        on = f"enable='between(t,{a:.3f},{b:.3f})'"
        if op.kind == "bruto":
            cw, ch = int(380 * k_scale) // 2 * 2, int(676 * k_scale) // 2 * 2
            brd = int(12 * k_scale)
            parts.append(
                f"{src}trim=start={op.src_start:.3f}:duration={b - a:.3f},setpts=PTS-STARTPTS+{a:.3f}/TB,fps=30,"
                f"scale={cw}:{ch}:force_original_aspect_ratio=increase,crop={cw}:{ch},setsar=1,"
                f"pad={cw + 2 * brd}:{ch + 2 * brd}:{brd}:{brd}:white,format=rgba,"
                f"rotate=-0.07:c=none:ow=rotw(-0.07):oh=roth(-0.07)[ov{k}]"
            )
            parts.append(f"{cur}[ov{k}]overlay=x={int(600 * k_scale)}:y={int(330 * k_scale)}:{on}:eof_action=pass[o{k}]")
        elif op.kind == "fantasma":
            lag = 0.45
            parts.append(f"{cur}split[m{k}][g{k}]")
            parts.append(
                f"[g{k}]trim=start={max(0.0, a - lag):.3f}:end={max(0.0, b - lag):.3f},setpts=PTS+{lag}/TB,"
                f"format=yuva420p,colorchannelmixer=aa=0.42[gh{k}]"
            )
            parts.append(f"[m{k}][gh{k}]overlay=0:0:{on}:eof_action=pass[o{k}]")
        elif op.kind == "pagina":
            pw, ph = int(760 * k_scale) // 2 * 2, int(1150 * k_scale) // 2 * 2
            parts.append(f"{cur}split[m{k}][p{k}]")
            parts.append(f"color=c=0xF4ECDF:s={W}x{H}:r=30:d={b - a:.3f},setpts=PTS+{a:.3f}/TB[bgp{k}]")
            parts.append(f"[p{k}]trim=start={a:.3f}:end={b:.3f},scale={pw}:{ph}:force_original_aspect_ratio=increase,"
                         f"crop={pw}:{ph},setsar=1[pv{k}]")
            parts.append(f"[bgp{k}][pv{k}]overlay={(W - pw) // 2}:{int(560 * k_scale)}:eof_action=pass[pg{k}]")
            parts.append(f"[m{k}][pg{k}]overlay=0:0:{on}:eof_action=pass[o{k}]")
        elif op.kind == "endcard":
            parts.append(f"color=c=0x{op.color.lstrip('#')}:s={W}x{H}:r=30:d={b - a:.3f},"
                         f"format=yuva420p,fade=t=in:st=0:d=0.25:alpha=1,setpts=PTS+{a:.3f}/TB[ec{k}]")
            parts.append(f"{cur}[ec{k}]overlay=0:0:{on}:eof_action=pass[o{k}]")
        elif op.kind in ("logo", "logo_end") and images and op.path in images:
            # Logo de la marca: pequeño en la esquina (zona segura de Instagram) o grande en el cierre.
            lw = int((150 if op.kind == "logo" else 420) * k_scale)
            alpha = 0.92 if op.kind == "logo" else 1.0
            fade = "" if op.kind == "logo" else f",fade=t=in:st={a:.3f}:d=0.35:alpha=1"
            parts.append(f"{images[op.path]}scale={lw}:-1,format=rgba,colorchannelmixer=aa={alpha},"
                         f"loop=-1:1,fps=30,setpts=N/30/TB{fade}[lg{k}]")
            pos = f"x=W-w-{int(40 * k_scale)}:y={int(210 * k_scale)}" if op.kind == "logo" else \
                f"x=(W-w)/2:y={int(860 * k_scale)}-h"
            parts.append(f"{cur}[lg{k}]overlay={pos}:{on}:shortest=1[o{k}]")
        else:
            continue
        cur = f"[o{k}]"
    return cur


def _image_inputs(ops: list, first_index: int) -> tuple[list[str], dict]:
    """Entradas extra de ffmpeg para las imágenes de los efectos (logo de la marca)."""
    args, labels = [], {}
    for op in ops or []:
        if op.path and op.path not in labels:
            labels[op.path] = f"[{first_index + len(labels)}:v]"
            args += ["-i", op.path]
    return args, labels


def build_filtergraph(
    spans: list[Span], info: MediaInfo, ass_path: Path | None, size: str = "1080", fit: str = "recortar",
    voice: bool = True,
    zooms: list[bool] | None = None,
    overlays: list | None = None,
) -> str:
    W, H = SIZES[size]
    zooms = zooms or [False] * len(spans)
    w0, h0 = info.width - info.width % 2, info.height - info.height % 2
    parts = []
    labels = []
    for i, sp in enumerate(spans):
        d = sp.duration
        fade = min(0.012, d / 4)
        zoom = f",crop=iw/{ZOOM}:ih/{ZOOM},scale={w0}:{h0}" if zooms[i] else ""
        parts.append(f"[0:v]trim=start={sp.start:.3f}:end={sp.end:.3f},setpts=PTS-STARTPTS{zoom},setsar=1[v{i}]")
        # Microfundidos solo en los cortes de verdad, no donde un tramo sigue al anterior.
        fades = []
        if i == 0 or abs(spans[i - 1].end - sp.start) > 1e-3:
            fades.append(f"afade=t=in:d={fade:.3f}")
        if i == len(spans) - 1 or abs(spans[i + 1].start - sp.end) > 1e-3:
            fades.append(f"afade=t=out:st={d - fade:.3f}:d={fade:.3f}")
        afx = "".join("," + f for f in fades)
        parts.append(
            f"[0:a]atrim=start={sp.start:.3f}:end={sp.end:.3f},asetpts=PTS-STARTPTS{afx}[a{i}]"
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
    parts.append("[vf]fps=30,setsar=1[vx]")
    _, images = _image_inputs(overlays, 1)
    cur = _video_overlays(parts, overlays or [], W, H, images=images)
    tail = f"{cur}null"
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
    zooms: list[bool] | None = None,
    preset: str = "medium",
    overlays: list | None = None,
) -> Path:
    graph = build_filtergraph(spans, info, ass_path, size, fit, voice, zooms, overlays)
    script = dst.with_suffix(".filters.txt")
    script.write_text(graph)
    extra, _ = _image_inputs(overlays, 1)
    cmd = [
        FFMPEG, "-y", "-v", "error", "-i", str(src), *extra,
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


def composite(
    base: Path, mask: Path, raw: Path, dst: Path, behind_ass: Path | None, ass_path: Path | None,
    seg_ops: list, overlays: list | None = None, size: str = "1080",
) -> Path:
    """Segunda pasada para los efectos que van detrás de la persona.

    `base` es el reel ya cortado y encuadrado (sin textos), `mask` su máscara de persona.
    Capas, de atrás adelante: fondo (con color o desenfoque), textos de detrás, la persona,
    efectos de vídeo, subtítulos y textos de delante.
    """
    W, H = SIZES[size]
    parts = ["[0:v]split=2[bg0][fg]"]
    cur = "[bg0]"
    for k, op in enumerate(seg_ops):
        a, b = op.start, op.end
        on = f"enable='between(t,{a:.3f},{b:.3f})'"
        if op.kind == "fondo":
            parts.append(f"color=c=0x{op.color.lstrip('#')}:s={W}x{H}:r=30:d={b - a:.3f},setpts=PTS+{a:.3f}/TB[c{k}]")
            parts.append(f"{cur}[c{k}]overlay=0:0:{on}:eof_action=pass[b{k}]")
        elif op.kind == "desenfoque":
            parts.append(f"{cur}split[x{k}][y{k}]")
            parts.append(f"[y{k}]boxblur=22:2,eq=brightness=-0.04[yb{k}]")
            parts.append(f"[x{k}][yb{k}]overlay=0:0:{on}[b{k}]")
        else:
            continue
        cur = f"[b{k}]"
    if behind_ass is not None:
        parts.append(f"{cur}ass=filename='{_filter_path(behind_ass)}':fontsdir='{_filter_path(FONTS_DIR)}'[bt]")
        cur = "[bt]"
    parts.append(f"[1:v]scale={W}:{H}:flags=bicubic,format=gray,boxblur=2:1[mk]")
    parts.append("[fg][mk]alphamerge[person]")
    parts.append(f"{cur}[person]overlay=0:0[vx]")
    extra, images = _image_inputs(overlays, 3)
    cur = _video_overlays(parts, overlays or [], W, H, "[vx]", "[2:v]", images)
    tail = f"{cur}null"
    if ass_path is not None:
        tail += f",ass=filename='{_filter_path(ass_path)}':fontsdir='{_filter_path(FONTS_DIR)}'"
    parts.append(tail + ",format=yuv420p[vout]")
    script = dst.with_suffix(".composite.txt")
    script.write_text(";\n".join(parts))
    cmd = [
        FFMPEG, "-y", "-v", "error", "-i", str(base), "-i", str(mask), "-i", str(raw), *extra,
        "-filter_complex_script", str(script), "-map", "[vout]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "copy", "-movflags", "+faststart", str(dst),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falló:\n{res.stderr[-2000:]}")
    return dst


def thumbnail(src: Path, dst: Path, t: float = 0.5) -> Path:
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-q:v", "3", str(dst)],
        check=True,
    )
    return dst
