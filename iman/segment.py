"""Recorte de la persona fotograma a fotograma (modelo de MediaPipe, en local).

Sirve para los efectos que pasan por detrás del creador: texto gigante detrás,
fondo de color liso y fondo desenfocado. Solo se analiza el vídeo dentro de las
ventanas de esos efectos; fuera, la máscara va en negro.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from . import media

MODEL = Path(__file__).parent / "assets" / "models" / "selfie_segmenter.tflite"
MASK_W, MASK_H = 288, 512  # el modelo trabaja a 256 px; más no mejora su resultado
OUT_W, OUT_H = 540, 960  # la máscara final se afina a esta resolución siguiendo los bordes de la imagen


def _cv2():
    """OpenCV con el filtro guiado (viene con MediaPipe), o None si no está."""
    try:
        import cv2
    except Exception:  # noqa: BLE001
        return None
    return cv2 if hasattr(cv2, "ximgproc") else None


def _refine(cv2, frame: np.ndarray, conf: np.ndarray) -> np.ndarray:
    """Pega el borde de la máscara al pelo y al contorno reales del fotograma; agrandada tal cual, el pelo
    sale borroso."""
    guide = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    up = cv2.resize(conf.astype(np.float32), (OUT_W, OUT_H), interpolation=cv2.INTER_LINEAR)
    return np.clip(cv2.ximgproc.guidedFilter(guide, up, 6, 1e-3), 0, 1)


def available() -> bool:
    try:
        import mediapipe  # noqa: F401
    except Exception:
        return False
    return MODEL.exists()


def person_masks(video: Path, out: Path, windows: list[tuple[float, float]], fps: int = 30) -> Path:
    """Escribe en `out` un vídeo en grises: blanco donde está la persona."""
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    opts = vision.ImageSegmenterOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL)),
        running_mode=vision.RunningMode.VIDEO,
        output_confidence_masks=True,
        output_category_mask=False,
    )
    seg = vision.ImageSegmenter.create_from_options(opts)
    cv2 = _cv2()
    fw, fh = (OUT_W, OUT_H) if cv2 else (MASK_W, MASK_H)
    frame_bytes = fw * fh * 3
    reader = subprocess.Popen(
        [media.FFMPEG, "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={fw}:{fh}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE,
    )
    writer = subprocess.Popen(
        [media.FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{fw}x{fh}",
         "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(out)],
        stdin=subprocess.PIPE,
    )
    blank = np.zeros((fh, fw), np.uint8)
    prev = None
    i = 0
    try:
        while True:
            buf = reader.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            t = i / fps
            if any(a - 0.2 <= t <= b + 0.2 for a, b in windows):
                frame = np.frombuffer(buf, np.uint8).reshape(fh, fw, 3)
                small = cv2.resize(frame, (MASK_W, MASK_H), interpolation=cv2.INTER_AREA) if cv2 else frame
                res = seg.segment_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(small)),
                                            int(t * 1000))
                conf = res.confidence_masks[0].numpy_view().reshape(MASK_H, MASK_W)
                if cv2:
                    conf = _refine(cv2, frame, conf)
                # Suavizado en el tiempo para que el borde no tiemble.
                prev = conf if prev is None else 0.6 * conf + 0.4 * prev
                # Contraste: borde nítido pero sin dientes de sierra.
                mask = np.clip((prev - 0.35) / 0.3, 0, 1)
                writer.stdin.write((mask * 255).astype(np.uint8).tobytes())
            else:
                prev = None
                writer.stdin.write(blank.tobytes())
            i += 1
    finally:
        writer.stdin.close()
        writer.wait()
        reader.wait()
        seg.close()
    if writer.returncode != 0:
        raise RuntimeError("No he podido recortar a la persona")
    return out


def subject(img) -> tuple[float, float, float] | None:
    """Dónde está la persona en una foto (PIL): (centro x de la cabeza, alto de la cabeza, alto de la cara),
    en proporción a la imagen. None si no hay nadie o no está el modelo."""
    if not available():
        return None
    try:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        small = np.ascontiguousarray(np.asarray(img.convert("RGB").resize((MASK_W, MASK_H))))
        opts = vision.ImageSegmenterOptions(base_options=BaseOptions(model_asset_path=str(MODEL)),
                                            output_confidence_masks=True, output_category_mask=False)
        with vision.ImageSegmenter.create_from_options(opts) as seg:
            conf = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=small)).confidence_masks[0]
            m = conf.numpy_view().reshape(MASK_H, MASK_W) > 0.5
    except Exception:  # noqa: BLE001
        return None
    rows = np.nonzero(m.sum(axis=1) > MASK_W * 0.03)[0]
    if len(rows) < MASK_H * 0.1:
        return None
    top = rows[0]
    head = m[top: top + int(MASK_H * 0.12)]
    cols = np.nonzero(head.any(axis=0))[0]
    cx = (cols[0] + cols[-1]) / 2 / MASK_W if len(cols) else 0.5
    # La cara cae más o menos un cuarto del ancho de la cabeza por debajo de la coronilla.
    width = (cols[-1] - cols[0]) / MASK_W if len(cols) else 0.3
    face = top / MASK_H + max(0.06, width * 0.55 * MASK_W / MASK_H)
    return float(cx), float(top / MASK_H), float(min(0.95, face))


def person_mask(img):
    """Máscara (PIL "L", del tamaño de la foto) de la persona de una foto, con el borde pegado al pelo.
    None si no hay modelo o no se ve a nadie."""
    if not available():
        return None
    from PIL import Image

    try:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        rgb = img.convert("RGB")
        small = np.ascontiguousarray(np.asarray(rgb.resize((MASK_W, MASK_H))))
        opts = vision.ImageSegmenterOptions(base_options=BaseOptions(model_asset_path=str(MODEL)),
                                            output_confidence_masks=True, output_category_mask=False)
        with vision.ImageSegmenter.create_from_options(opts) as seg:
            conf = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=small)).confidence_masks[0]
            conf = conf.numpy_view().reshape(MASK_H, MASK_W).astype(np.float32)
    except Exception:  # noqa: BLE001
        return None
    if (conf > 0.5).mean() < 0.02:
        return None
    w, h = rgb.size
    cv2 = _cv2()
    if cv2:
        frame = np.asarray(rgb)
        guide = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
        up = cv2.resize(conf, (w, h), interpolation=cv2.INTER_LINEAR)
        conf = np.clip(cv2.ximgproc.guidedFilter(guide, up, max(4, w // 160), 1e-3), 0, 1)
    else:
        conf = np.asarray(Image.fromarray((conf * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)) / 255
    mask = np.clip((conf - 0.35) / 0.3, 0, 1)
    return Image.fromarray((mask * 255).astype(np.uint8), "L")
