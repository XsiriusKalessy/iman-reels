"""Energía del audio de un directo o una charla larga: dónde se sube la voz, se ríe o pasa algo.

Mide el volumen (RMS) segundo a segundo con ffmpeg y marca las ventanas con más energía respecto a la media del
propio vídeo. Sirve para que, de un directo, salgan los momentos con reacción y no solo los mejor explicados.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .media import FFMPEG


def levels(src: Path) -> list[float]:
    """RMS en dB por segundo (lista de -inf..0, con -99 donde hay silencio total)."""
    cmd = [FFMPEG, "-v", "info", "-nostats", "-i", str(src), "-vn", "-af",
           "aresample=16000,asetnsamples=n=16000:p=0,astats=metadata=1:reset=1,"
           "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-", "-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = []
    for m in re.finditer(r"lavfi\.astats\.Overall\.RMS_level=(-?[\d.]+|-inf)", res.stdout):
        v = m.group(1)
        out.append(-99.0 if v == "-inf" else max(-99.0, float(v)))
    return out


def peaks(lv: list[float], window: int = 8, top: float = 0.2, min_gap: int = 20) -> list[tuple[int, int]]:
    """Ventanas (segundo inicial, final) con más energía: la quinta parte más alta, separadas entre sí."""
    if len(lv) < window * 2:
        return []
    sums = [sum(lv[i:i + window]) / window for i in range(0, len(lv) - window + 1)]
    order = sorted(range(len(sums)), key=lambda i: -sums[i])
    want = max(1, int(len(sums) * top / window))
    chosen: list[int] = []
    for i in order:
        if all(abs(i - j) >= min_gap for j in chosen):
            chosen.append(i)
        if len(chosen) >= want:
            break
    return sorted((i, i + window) for i in chosen)


def hint(src: Path) -> str:
    """Texto para la IA: «MOMENTOS CON MÁS ENERGÍA: 02:10-02:18, …» (vacío si no hay nada claro)."""
    try:
        ps = peaks(levels(src))
    except Exception:  # noqa: BLE001 - sin energía se eligen por la transcripción
        return ""
    if not ps:
        return ""
    fmt = lambda s: f"{s // 60:02d}:{s % 60:02d}"  # noqa: E731
    return ("MOMENTOS CON MÁS ENERGÍA EN EL AUDIO (risas, subidas de voz, reacciones): "
            + ", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in ps[:12])
            + ". Es un directo: prioriza los tramos con reacción y lo que se entiende solo.")
