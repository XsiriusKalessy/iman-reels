"""Tarjetas explicativas animadas: de 2 a 6 cosas con su icono que entran una a una y luego se van
resaltando por turnos mientras las nombras ("uno para cada problema").

Se pinta como un vídeo a pantalla completa (igual que el mapa) y entra como plano de apoyo, con el creador
en el círculo de arriba a la derecha. Los iconos son emojis de Noto Color Emoji (OFL), que viajan con la app.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .stickers import _emoji
from .textfit import FILES, FONTS_DIR

W, H, FPS = 1080, 1920, 30
BG, INK, MUTED = (244, 236, 223), (20, 21, 24), (120, 112, 100)
_EMOJI = re.compile(r"^\s*([^\w\s]{1,4}️?)\s*(.*)$")


def items(text: str) -> list[tuple[str, str]]:
    """"📄 Contratos | 🔒 Privacidad" → [("📄", "Contratos"), ("🔒", "Privacidad")]; sin emoji, un punto."""
    out = []
    for part in text.split("|")[:6]:
        part = " ".join(part.split())
        if not part:
            continue
        m = _EMOJI.match(part)
        icon, label = (m.group(1), m.group(2)) if m and m.group(2) else ("", part)
        out.append((icon, label[:22]))
    return out


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / FILES[name]), size)


def _ease(u: float) -> float:
    """Sale rápido y frena con un pelín de rebote."""
    u = min(max(u, 0.0), 1.0)
    return 1 + 2.2 * (u - 1) ** 3 + 1.2 * (u - 1) ** 2


def _card(icon: str, label: str, w: int, h: int, accent: tuple, on: bool) -> Image.Image:
    pad = 30
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 10, pad + w, pad + h + 10), 34, fill=(0, 0, 0, 70 if on else 40))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((pad, pad, pad + w, pad + h), 34, fill=(255, 255, 255, 255),
                        outline=accent + (255,) if on else (226, 218, 205, 255), width=7 if on else 2)
    circle = int(h * 0.46)
    cx, cy = pad + w // 2, pad + int(h * 0.36)
    d.ellipse((cx - circle // 2, cy - circle // 2, cx + circle // 2, cy + circle // 2),
              fill=accent + (255,) if on else (236, 228, 214, 255))
    pic = _emoji(icon) if icon else None
    if pic is not None:
        side = int(circle * 0.62)
        pic = pic.resize((side, int(side * pic.height / pic.width)), Image.LANCZOS)
        im.alpha_composite(pic, (cx - pic.width // 2, cy - pic.height // 2))
    else:
        d.ellipse((cx - 14, cy - 14, cx + 14, cy + 14), fill=(255, 255, 255, 255) if on else accent + (255,))
    size = 44
    font = _font("Figtree ExtraBold", size)
    while font.getlength(label) > w - 36 and size > 24:
        size -= 2
        font = _font("Figtree ExtraBold", size)
    d.text((cx, pad + int(h * 0.80)), label, font=font, fill=INK + (255,) if on else MUTED + (255,), anchor="mm")
    return im


def render(entries: list[tuple[str, str]], duration: float, dst: Path, title: str = "",
           accent: str = "#FF5547") -> Path:
    """Vídeo (1080x1920, 30 fps, sin sonido) de las tarjetas."""
    acc = tuple(int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    n = len(entries)
    cols = 2 if n in (2, 4) else 3
    rows = math.ceil(n / cols)
    gap = 34
    cw = (W - 120 - gap * (cols - 1)) // cols
    ch = min(int(cw * 1.05), (640 - gap * (rows - 1)) // rows)
    top = 640 + (640 - (rows * ch + gap * (rows - 1))) // 2  # entre el título y los subtítulos
    cards = [(_card(i, lab, cw, ch, acc, False), _card(i, lab, cw, ch, acc, True)) for i, lab in entries]
    pos = [(60 + (k % cols) * (cw + gap) - 30, top + (k // cols) * (ch + gap) - 30) for k in range(n)]
    # Fila incompleta: centrada.
    last = n % cols
    if last:
        shift = (cols - last) * (cw + gap) // 2
        pos = [(x + shift, y) if k >= n - last else (x, y) for k, (x, y) in enumerate(pos)]
    base = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(base)
    if title:
        size = 84
        font = _font("Figtree ExtraBold", size)
        words = title.split()
        lines = [title]
        if font.getlength(title) > 640 and len(words) > 1:  # en dos líneas, a la izquierda del círculo
            half = len(words) // 2
            lines = [" ".join(words[:half]), " ".join(words[half:])]
        while max(font.getlength(ln) for ln in lines) > 640 and size > 44:
            size -= 4
            font = _font("Figtree ExtraBold", size)
        for i, ln in enumerate(lines):
            parts = ln.rsplit(" ", 1) if i == len(lines) - 1 and " " in ln else ["", ln] if i == len(lines) - 1 else [ln, ""]
            x, y = 70, 300 + i * int(size * 1.12)
            d.text((x, y), parts[0] + (" " if parts[0] and parts[1] else ""), font=font, fill=INK)
            x += font.getlength(parts[0] + (" " if parts[0] and parts[1] else ""))
            # La última palabra, en el color de la marca (más oscuro si es claro: sobre crema no se leería).
            light = 0.299 * acc[0] + 0.587 * acc[1] + 0.114 * acc[2] > 165
            d.text((x, y), parts[1], font=font, fill=tuple(int(c * 0.62) for c in acc) if light else acc)
    intro = min(0.35 + 0.18 * n, duration * 0.45)
    step = max(0.45, (duration - intro - 0.3) / n)
    dst.parent.mkdir(parents=True, exist_ok=True)
    from .media import FFMPEG

    proc = subprocess.Popen(
        [FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(dst)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in range(max(1, int(round(duration * FPS)))):
            t = f / FPS
            frame = base.copy()
            active = int((t - intro) / step) if t >= intro else -1
            for k, ((off, on), (x, y)) in enumerate(zip(cards, pos)):
                u = (t - 0.12 * k) / 0.35  # entran una a una
                if u <= 0:
                    continue
                s = _ease(u)
                card = on if k == min(active, n - 1) else off
                if k == active:
                    s *= 1 + 0.07 * min(1.0, (t - intro - active * step) / 0.15)
                if abs(s - 1) > 0.01:
                    card = card.resize((max(1, int(card.width * s)), max(1, int(card.height * s))), Image.BILINEAR)
                if active >= 0 and k != active:
                    card = card.copy()
                    card.putalpha(card.getchannel("A").point(lambda a: int(a * 0.55)))
                frame.alpha_composite(card, (int(x + (off.width - card.width) / 2), int(y + (off.height - card.height) / 2)))
            proc.stdin.write(frame.convert("RGB").tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg falló:\n{proc.stderr.read().decode('utf-8', 'replace')[-1500:]}")
    finally:
        if proc.poll() is None:
            proc.kill()
    return dst


def cached(entries: list[tuple[str, str]], duration: float, title: str = "", accent: str = "#FF5547") -> Path:
    from . import config

    key = hashlib.sha1(json.dumps([entries, round(duration, 2), title, accent, 1]).encode()).hexdigest()[:16]
    out = config.HOME / "cache" / "tarjetas" / f"{key}.mp4"
    if not out.exists():
        tmp = out.with_suffix(".tmp.mp4")
        render(entries, duration, tmp, title.strip()[:40], accent)
        tmp.replace(out)
    return out
