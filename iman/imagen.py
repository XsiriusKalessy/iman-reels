"""Herramientas de foto: quitar el fondo, mejorar una foto y reiluminarla.

Todo en local con el mismo recorte de persona que el resto de Imán (sin servicios de pago). Sirven para las
fotos de apoyo, las portadas o lo que quieras publicar aparte.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from . import segment

MAX_SIDE = 2400  # más grande no se nota en redes y tarda mucho
LIGHTS = {"estudio": "Estudio", "calida": "Atardecer", "fria": "Luz fría", "neon": "Neón"}


class NoPerson(ValueError):
    pass


def load(path) -> Image.Image:
    with Image.open(path) as im:
        img = ImageOps.exif_transpose(im)
        img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return img


def _mask(img: Image.Image) -> Image.Image:
    mask = segment.person_mask(img.convert("RGB"))
    if mask is None or np.asarray(mask).mean() < 255 * 0.02:
        raise NoPerson("No veo a ninguna persona en la foto: el recorte funciona con personas.")
    return mask


def quitar_fondo(img: Image.Image) -> Image.Image:
    """La persona recortada sobre transparente (PNG), recortada a su tamaño con un pequeño margen."""
    mask = _mask(img)
    out = img.convert("RGBA")
    out.putalpha(mask)
    box = mask.point(lambda v: 255 if v > 30 else 0).getbbox()
    if box:
        pad = int(max(img.size) * 0.02)
        out = out.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(img.width, box[2] + pad),
                        min(img.height, box[3] + pad)))
    return out


def _gray_world(a: np.ndarray, k: float = 0.5) -> np.ndarray:
    """Corrige a medias el tono de la luz (la foto amarillenta o azulada), sin dejarla gris."""
    means = a.reshape(-1, 3).mean(0) + 1e-3
    gain = (means.mean() / means) ** k
    return np.clip(a * gain, 0, 255)


def mejorar(img: Image.Image) -> Image.Image:
    """Mejora automática: color de la luz, niveles, algo de viveza, ruido fuera y nitidez. Si es pequeña, la
    agranda a 1080 px por el lado corto (redes)."""
    alpha = img.getchannel("A") if img.mode == "RGBA" else None
    rgb = img.convert("RGB")
    try:
        import cv2

        a = np.asarray(rgb)
        if max(rgb.size) <= 2000:  # quitar ruido es lento en fotos enormes; ahí casi no hace falta
            a = cv2.fastNlMeansDenoisingColored(a, None, 3, 3, 7, 21)
        rgb = Image.fromarray(a)
    except Exception:  # noqa: BLE001 - sin OpenCV: sin quitar ruido
        pass
    rgb = Image.fromarray(_gray_world(np.asarray(rgb, np.float32)).astype(np.uint8))
    rgb = ImageOps.autocontrast(rgb, cutoff=0.6, preserve_tone=True)
    # Sombras un poco más abiertas (curva suave) para caras a contraluz.
    lut = [int(255 * ((i / 255) ** 0.92)) for i in range(256)]
    rgb = rgb.point(lut * 3)
    rgb = ImageEnhance.Color(rgb).enhance(1.12)
    short = min(rgb.size)
    if short < 1080:
        k = 1080 / short
        rgb = rgb.resize((round(rgb.width * k), round(rgb.height * k)), Image.LANCZOS)
        if alpha is not None:
            alpha = alpha.resize(rgb.size, Image.LANCZOS)
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.6, percent=80, threshold=3))
    if alpha is not None:
        rgb.putalpha(alpha)
    return rgb


def reiluminar(img: Image.Image, light: str = "estudio", side: str = "izquierda") -> Image.Image:
    """Cambia la luz de la foto: el fondo se apaga un poco, a ti te entra una luz por un lado (o dos, en neón)
    y un brillo de borde que te separa del fondo."""
    rgb = img.convert("RGB")
    mask = _mask(rgb)
    key, rim, bg_k = {
        "estudio": ((255, 244, 230), (255, 255, 255), 0.55),
        "calida": ((255, 170, 90), (255, 200, 140), 0.6),
        "fria": ((150, 200, 255), (200, 225, 255), 0.6),
        "neon": ((255, 60, 170), (60, 200, 255), 0.45),
    }.get(light, ((255, 244, 230), (255, 255, 255), 0.55))
    w, h = rgb.size
    # Fondo más oscuro y un poco desenfocado: la persona gana protagonismo.
    bg = rgb.filter(ImageFilter.GaussianBlur(max(rgb.size) / 400))
    bg = ImageEnhance.Brightness(ImageEnhance.Color(bg).enhance(0.8)).enhance(bg_k)
    # Persona: luz que entra por un lado (y sombra suave en el otro); en neón, una de cada color.
    ramp = np.linspace(1, 0, w) if side == "izquierda" else np.linspace(0, 1, w)
    ramp = (ramp ** 1.4)[None, :, None]
    gain = 0.78 + 0.55 * ramp * (np.array(key, np.float32) / 255)
    if light == "neon":
        gain = gain + 0.5 * (1 - ramp) ** 1.4 * (np.array(rim, np.float32) / 255) - 0.1
    person = Image.fromarray(np.clip(np.asarray(rgb, np.float32) * gain, 0, 255).astype(np.uint8))
    person = ImageEnhance.Contrast(person).enhance(1.06)
    out = Image.composite(person, bg, mask)
    # Luz de borde: el contorno de la persona brilla un poco del color de la luz de atrás.
    edge = ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(9))).filter(ImageFilter.GaussianBlur(3))
    glow = Image.new("RGB", rgb.size, rim)
    out = Image.composite(glow, out, edge.point(lambda v: int(v * 0.45)))
    return out
