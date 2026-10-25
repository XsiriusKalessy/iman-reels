"""Fotos que se mueven en 2.5D (paralaje): la foto deja de ser un plano quieto y parece que la cámara se mueve.

- Si sale una persona: se recorta (el mismo recorte que el resto de Imán), el hueco del fondo se rellena y las
  dos capas se mueven a distinta velocidad: el fondo despacio y la persona más y hacia el otro lado.
- Si no (un paisaje, un hotel): se supone que lo de abajo está más cerca que lo de arriba (como casi siempre en
  una foto de viaje) y la imagen se desliza más abajo que arriba, con un zoom lento.

Se pinta como un vídeo corto (1080x1920, 30 fps) que entra como plano de apoyo. Todo en local.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

W, H, FPS = 1080, 1920, 30
MARGIN = 1.2  # la foto se prepara un 20 % más grande que el reel: margen para moverla sin que se vean bordes
K0 = 1 / 1.12


def _cv2():
    try:
        import cv2
    except Exception:  # noqa: BLE001
        return None
    return cv2


def _ease(u: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * min(max(u, 0.0), 1.0))


def _layers(img: Image.Image):
    """(fondo RGB, persona RGBA o None) al tamaño con margen."""
    from . import segment

    size = (int(W * MARGIN), int(H * MARGIN))
    img = ImageOps.fit(img.convert("RGB"), size, Image.LANCZOS, centering=(0.5, 0.4))
    mask = segment.person_mask(img)
    if mask is None:
        return img, None
    m = np.asarray(mask, np.float32) / 255
    if m.mean() < 0.04 or m.mean() > 0.7:  # nadie, o tan cerca que no hay fondo que mover
        return img, None
    cv2 = _cv2()
    bg = np.asarray(img).copy()
    hole = (m > 0.15).astype(np.uint8) * 255
    if cv2 is not None:
        # Relleno del hueco a un cuarto de tamaño (rápido y suficiente: el fondo va algo desenfocado).
        k = 4
        small = cv2.resize(bg, (size[0] // k, size[1] // k), interpolation=cv2.INTER_AREA)
        hs = cv2.resize(hole, (size[0] // k, size[1] // k), interpolation=cv2.INTER_NEAREST)
        hs = cv2.dilate(hs, np.ones((7, 7), np.uint8))
        filled = cv2.resize(cv2.inpaint(small, hs, 9, cv2.INPAINT_TELEA), size, interpolation=cv2.INTER_CUBIC)
        grow = cv2.dilate(hole, np.ones((31, 31), np.uint8))[..., None] > 0
        bg = np.where(grow, filled, bg)
    back = Image.fromarray(bg).filter(ImageFilter.GaussianBlur(2.2))  # un poco de profundidad de campo
    person = img.convert("RGBA")
    person.putalpha(mask)
    return back, person


def _affine(im, k: float, src_c: tuple[float, float], dst_c: tuple[float, float]):
    """Escala `k` llevando el punto `src_c` de la foto al punto `dst_c` del reel (array con OpenCV, o PIL)."""
    if isinstance(im, np.ndarray):
        m = np.float32([[k, 0, dst_c[0] - src_c[0] * k], [0, k, dst_c[1] - src_c[1] * k]])
        return _cv2().warpAffine(im, m, (W, H), flags=1, borderMode=1)  # lineal; bordes repetidos
    a = 1 / k
    data = (a, 0, src_c[0] - dst_c[0] * a, 0, a, src_c[1] - dst_c[1] * a)
    fill = (0, 0, 0, 0) if im.mode == "RGBA" else (0, 0, 0)
    return im.transform((W, H), Image.AFFINE, data, Image.BILINEAR, fillcolor=fill)


def frames(img: Image.Image, duration: float, direction: int = 1):
    """Fotogramas (PIL RGB) del movimiento."""
    back, person = _layers(img)
    sw, sh = back.size
    n = max(1, int(round(duration * FPS)))
    cv2 = _cv2()
    if person is None and cv2 is not None:
        ys = np.arange(H, dtype=np.float32)[:, None]
        depth = (ys / H) ** 1.6  # abajo, cerca; arriba, lejos
        xs = np.arange(W, dtype=np.float32)[None, :]
    if person is not None and cv2 is not None:
        back_a = np.asarray(back)
        person_a = np.asarray(person).astype(np.float32)
        person_a[..., :3] *= person_a[..., 3:] / 255  # premultiplicada: el borde no se oscurece al escalar
    for f in range(n):
        u = _ease(f / max(1, n - 1))
        side = direction * (u - 0.5) * 2  # de -1 a 1
        if person is not None and cv2 is not None:
            frame = _affine(back_a, K0 * (1 + 0.04 * u), (sw / 2, sh / 2), (W / 2 - 18 * side, H / 2)).astype(np.float32)
            m = np.float32([[K0 * (1 + 0.10 * u), 0, 0], [0, K0 * (1 + 0.10 * u), 0]])
            m[0, 2], m[1, 2] = W / 2 + 40 * side - sw / 2 * m[0, 0], H - sh * m[1, 1]
            front = cv2.warpAffine(person_a, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            out = front[..., :3] + frame * (1 - front[..., 3:] / 255)
            yield Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
        elif person is not None:
            frame = _affine(back, K0 * (1 + 0.04 * u), (sw / 2, sh / 2), (W / 2 - 18 * side, H / 2))
            front = _affine(person, K0 * (1 + 0.10 * u), (sw / 2, sh), (W / 2 + 40 * side, H))
            frame = frame.convert("RGBA")
            frame.alpha_composite(front)
            yield frame.convert("RGB")
        elif cv2 is not None:
            base = _affine(np.asarray(back), K0 * (1 + 0.07 * u), (sw / 2, sh / 2), (W / 2, H / 2))
            # Las filas de abajo se desplazan más que las de arriba (y crecen un pelín): sensación de volumen.
            shift = 70 * side * (depth - 0.3)
            grow = 1 - 0.05 * u * depth
            mapx = ((xs - W / 2) * grow + W / 2 - shift).astype(np.float32)
            mapy = np.broadcast_to(ys, (H, W)).astype(np.float32)
            out = cv2.remap(base, np.broadcast_to(mapx, (H, W)).astype(np.float32), mapy, cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_REFLECT)
            yield Image.fromarray(out)
        else:  # sin OpenCV: zoom y desplazamiento lentos, como antes
            yield _affine(back, K0 * (1 + 0.08 * u), (sw / 2, sh / 2), (W / 2 - 30 * side, H / 2))


def render(photo: Path, duration: float, dst: Path) -> Path:
    from .media import FFMPEG

    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(photo) as im:
        img = ImageOps.exif_transpose(im).convert("RGB")
    try:  # la foto mejorada antes (luz, color, nitidez): las de móvil suelen venir apagadas
        from . import imagen

        img = imagen.mejorar(img)
    except Exception:  # noqa: BLE001
        pass
    direction = 1 if int(hashlib.sha1(str(photo).encode()).hexdigest(), 16) % 2 else -1
    proc = subprocess.Popen(
        [FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(dst)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame in frames(img, duration, direction):
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg falló:\n{proc.stderr.read().decode('utf-8', 'replace')[-1500:]}")
    finally:
        if proc.poll() is None:
            proc.kill()
    return dst


def cached(photo: str | Path, duration: float) -> Path:
    from . import config

    p = Path(photo)
    st = p.stat()
    # A medios segundos: un corte que se mueve 10 ms en una reedición no vuelve a renderizar la foto
    # (el montaje ya recorta el clip a la duración exacta con trim).
    canon = math.ceil(max(0.5, duration) * 2) / 2
    key = hashlib.sha1(json.dumps([str(p), st.st_size, st.st_mtime, canon, 2]).encode()).hexdigest()[:16]
    out = config.HOME / "cache" / "paralaje" / f"{key}.mp4"
    if not out.exists():
        tmp = out.with_suffix(".tmp.mp4")
        render(p, canon, tmp)
        tmp.replace(out)
    return out
