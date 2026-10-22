"""Tus manos en el vídeo (modelo de MediaPipe, en local).

Sirve para los efectos que reaccionan a lo que haces: la palabra que sube con tu dedo,
el choque (la palabra salta en pedazos cuando la tocas) y lo que dices aparece donde señalas.
Se analiza la toma original una vez, a pocos fotogramas por segundo, y se guarda en manos.json.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import media

MODEL = Path(__file__).parent / "assets" / "models" / "hand_landmarker.task"
FPS = 10
WIDTH = 360

# Puntos de la mano del modelo: muñeca, nudillos y yemas.
WRIST, INDEX_MCP, INDEX_PIP, INDEX_TIP = 0, 5, 6, 8
FINGERS = [(9, 10, 12), (13, 14, 16), (17, 18, 20)]  # corazón, anular, meñique: (nudillo, falange, yema)


def available() -> bool:
    try:
        import mediapipe  # noqa: F401
    except Exception:
        return False
    return MODEL.exists()


def track(src: Path, cache: Path | None = None) -> list[dict]:
    """Por cada fotograma analizado: {"t": segundos, "hands": [[[x, y] × 21], …]} en coordenadas 0-1 de la toma."""
    if cache is not None and cache.exists():
        return json.loads(cache.read_text())
    import mediapipe as mp
    import numpy as np
    from mediapipe.tasks.python import BaseOptions, vision

    info = media.probe(src)
    w = WIDTH
    h = int(round(WIDTH * info.height / info.width / 2)) * 2
    opts = vision.HandLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(MODEL)),
                                        running_mode=vision.RunningMode.VIDEO, num_hands=2,
                                        min_hand_detection_confidence=0.5, min_tracking_confidence=0.5)
    marker = vision.HandLandmarker.create_from_options(opts)
    reader = subprocess.Popen([media.FFMPEG, "-v", "error", "-i", str(src), "-vf", f"fps={FPS},scale={w}:{h}",
                               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    frames, size, i = [], w * h * 3, 0
    try:
        while True:
            buf = reader.stdout.read(size)
            if len(buf) < size:
                break
            img = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            res = marker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img)),
                                          int(i * 1000 / FPS))
            hands = [[[round(p.x, 4), round(p.y, 4)] for p in lm] for lm in res.hand_landmarks]
            frames.append({"t": round(i / FPS, 3), "hands": hands})
            i += 1
    finally:
        reader.stdout.close()
        reader.wait()
        marker.close()
    if cache is not None:
        cache.write_text(json.dumps(frames))
    return frames


def _dist(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def pointing(hand: list) -> tuple[float, float] | None:
    """Si la mano señala con el índice (los otros dedos recogidos), la dirección en la que señala."""
    wrist, mcp, pip, tip = hand[WRIST], hand[INDEX_MCP], hand[INDEX_PIP], hand[INDEX_TIP]
    if _dist(tip, wrist) < _dist(pip, wrist) * 1.15:
        return None  # el índice no está estirado
    curled = sum(_dist(hand[t], wrist) < _dist(hand[p], wrist) * 1.05 for _, p, t in FINGERS)
    if curled < 2:
        return None  # mano abierta, no señala
    d = (tip[0] - mcp[0], tip[1] - mcp[1])
    n = (d[0] ** 2 + d[1] ** 2) ** 0.5 or 1.0
    return d[0] / n, d[1] / n


@dataclass
class Gesture:
    kind: str  # "sube" (dedo hacia arriba que se mueve) | "senala" (señala y se queda)
    start: float
    end: float
    path: list[tuple[float, float, float]]  # (t, x, y) de la yema del índice, coordenadas de la toma
    direction: tuple[float, float]


def gestures(frames: list[dict], min_hold: float = 0.4) -> list[Gesture]:
    """Busca los momentos en que señalas: hacia arriba subiendo el dedo, o hacia un lado para enseñar algo."""
    out: list[Gesture] = []
    run: list[tuple[float, float, float, tuple[float, float]]] = []

    def close():
        if len(run) < 2 or run[-1][0] - run[0][0] < min_hold:
            return
        rise = run[0][2] - min(p[2] for p in run)
        dx = sum(p[3][0] for p in run) / len(run)
        dy = sum(p[3][1] for p in run) / len(run)
        kind = "sube" if dy < -0.6 and rise > 0.08 else "senala"
        out.append(Gesture(kind, run[0][0], run[-1][0] + 1 / FPS, [(t, x, y) for t, x, y, _ in run], (dx, dy)))

    for f in frames:
        hit = None
        for hand in f["hands"]:
            d = pointing(hand)
            if d is not None:
                hit = (f["t"], *hand[INDEX_TIP], d)
                break
        if hit and (not run or hit[0] - run[-1][0] <= 2.5 / FPS):
            run.append(hit)
        else:
            close()
            run = [hit] if hit else []
    close()
    return out


def near(frames: list[dict], t0: float, t1: float, box: tuple[float, float, float, float]) -> float | None:
    """Primer momento entre t0 y t1 en que alguna yema o la palma entra en `box` (x0, y0, x1, y1, coords 0-1)."""
    x0, y0, x1, y1 = box
    for f in frames:
        if not t0 <= f["t"] <= t1:
            continue
        for hand in f["hands"]:
            for k in (WRIST, 4, 8, 12, 16, 20, 9):
                x, y = hand[k]
                if x0 <= x <= x1 and y0 <= y <= y1:
                    return f["t"]
    return None
