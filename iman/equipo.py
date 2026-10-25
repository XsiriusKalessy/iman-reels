"""Cómo de potente es el ordenador, para decidir solo si hace falta el «modo ligero».

En un portátil sencillo (pocos núcleos, poca memoria) lo que más pesa es recortar a la persona fotograma a
fotograma (texto detrás de ti, anillo, lluvia, cambio de fondo), seguir las manos y la cabeza, el 3D y el 4K. En
modo ligero Imán se salta esos efectos y monta el reel igual de bien con el resto, así que sale rápido en cualquier
ordenador, sin servidores de pago.
"""

from __future__ import annotations

import os
import platform
import shutil

MIN_CORES = 4  # con 4 hilos o menos, mejor ligero
MIN_RAM_GB = 8

# Efectos que recortan o siguen a la persona en cada fotograma, o que dibujan en 3D: lo más pesado.
HEAVY_EFFECTS = {"detras", "fondo", "desenfoque", "anillo", "lluvia", "texto3d", "particulas", "etiqueta", "mosaico"}


def ram_gb() -> float:
    try:
        if platform.system() == "Windows":
            import ctypes

            class _Mem(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            m = _Mem()
            m.dwLength = ctypes.sizeof(_Mem)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 1024 ** 3
        if platform.system() == "Darwin":
            import subprocess

            return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 1024 ** 3
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
    except Exception:  # noqa: BLE001 - si no se sabe, no se frena a nadie
        return 16.0


def gpu() -> bool:
    """Tarjeta gráfica NVIDIA o un Mac con chip de Apple (los dos aceleran)."""
    return bool(shutil.which("nvidia-smi")) or (platform.system() == "Darwin" and platform.machine() == "arm64")


def info() -> dict:
    cores = os.cpu_count() or 2
    ram = round(ram_gb(), 1)
    weak = cores <= MIN_CORES or ram < MIN_RAM_GB
    return {"cores": cores, "ram_gb": ram, "gpu": gpu(), "weak": weak}


def ligero(setting: str) -> bool:
    """`setting`: "auto" (lo decide el ordenador), "si" o "no"."""
    if setting in ("si", "no"):
        return setting == "si"
    return info()["weak"]
