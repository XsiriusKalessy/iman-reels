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
