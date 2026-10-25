"""Quitar ruido fuerte de la voz (calle, tráfico, viento, aire acondicionado) sin modelos de pago ni descargas.

Puerta espectral: se mide el ruido de fondo de cada frecuencia en los ratos sin voz (mínimo de los últimos
segundos, así sigue al ruido si cambia) y se baja lo que no sobresale de él. Nunca se quita del todo (como
mucho unos 14 dB) y la ganancia se suaviza en tiempo y frecuencia: mejor un poco de ambiente que una voz
metálica o con burbujitas.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from .media import FFMPEG

SR = 48000
N_FFT, HOP = 2048, 512
FLOOR = 10 ** (-14 / 20)  # lo máximo que se baja el ruido
OVER = 2.0  # cuánto por encima del ruido tiene que estar algo para quedarse entero
CHUNK, PAD = 60 * SR, SR  # trozos de un minuto con un segundo de margen a cada lado


def _stft(x: np.ndarray, win: np.ndarray) -> np.ndarray:
    n = 1 + (len(x) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    return np.fft.rfft(x[idx] * win, axis=1).astype(np.complex64)


def _istft(spec: np.ndarray, win: np.ndarray, length: int) -> np.ndarray:
    frames = np.fft.irfft(spec, n=N_FFT, axis=1).astype(np.float32) * win
    out = np.zeros(length, np.float32)
    norm = np.zeros(length, np.float32)
    for i, f in enumerate(frames):
        s = i * HOP
        out[s:s + N_FFT] += f
        norm[s:s + N_FFT] += win ** 2
    return out / np.maximum(norm, 1e-6)


def _running_min(p: np.ndarray, width: int) -> np.ndarray:
    """Mínimo de cada frecuencia en una ventana de `width` tramas centrada (por bloques, sin scipy)."""
    block = max(1, width // 4)
    n = p.shape[0]
    nb = -(-n // block)
    padded = np.full((nb * block, p.shape[1]), np.inf, np.float32)
    padded[:n] = p
    mins = padded.reshape(nb, block, -1).min(1)
    out = np.empty_like(mins)
    for b in range(nb):
        out[b] = mins[max(0, b - 2):b + 3].min(0)
    return np.repeat(out, block, axis=0)[:n]


def _smooth(g: np.ndarray, t: int = 3, f: int = 5) -> np.ndarray:
    k_t, k_f = np.ones(t, np.float32) / t, np.ones(f, np.float32) / f
    g = np.apply_along_axis(lambda c: np.convolve(c, k_t, mode="same"), 0, g)
    return np.apply_along_axis(lambda r: np.convolve(r, k_f, mode="same"), 1, g)


def denoise(x: np.ndarray) -> np.ndarray:
    """Audio mono float32 a 48 kHz → el mismo con el ruido de fondo bajado."""
    if len(x) < N_FFT * 4:
        return x
    out = np.zeros_like(x)
    win = np.hanning(N_FFT).astype(np.float32)
    for start in range(0, len(x), CHUNK):
        a, b = max(0, start - PAD), min(len(x), start + CHUNK + PAD)
        seg = np.pad(x[a:b], (N_FFT, N_FFT), mode="reflect")
        spec = _stft(seg, win)
        power = np.abs(spec) ** 2
        # Potencia suavizada en el tiempo y su mínimo en ~3 s: el ruido de fondo de cada frecuencia.
        smooth = power.copy()
        for i in range(1, len(smooth)):
            smooth[i] = 0.7 * smooth[i - 1] + 0.3 * power[i]
        noise = _running_min(smooth, int(3 * SR / HOP)) * 3
        gain = np.clip(1 - OVER * noise / np.maximum(power, 1e-12), 0, 1)
        gain = _smooth(np.maximum(np.sqrt(gain), FLOOR))
        clean = _istft(spec * gain, win, len(seg))[N_FFT:N_FFT + (b - a)]
        keep_a = start - a
        out[start:min(len(x), start + CHUNK)] = clean[keep_a:keep_a + min(CHUNK, len(x) - start)]
    return out


def read_audio(src: Path) -> np.ndarray:
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def clean_source(src: Path, workdir: Path) -> Path:
    """El vídeo con la voz limpia (la imagen se copia tal cual). Se guarda para no repetirlo al reeditar."""
    dst = workdir / "voz-limpia.mp4"
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst
    audio = denoise(read_audio(src))
    tmp = workdir / "voz-limpia.tmp.mp4"
    cmd = [FFMPEG, "-y", "-v", "error", "-i", str(src), "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
           "-map", "0:v:0", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(tmp)]
    res = subprocess.run(cmd, input=audio.astype(np.float32).tobytes(), capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falló:\n{res.stderr.decode('utf-8', 'replace')[-2000:]}")
    tmp.replace(dst)
    return dst
