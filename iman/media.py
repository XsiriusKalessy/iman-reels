"""Todo lo que toca ffmpeg: analizar, extraer audio y renderizar el reel."""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .models import Span
from .textfit import fonts_dir

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


@functools.cache
def _ffmpeg_major() -> int:
    try:
        out = subprocess.run([FFMPEG, "-hide_banner", "-version"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        m = re.search(r"version n?(\d+)\.", out)
        return int(m.group(1)) if m else 99  # las compilaciones "master" no llevan número: son las más nuevas
    except OSError:
        return 99


def filter_script_args(script: Path) -> list[str]:
    """ffmpeg 7 cambió cómo se pasa el filtro desde un archivo; ffmpeg 8 quitó la forma antigua."""
    if _ffmpeg_major() >= 7:
        return ["-/filter_complex", str(script)]
    return ["-filter_complex_script", str(script)]


@dataclass
class MediaInfo:
    width: int
    height: int
    duration: float
    fps: float
    has_audio: bool
    hdr: bool


def probe_streams(path: Path) -> list[dict]:
    out = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", str(path)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
    return json.loads(out).get("streams", [])


def probe(path: Path) -> MediaInfo:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
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


# Suave a propósito: una reducción de ruido o un de-esser fuertes dejan la voz metálica o con siseo raro
# (sobre todo grabando en el coche o en la calle). Mejor algo de ruido que una voz que no parece tuya.
VOICE_CHAIN = (
    "highpass=f=70,lowpass=f=16000,afftdn=nr=6:nf=-48:tn=1,"
    "equalizer=f=220:t=q:w=1:g=-1.5,equalizer=f=3500:t=q:w=1.4:g=1.5,deesser=i=0.15,"
    "acompressor=threshold=-18dB:ratio=2.5:attack=15:release=160:makeup=1.5"
)

# Looks de un clic (color y textura), todos con filtros de ffmpeg: nada de LUTs ni packs de terceros.
LOOKS = {
    "natural": "eq=contrast=1.04:saturation=1.06",
    "calido": "colorbalance=rm=0.06:gm=0.01:bm=-0.07:rh=0.04:bh=-0.05,eq=saturation=1.1:contrast=1.04",
    "teal": "colorbalance=rs=-0.08:gs=-0.02:bs=0.12:rh=0.10:gh=0.02:bh=-0.10,eq=contrast=1.08:saturation=1.12",
    "cine": "colorbalance=rs=-0.05:bs=0.08:rh=0.06:bh=-0.05,eq=contrast=1.1:saturation=0.92,"
            "noise=alls=8:allf=t,vignette=PI/5",
    "grano": "eq=saturation=0.9:contrast=1.06,noise=alls=16:allf=t+u,vignette=PI/4.5",
    "retro": "rgbashift=rh=-4:bh=4,eq=saturation=1.25:contrast=1.1,noise=alls=10:allf=t,"
             "drawgrid=w=iw:h=4:t=1:c=black@0.22,vignette=PI/4",
    "bn": "hue=s=0,eq=contrast=1.18,noise=alls=12:allf=t,vignette=PI/5",
}

# Transiciones en los cortes: un barrido con desenfoque de movimiento (whip) o un glitch de 0,1 s.
TRANSITIONS = {
    "whip": "avgblur=sizeX=56:sizeY=1:enable='lt(t,0.12)'",
    "glitch": "rgbashift=rh=-18:gh=6:bh=18:enable='lt(t,0.1)',noise=alls=45:allf=t:enable='lt(t,0.1)'",
}


def transition_plan(spans: list[Span]) -> dict[int, str]:
    """En qué tramos entra una transición: uno de cada dos cortes de verdad, alternando whip y glitch."""
    out, n = {}, 0
    for i in range(1, len(spans)):
        if abs(spans[i - 1].end - spans[i].start) > 1e-3:
            n += 1
            if n % 2 == 0:
                out[i] = "whip" if (n // 2) % 2 else "glitch"
    return out


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
        elif op.kind == "apoyo" and images and id(op) in images:
            # Vídeo de apoyo a pantalla completa y el creador, que sigue hablando, en un círculo arriba (los subtítulos van abajo).
            d = b - a
            still = Path(op.path).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
            ramp = getattr(op, "ramp", True)
            feed = (f"loop=-1:1,fps=30,trim=duration={d:.3f},setpts=PTS-STARTPTS+{a:.3f}/TB" if still else
                    f"trim=duration={ramp_need(d, ramp):.3f},setpts=PTS-STARTPTS,{ramp_pts(d, ramp)}fps=30,"
                    f"tpad=stop_mode=clone:stop_duration={d:.3f},trim=duration={d:.3f},setpts=PTS+{a:.3f}/TB")
            # Un toque de zoom lento para que las fotos no se vean quietas.
            zoom = (f",scale={int(W * 1.08)}:{int(H * 1.08)},crop={W}:{H}:'(iw-ow)/2*(1-(t-{a:.3f})/{d:.3f})':"
                    f"'(ih-oh)/2'") if still else ""
            parts.append(f"{images[id(op)]}{feed},scale={W}:{H}:force_original_aspect_ratio=increase,"
                         f"crop={W}:{H}{zoom},setsar=1,format=yuv420p,fade=t=in:st={a:.3f}:d=0.15[br{k}]")
            dd = int(340 * k_scale) // 2 * 2
            ring = int(10 * k_scale)
            circle = "if(lt(hypot(X-W/2,Y-H/2),W/2-1),255,0)"
            parts.append(f"{cur}split[m{k}][f{k}]")
            parts.append(f"[f{k}]trim=start={a:.3f}:end={b:.3f},crop=iw*0.62:iw*0.62:(iw-ow)/2:ih*0.10,scale={dd}:{dd},format=rgba,"
                         f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{circle}'[fc{k}]")
            parts.append(f"color=c=white:s={dd + 2 * ring}x{dd + 2 * ring}:r=30,format=rgba,"
                         f"geq=r=255:g=255:b=255:a='{circle}'[rg{k}]")
            parts.append(f"[rg{k}][fc{k}]overlay={ring}:{ring}:shortest=1[bb{k}]")
            parts.append(f"[m{k}][br{k}]overlay=0:0:{on}:eof_action=pass[t{k}]")
            parts.append(f"[t{k}][bb{k}]overlay=x=W-w-{int(48 * k_scale)}:y={int(250 * k_scale)}:{on}:eof_action=pass[o{k}]")
        elif op.kind == "objeto" and images and id(op) in images:
            # Pegatina del objeto que se nombra: entra subiendo y con fundido, alternando lado.
            n_obj = sum(1 for o in ops[:k] if o.kind == "objeto")
            sw = int(400 * k_scale)
            parts.append(f"{images[id(op)]}scale={sw}:-1,format=rgba,loop=-1:1,fps=30,setpts=N/30/TB,"
                         f"fade=t=in:st={a:.3f}:d=0.2:alpha=1,fade=t=out:st={b - 0.2:.3f}:d=0.2:alpha=1[ob{k}]")
            x = f"W-w-{int(50 * k_scale)}" if n_obj % 2 == 0 else f"{int(50 * k_scale)}"
            y = f"{int(860 * k_scale)}+{int(90 * k_scale)}*max(0,1-(t-{a:.3f})/0.25)"
            parts.append(f"{cur}[ob{k}]overlay=x={x}:y='{y}':{on}:shortest=1[o{k}]")
        elif op.kind in ("captura", "collage") and images and id(op) in images:
            # Tarjeta con captura o collage de fotos de apoyo: sube desde abajo con un frenazo y se funde.
            cw = int((760 if op.kind == "captura" else 1000) * k_scale)
            parts.append(f"{images[id(op)]}scale={cw}:-1,format=rgba,loop=-1:1,fps=30,setpts=N/30/TB,"
                         f"fade=t=in:st={a:.3f}:d=0.15:alpha=1,fade=t=out:st={b - 0.2:.3f}:d=0.2:alpha=1[cp{k}]")
            y = f"{int(330 * k_scale)}+{int(160 * k_scale)}*pow(max(0,1-(t-{a:.3f})/0.3),3)"
            parts.append(f"{cur}[cp{k}]overlay=x=(W-w)/2:y='{y}':{on}:shortest=1[o{k}]")
        elif op.kind in ("logo", "logo_end") and images and id(op) in images:
            # Logo de la marca: pequeño en la esquina (zona segura de Instagram) o grande en el cierre.
            lw = int((150 if op.kind == "logo" else 420) * k_scale)
            alpha = 0.92 if op.kind == "logo" else 1.0
            fade = "" if op.kind == "logo" else f",fade=t=in:st={a:.3f}:d=0.35:alpha=1"
            parts.append(f"{images[id(op)]}scale={lw}:-1,format=rgba,colorchannelmixer=aa={alpha},"
                         f"loop=-1:1,fps=30,setpts=N/30/TB{fade}[lg{k}]")
            pos = f"x=W-w-{int(40 * k_scale)}:y={int(210 * k_scale)}" if op.kind == "logo" else \
                f"x=(W-w)/2:y={int(860 * k_scale)}-h"
            parts.append(f"{cur}[lg{k}]overlay={pos}:{on}:shortest=1[o{k}]")
        else:
            continue
        cur = f"[o{k}]"
    return cur


# Rampa de velocidad en los vídeos de apoyo: entra rápido (x2,5) y frena a cámara un poco lenta (x0,8).
RAMP_FAST, RAMP_FAST_IN, RAMP_SLOW = 2.5, 0.6, 0.8


def ramp_need(d: float, on: bool = True) -> float:
    """Segundos del vídeo de apoyo que hacen falta para llenar d segundos con la rampa."""
    if not on or d < 1.2:
        return d
    return RAMP_FAST_IN + RAMP_SLOW * (d - RAMP_FAST_IN / RAMP_FAST)


def ramp_pts(d: float, on: bool = True) -> str:
    """setpts de la rampa (T = tiempo del vídeo original), vacío en planos cortos que no la necesitan."""
    if not on or d < 1.2:
        return ""
    f, r, sl = RAMP_FAST, RAMP_FAST_IN, RAMP_SLOW
    return f"setpts='if(lt(T,{r}),T/{f},{r / f:.4f}+(T-{r})/{sl})/TB',"


def reframe(cx: float, w0: int, h0: int) -> tuple[int, int] | None:
    """(x, ancho) del recorte vertical 9:16 centrado en `cx` (0-1); None si el vídeo ya es vertical."""
    cw = int(h0 * 9 / 16) // 2 * 2
    if cw >= w0 * 0.95:
        return None
    return int(min(max(cx * w0 - cw / 2, 0), w0 - cw)) // 2 * 2, cw


def _image_inputs(ops: list, first_index: int) -> tuple[list[str], dict]:
    """Entradas extra de ffmpeg para los efectos con archivo (logo, vídeos de apoyo): una por efecto."""
    args, labels = [], {}
    for op in ops or []:
        if op.path:
            labels[id(op)] = f"[{first_index + len(labels)}:v]"
            args += ["-i", op.path]
    return args, labels


def _hush(hush: list[tuple[float, float]] | None) -> str:
    """Silencio dramático: la música se corta en seco en esos tramos (solo queda la voz)."""
    if not hush:
        return ""
    cond = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in hush)
    return f",volume='if({cond},0,1)':eval=frame"


def build_filtergraph(
    spans: list[Span], info: MediaInfo, ass_path: Path | None, size: str = "1080", fit: str = "recortar",
    voice: bool = True,
    zooms: list[bool] | None = None,
    overlays: list | None = None,
    tail: float = 0.0,
    sfx_bed: Path | None = None,
    music: Path | None = None,
    punch: bool = False,
    hush: list[tuple[float, float]] | None = None,
    look: str = "",
    transitions: dict[int, str] | None = None,
    framing: list[float] | None = None,
) -> str:
    """`framing`: centro x (0-1) de la cabeza en cada tramo; con vídeos horizontales el recorte vertical
    va centrado en ella y en todos los cortes queda en el mismo sitio (los saltos casan).
    `tail`: segundos extra al final (último fotograma congelado y silencio) para el cierre de marca.
    `sfx_bed`: pista con los efectos de sonido; `music`: tu música, que baja sola cuando hablas.
    `punch`: zoom rápido de entrada en el primer medio segundo (que nada esté quieto al empezar)."""
    W, H = SIZES[size]
    zooms = zooms or [False] * len(spans)
    w0, h0 = info.width - info.width % 2, info.height - info.height % 2
    parts = []
    labels = []
    for i, sp in enumerate(spans):
        d = sp.duration
        fade = min(0.012, d / 4)
        ref = reframe(framing[i], w0, h0) if framing and fit != "fondo" and i < len(framing) else None
        cw = ref[1] if ref else w0
        frame = f",crop={ref[1]}:{h0}:{ref[0]}:0" if ref else ""
        zoom = f",crop=iw/{ZOOM}:ih/{ZOOM},scale={cw}:{h0}" if zooms[i] else ""
        tr = "," + TRANSITIONS[transitions[i]] if transitions and i in transitions else ""
        parts.append(f"[0:v]trim=start={sp.start:.3f}:end={sp.end:.3f},setpts=PTS-STARTPTS{frame}{zoom},setsar=1{tr}[v{i}]")
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
    if tail > 0:
        parts.append(f"{''.join(labels)}concat=n={len(spans)}:v=1:a=1[vc0][ac0]")
        parts.append(f"[vc0]tpad=stop_mode=clone:stop_duration={tail:.3f}[vc]")
        parts.append(f"[ac0]apad=pad_dur={tail:.3f}[ac]")
    else:
        parts.append(f"{''.join(labels)}concat=n={len(spans)}:v=1:a=1[vc][ac]")

    chain = "[vc]"
    if info.hdr:
        # Mapeo de tonos HDR (iPhone) -> SDR BT.709.
        chain += TONEMAP
    if fit == "fondo":
        parts.append(f"{chain}split[bg0][fg0]")
        parts.append(
            f"[bg0]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:2,eq=brightness=-0.08[bg]"
        )
        parts.append(f"[fg0]scale={W}:{H}:force_original_aspect_ratio=decrease[fg]")
        parts.append("[bg][fg]overlay=(W-w)/2:(H-h)/2[vf]")
    else:
        parts.append(f"{chain}scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}[vf]")
    if look in LOOKS:
        parts.append(f"[vf]{LOOKS[look]}[vfl]")
        vf = "[vfl]"
    else:
        vf = "[vf]"
    if punch:
        # Entra un 20 % más cerca y se abre en 0,45 s, con un frenazo suave al final.
        parts.append(f"{vf}fps=30,setsar=1,split[pz0][pz1]")
        parts.append(f"[pz0]trim=duration=0.45,setpts=PTS-STARTPTS,"
                     f"zoompan=z='1+0.2*pow(1-on/13,3)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps=30[pz2]")
        parts.append("[pz1]trim=start=0.45,setpts=PTS-STARTPTS[pz3]")
        parts.append("[pz2][pz3]concat=n=2:v=1:a=0,setsar=1[vx]")
    else:
        parts.append(f"{vf}fps=30,setsar=1[vx]")
    _, images = _image_inputs(overlays, 1)
    cur = _video_overlays(parts, overlays or [], W, H, images=images)
    tail = f"{cur}null"
    if ass_path is not None:
        tail += f",ass=filename='{_filter_path(ass_path)}':fontsdir='{_filter_path(fonts_dir())}'"
    parts.append(tail + ",format=yuv420p[vout]")
    audio = "[ac]"
    if voice:
        # Voz más limpia: fuera graves y zumbidos, menos ruido de fondo, nivel más estable.
        audio += VOICE_CHAIN + ","
    nxt = 1 + len(images)  # entradas de audio extra, después de las imágenes
    if music is not None or sfx_bed is not None:
        parts.append(f"{audio}aresample=48000,aformat=channel_layouts=stereo[vo]")
        audio = "[vo]"
    if music is not None:
        # La música, en bucle y baja; se aparta sola cuando hablas (sidechain con la voz).
        parts.append(f"[{nxt}:a]aloop=loop=-1:size=2000000000,aresample=48000,aformat=channel_layouts=stereo,"
                     f"volume=0.22,afade=t=in:d=0.6{_hush(hush)}[mu]")
        parts.append(f"{audio}asplit[vk][vs]")
        parts.append("[mu][vs]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=500[md]")
        parts.append("[vk][md]amix=inputs=2:duration=first:normalize=0[vm]")
        audio = "[vm]"
        nxt += 1
    if sfx_bed is not None:
        parts.append(f"[{nxt}:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.55[sx]")
        parts.append(f"{audio}[sx]amix=inputs=2:duration=first:normalize=0[vsx]")
        audio = "[vsx]"
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
    tail: float = 0.0,
    sfx_bed: Path | None = None,
    music: Path | None = None,
    punch: bool = False,
    hush: list[tuple[float, float]] | None = None,
    look: str = "",
    transitions: dict[int, str] | None = None,
    framing: list[float] | None = None,
) -> Path:
    graph = build_filtergraph(spans, info, ass_path, size, fit, voice, zooms, overlays, tail, sfx_bed, music, punch,
                              hush, look, transitions, framing)
    script = dst.with_suffix(".filters.txt")
    script.write_text(graph, encoding="utf-8")
    extra, _ = _image_inputs(overlays, 1)
    if music is not None:
        extra += ["-i", str(music)]
    if sfx_bed is not None:
        extra += ["-i", str(sfx_bed)]
    cmd = [
        FFMPEG, "-y", "-v", "error", "-i", str(src), *extra,
        *filter_script_args(script),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", preset, "-crf", "18", "-profile:v", "high",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
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
    extra, images = _image_inputs(overlays, 3)
    photos = {}  # fotos de fondo: entradas después de las de los efectos
    for op in seg_ops:
        if op.kind == "foto" and op.path:
            photos[id(op)] = f"[{3 + len(images) + len(photos)}:v]"
            extra += ["-loop", "1", "-i", op.path]
    for k, op in enumerate(seg_ops):
        a, b = op.start, op.end
        on = f"enable='between(t,{a:.3f},{b:.3f})'"
        if op.kind == "fondo":
            parts.append(f"color=c=0x{op.color.lstrip('#')}:s={W}x{H}:r=30:d={b - a:.3f},setpts=PTS+{a:.3f}/TB[c{k}]")
            parts.append(f"{cur}[c{k}]overlay=0:0:{on}:eof_action=pass[b{k}]")
        elif op.kind == "foto" and id(op) in photos:
            parts.append(f"{photos[id(op)]}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
                         f"fps=30,trim=duration={b - a:.3f},setpts=PTS-STARTPTS+{a:.3f}/TB,format=yuv420p[ph{k}]")
            parts.append(f"{cur}[ph{k}]overlay=0:0:{on}:eof_action=pass[b{k}]")
        elif op.kind == "desenfoque":
            parts.append(f"{cur}split[x{k}][y{k}]")
            parts.append(f"[y{k}]boxblur=22:2,eq=brightness=-0.04[yb{k}]")
            parts.append(f"[x{k}][yb{k}]overlay=0:0:{on}[b{k}]")
        else:
            continue
        cur = f"[b{k}]"
    if behind_ass is not None:
        parts.append(f"{cur}ass=filename='{_filter_path(behind_ass)}':fontsdir='{_filter_path(fonts_dir())}'[bt]")
        cur = "[bt]"
    # Borde del recorte suavizado y una sombra difusa detrás, para que la persona no parezca pegada encima.
    parts.append(f"[1:v]scale={W}:{H}:flags=bicubic,format=gray,split[m1][m2]")
    parts.append("[m1]boxblur=2:1[mk]")
    parts.append("[m2]boxblur=36:2,split[sa][sb]")
    parts.append("[sa]lut=y=16[sk]")
    parts.append("[sb]lut=y=val*0.55[sx]")
    parts.append("[sk]format=yuv420p[skc]")
    parts.append("[skc][sx]alphamerge[shadow]")
    swap = [o for o in seg_ops if o.kind in ("fondo", "foto", "desenfoque")]
    when = "+".join(f"between(t,{o.start:.3f},{o.end:.3f})" for o in swap) or "0"
    parts.append(f"{cur}[shadow]overlay={int(18 * W / 1080)}:{int(26 * W / 1080)}:enable='{when}'[sh]")
    parts.append("[fg][mk]alphamerge[person]")
    parts.append("[sh][person]overlay=0:0[vx]")
    cur = _video_overlays(parts, overlays or [], W, H, "[vx]", "[2:v]", images)
    tail = f"{cur}null"
    if ass_path is not None:
        tail += f",ass=filename='{_filter_path(ass_path)}':fontsdir='{_filter_path(fonts_dir())}'"
    parts.append(tail + ",format=yuv420p[vout]")
    script = dst.with_suffix(".composite.txt")
    script.write_text(";\n".join(parts), encoding="utf-8")
    cmd = [
        FFMPEG, "-y", "-v", "error", "-i", str(base), "-i", str(mask), "-i", str(raw), *extra,
        *filter_script_args(script), "-map", "[vout]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "copy", "-movflags", "+faststart", str(dst),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falló:\n{res.stderr[-2000:]}")
    return dst


def thumbnail(src: Path, dst: Path, t: float = 0.5) -> Path:
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-q:v", "3", str(dst)],
        check=True,
    )
    return dst


STILL_EXT = (".jpg", ".jpeg", ".png", ".webp")


def duration_of(path: Path) -> float:
    """Duración de cualquier archivo (también audio solo o una foto, que da 0)."""
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def voice_canvas(audio: Path, dst: Path, cuts: list[float], clips: list[Path], color: str = "#141518") -> Path:
    """Para reels sin cámara: tu voz sobre tus vídeos y fotos, cambiando de plano en `cuts` (segundos).

    Sin vídeos, un fondo liso con un brillo suave; los subtítulos grandes hacen el resto.
    """
    W, H = SIZES["1080"]
    total = duration_of(audio)
    bounds = [0.0, *[c for c in cuts if 0 < c < total], total]
    parts, inputs = [], ["-i", str(audio)]
    if not clips:
        c = color.lstrip("#")
        parts.append(f"color=c=0x{c}:s={W}x{H}:r=30:d={total:.3f},vignette=PI/4,format=yuv420p[vout]")
    else:
        lens = {p: (0.0 if p.suffix.lower() in STILL_EXT else duration_of(p)) for p in clips}
        pos = {p: 0.0 for p in clips}
        labels = []
        for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
            d, p = b - a, clips[i % len(clips)]
            inputs += ["-i", str(p)]
            if p.suffix.lower() in STILL_EXT:
                feed = (f"loop=-1:1,fps=30,trim=duration={d:.3f},setpts=PTS-STARTPTS,"
                        f"scale={int(W * 1.1)}:{int(H * 1.1)}:force_original_aspect_ratio=increase,"
                        f"crop={W}:{H}:'(iw-ow)/2*(1-t/{d:.3f})':'(ih-oh)/2'")
            else:
                if pos[p] + d > lens[p]:
                    pos[p] = 0.0
                feed = (f"trim=start={pos[p]:.3f},setpts=PTS-STARTPTS,fps=30,"
                        f"tpad=stop_mode=clone:stop_duration={d:.3f},trim=duration={d:.3f},"
                        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}")
                pos[p] += d
            parts.append(f"[{i + 1}:v]{feed},setsar=1,format=yuv420p[c{i}]")
            labels.append(f"[c{i}]")
        parts.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[vout]")
    script = dst.with_suffix(".canvas.txt")
    script.write_text(";\n".join(parts), encoding="utf-8")
    cmd = [FFMPEG, "-y", "-v", "error", *inputs, *filter_script_args(script), "-map", "[vout]", "-map", "0:a",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", str(dst)]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falló:\n{res.stderr[-2000:]}")
    return dst


def silences(src: Path, noise_db: int = -35, min_len: float = 0.12) -> list[tuple[float, float]]:
    """Tramos en silencio de un vídeo (inicio, fin), para cortar entre frases."""
    res = subprocess.run([FFMPEG, "-v", "info", "-i", str(src), "-af", f"silencedetect=n={noise_db}dB:d={min_len}",
                          "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", res.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", res.stderr)]
    return list(zip(starts, ends))


def split_points(duration: float, quiet: list[tuple[float, float]], limit: float = 59.0,
                 shortest: float = 30.0) -> list[float]:
    """Dónde partir un vídeo en trozos de menos de `limit` segundos: en el último silencio que quepa
    (sin dejar trozos de menos de `shortest`) y, si no hay ninguno, justo en el límite."""
    cuts, start = [], 0.0
    while duration - start > limit:
        mids = [(a + b) / 2 for a, b in quiet if start + shortest <= (a + b) / 2 <= start + limit]
        at = max(mids) if mids else start + limit
        cuts.append(round(at, 3))
        start = at
    return cuts


def cut(src: Path, dst: Path, start: float, end: float) -> Path:
    """Un trozo de un vídeo largo, recodificado para que el corte sea exacto."""
    cmd = [FFMPEG, "-y", "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-i", str(src), "-t", f"{end - start:.3f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           str(dst)]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falló:\n{res.stderr[-2000:]}")
    return dst


TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
           "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,")


def color_stats(src: Path, hdr: bool = False, samples: int = 6) -> tuple[list[float], list[float]]:
    """Media y desviación de R, G y B en unos fotogramas pequeños repartidos por el vídeo."""
    import numpy as np

    dur = max(duration_of(src), 0.1)
    frames = []
    for i in range(samples):
        t = dur * (i + 0.5) / samples
        cmd = [FFMPEG, "-v", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
               "-vf", f"{TONEMAP if hdr else ''}scale=64:64,format=rgb24", "-f", "rawvideo", "-"]
        raw = subprocess.run(cmd, capture_output=True).stdout
        if len(raw) == 64 * 64 * 3:
            frames.append(np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(float))
    if not frames:
        return [128.0] * 3, [50.0] * 3
    px = np.concatenate(frames)
    return px.mean(0).tolist(), np.maximum(px.std(0), 1.0).tolist()


def match_filter(stats: tuple[list[float], list[float]], target: tuple[list[float], list[float]]) -> str:
    """lutrgb que lleva el color de una toma al de la primera (media y contraste por canal, con límites
    para que una toma muy distinta no se pase de vueltas)."""
    exprs = []
    for c, (m, s, mt, st) in enumerate(zip(*stats, *target)):
        g = min(max(st / s, 0.8), 1.25)
        off = min(max(mt - m * g, -40.0), 40.0)
        exprs.append(f"{'rgb'[c]}='clip(val*{g:.4f}+{off:.2f},0,255)'")
    return "lutrgb=" + ":".join(exprs)


def join_takes(srcs: list[Path], dst: Path) -> Path:
    """Varias tomas grabadas por separado → un solo vídeo, con el tamaño de la primera y su mismo color
    (si una toma salió más oscura o más fría, se iguala a la primera antes de editar)."""
    infos = [probe(p) for p in srcs]
    W = infos[0].width // 2 * 2
    H = infos[0].height // 2 * 2
    stats = [color_stats(p, i.hdr) for p, i in zip(srcs, infos)]
    inputs, parts, labels = [], [], []
    for k, (p, info) in enumerate(zip(srcs, infos)):
        inputs += ["-i", str(p)]
        fix = "" if k == 0 else match_filter(stats[k], stats[0]) + ","
        parts.append(f"[{k}:v]{TONEMAP if info.hdr else ''}scale={W}:{H}:force_original_aspect_ratio=increase,"
                     f"crop={W}:{H},fps=30,format=rgb24,{fix}format=yuv420p,setsar=1[v{k}]")
        if info.has_audio:
            parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo[a{k}]")
        else:
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={info.duration:.3f}[a{k}]")
        labels.append(f"[v{k}][a{k}]")
    parts.append(f"{''.join(labels)}concat=n={len(srcs)}:v=1:a=1[v][a]")
    script = dst.parent / "tomas.join.txt"  # no "original.*": el servidor busca el vídeo con ese nombre
    script.write_text(";\n".join(parts), encoding="utf-8")
    cmd = [FFMPEG, "-y", "-v", "error", *inputs, *filter_script_args(script), "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", str(dst)]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    script.unlink(missing_ok=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falló:\n{res.stderr[-2000:]}")
    return dst
