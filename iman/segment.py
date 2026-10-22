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
MASK_W, MASK_H = 288, 512  # el modelo trabaja a 256 px; más no mejora el borde


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
    frame_bytes = MASK_W * MASK_H * 3
    reader = subprocess.Popen(
        [media.FFMPEG, "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={MASK_W}:{MASK_H}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE,
    )
    writer = subprocess.Popen(
        [media.FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{MASK_W}x{MASK_H}",
         "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(out)],
        stdin=subprocess.PIPE,
    )
    blank = np.zeros((MASK_H, MASK_W), np.uint8)
    prev = None
    i = 0
    try:
        while True:
            buf = reader.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            t = i / fps
            if any(a - 0.2 <= t <= b + 0.2 for a, b in windows):
                frame = np.frombuffer(buf, np.uint8).reshape(MASK_H, MASK_W, 3)
                res = seg.segment_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame)),
                                            int(t * 1000))
                conf = res.confidence_masks[0].numpy_view().reshape(MASK_H, MASK_W)
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
