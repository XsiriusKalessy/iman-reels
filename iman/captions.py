"""Subtítulos animados y título del gancho en formato ASS (libass)."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Word

W, H = 1080, 1920


@dataclass(frozen=True)
class Style:
    key: str
    label: str
    font: str
    size: int
    text: str  # color del texto en &HBBGGRR
    accent: str  # palabra activa / destacada
    outline: str
    outline_w: float
    shadow: float
    uppercase: bool
    title_font: str
    title_size: int
    title_box: str  # color de la caja del título
    title_text: str
    max_words: int = 3
    max_chars: int = 16
    y: int = 1340  # altura de los subtítulos
    pop: bool = True  # la palabra activa crece un poco
    box: str = ""  # color de caja detrás de cada bloque (vacío = sin caja)
    # Cómo entra cada bloque: pop (crece), muelle (rebota), sube (sube desenfocado), enfoque (se enfoca).
    entry: str = "pop"
    # Si tiene fuente alternativa, las palabras destacadas salen solas, enormes y con esa fuente.
    alt_font: str = ""
    alt_size: int = 0


def rgb(hex6: str) -> str:
    """'#RRGGBB' -> '&H00BBGGRR' (formato ASS)."""
    h = hex6.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


STYLES: dict[str, Style] = {
    "impacto": Style(
        "impacto", "Impacto", "Montserrat Black", 84, rgb("#FFFFFF"), rgb("#FFE14D"), rgb("#000000"),
        6, 0, True, "Anton", 104, rgb("#111111"), rgb("#FFFFFF"),
    ),
    "editorial": Style(
        "editorial", "Editorial", "Playfair Display ExtraBold", 88, rgb("#FFFFFF"), rgb("#7CF5D8"),
        rgb("#101010"), 4, 2, False, "Playfair Display ExtraBold", 96, rgb("#FFFFFF"), rgb("#111111"),
        max_words=3, max_chars=18,
    ),
    "palabra": Style(
        "palabra", "Palabra a palabra", "Playfair Display ExtraBold", 132, rgb("#FFFFFF"), rgb("#FFFFFF"),
        rgb("#000000"), 0, 4, False, "Montserrat Black", 72, rgb("#111111"), rgb("#FFFFFF"),
        max_words=1, max_chars=40, y=1240,
    ),
    "karaoke": Style(
        "karaoke", "Karaoke", "Figtree ExtraBold", 70, rgb("#FFFFFF"), rgb("#FF4F7B"), rgb("#000000"),
        2, 3, False, "Figtree ExtraBold", 84, rgb("#FFFFFF"), rgb("#141518"), max_words=7, max_chars=30, y=1300, pop=False,
    ),
    "caja": Style(
        "caja", "Caja", "Playfair Display ExtraBold", 64, rgb("#FFFFFF"), rgb("#7CF5D8"), rgb("#123A35"),
        14, 0, False, "Playfair Display ExtraBold", 88, rgb("#123A35"), rgb("#FFFFFF"),
        max_words=4, max_chars=22, y=1380, pop=False, box=rgb("#123A35"),
    ),
    "neon": Style(
        "neon", "Neón", "Anton", 96, rgb("#FFFFFF"), rgb("#39FF88"), rgb("#0A0A0A"),
        5, 0, True, "Anton", 112, rgb("#39FF88"), rgb("#0A0A0A"), max_words=2, max_chars=14,
    ),
    "gigante": Style(
        "gigante", "Gigante", "Anton", 230, rgb("#FFFFFF"), rgb("#FFE14D"), rgb("#000000"),
        7, 0, True, "Anton", 112, rgb("#FFE14D"), rgb("#111111"), max_words=1, max_chars=40, y=1230,
        pop=False, entry="muelle",
    ),
    "mezcla": Style(
        "mezcla", "Mezcla", "Figtree ExtraBold", 68, rgb("#FFFFFF"), rgb("#FF4F7B"), rgb("#000000"),
        2, 3, False, "Figtree ExtraBold", 84, rgb("#FFFFFF"), rgb("#141518"), max_words=5, max_chars=26, y=1320,
        pop=False, entry="sube", alt_font="Playfair Display ExtraBold", alt_size=150,
    ),
    "minimal": Style(
        "minimal", "Minimal", "Figtree SemiBold", 66, rgb("#FFFFFF"), rgb("#FFD84D"), rgb("#000000"),
        0, 3, False, "Figtree ExtraBold", 84, rgb("#FFFFFF"), rgb("#141518"), max_words=5, max_chars=28, y=1340,
        pop=False, entry="sube",
    ),
    "elegante": Style(
        "elegante", "Elegante", "Playfair Display ExtraBold", 86, rgb("#FFFFFF"), rgb("#F2C46D"), rgb("#000000"),
        0, 3, False, "Playfair Display ExtraBold", 92, rgb("#F4ECDF"), rgb("#1A1A1A"), max_words=3, max_chars=20,
        pop=False, entry="enfoque",
    ),
    "manuscrita": Style(
        "manuscrita", "Manuscrita", "Caveat", 140, rgb("#FFFFFF"), rgb("#FFE14D"), rgb("#000000"),
        0, 4, False, "Caveat", 120, rgb("#FFFFFF"), rgb("#141518"), max_words=3, max_chars=22, y=1300,
        pop=False, entry="sube",
    ),
    "marcador": Style(
        "marcador", "Marcador", "Montserrat Black", 74, rgb("#111111"), rgb("#E0322C"), rgb("#FFE14D"),
        16, 0, True, "Montserrat Black", 96, rgb("#FFE14D"), rgb("#111111"), max_words=3, max_chars=16, y=1360,
        pop=False, box=rgb("#FFE14D"), entry="muelle",
    ),
}

# Animaciones de entrada (ASS): suaves, con un pequeño rebote o desenfoque, como el motion de las apps modernas.
ENTRIES = {
    # Rebote: crece al 120 % y vuelve al 100 % (overshoot), suave pero con impacto.
    "pop": r"\fscx70\fscy70\t(0,90,\fscx120\fscy120)\t(90,190,\fscx100\fscy100)",
    "muelle": r"\fscx55\fscy55\t(0,120,\fscx116\fscy116)\t(120,200,\fscx95\fscy95)\t(200,260,\fscx100\fscy100)",
    "sube": r"\alpha&HFF&\blur6\t(0,180,\alpha&H00&\blur0)",
    "enfoque": r"\alpha&HFF&\blur16\fscx108\fscy108\t(0,240,\alpha&H00&\blur0\fscx100\fscy100)",
}


def _place(entry: str, y: int) -> str:
    """Posición del bloque; «sube» entra desde 36 px más abajo."""
    return f"\\move(540,{y + 36},540,{y},0,180)" if entry == "sube" else f"\\pos(540,{y})"


def _ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def group_words(words: list[Word], max_words: int, max_chars: int, pause: float = 0.35) -> list[list[int]]:
    """Agrupa palabras en bloques cortos que caben en pantalla."""
    groups: list[list[int]] = []
    cur: list[int] = []
    for i, w in enumerate(words):
        if cur:
            prev = words[cur[-1]]
            chars = sum(len(words[k].text) + 1 for k in cur) + len(w.text)
            ends_sentence = prev.text.rstrip()[-1:] in ".?!,:;"
            if len(cur) >= max_words or chars > max_chars or w.start - prev.end > pause or ends_sentence:
                groups.append(cur)
                cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    return groups


def build_ass(
    words: list[Word],
    style: Style,
    duration: float,
    hook_title: str = "",
    emphasis: set[int] | None = None,
    hook_seconds: float = 2.8,
    extra_events: list[str] | None = None,
    hide: list | None = None,
) -> str:
    """`words` ya están en la línea de tiempo del reel. `emphasis` son índices de `words`."""
    emphasis = emphasis or set()
    hide = hide or []

    def visible(a: float, b: float) -> list[tuple[float, float]]:
        """Recorta [a, b) quitando los tramos en los que hay un efecto a pantalla completa."""
        parts = [(a, b)]
        for win in hide:
            nxt = []
            for x, y in parts:
                if win.end <= x or win.start >= y:
                    nxt.append((x, y))
                    continue
                if x < win.start:
                    nxt.append((x, win.start))
                if win.end < y:
                    nxt.append((win.end, y))
            parts = nxt
        return [(x, y) for x, y in parts if y - x > 0.03]
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Sub,{style.font},{style.size},{style.text},{style.accent},{style.outline},&H80000000,"
        f"0,0,0,0,100,100,0,0,1,{style.outline_w},{style.shadow},5,60,60,0,1",
        f"Style: Box,{style.font},{style.size},{style.text},{style.accent},{style.box or style.outline},"
        f"{style.box or style.outline},0,0,0,0,100,100,0,0,3,{style.outline_w},0,5,60,60,0,1",
        f"Style: Hook,{style.title_font},{style.title_size},{style.title_text},{style.title_text},"
        f"{style.title_box},{style.title_box},0,0,0,0,100,100,0,0,3,28,0,5,90,90,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    hook_end = 0.0
    if hook_title:
        hook_end = min(hook_seconds, duration)
        # Si un efecto a pantalla completa empieza pronto, el gancho le deja sitio.
        for win in hide:
            if 0.8 < win.start < hook_end:
                hook_end = win.start
        title = _esc(hook_title.upper() if style.uppercase else hook_title)
        anim = r"{\pos(540,560)\fad(120,200)\fscx70\fscy70\t(0,180,\fscx104\fscy104)\t(180,260,\fscx100\fscy100)}"
        lines.append(f"Dialogue: 2,{_ts(0)},{_ts(hook_end)},Hook,,0,0,0,,{anim}{title}")

    groups = group_words(words, style.max_words, style.max_chars)
    if style.alt_font and emphasis:
        # Las palabras destacadas salen solas, con la fuente alternativa.
        split = []
        for g in groups:
            cur = []
            for k in g:
                if k in emphasis:
                    if cur:
                        split.append(cur)
                    split.append([k])
                    cur = []
                else:
                    cur.append(k)
            if cur:
                split.append(cur)
        groups = split
    for group in groups:
        solo = bool(style.alt_font) and len(group) == 1 and group[0] in emphasis
        g_start = words[group[0]].start
        g_end = words[group[-1]].end
        # Cada bloque dura hasta que empieza el siguiente (máx. 0.6 s de cola).
        nxt = group[-1] + 1
        tail = min(g_end + 0.6, words[nxt].start) if nxt < len(words) else min(g_end + 0.6, duration)
        for pos, k in enumerate(group):
            seg_start = words[k].start if pos else g_start
            seg_end = words[group[pos + 1]].start if pos + 1 < len(group) else tail
            if seg_end <= seg_start:
                continue
            parts = []
            for kk in group:
                txt = _esc(words[kk].text.upper() if style.uppercase else words[kk].text)
                txt = txt.rstrip(",;:.") if style.uppercase else txt
                if kk == k and pos == 0:
                    # El bloque entero ya entra con "pop"; aquí solo cambia el color.
                    parts.append(r"{\c" + style.accent + "&}" + txt + r"{\c" + style.text + "&}")
                elif kk == k and not style.pop:
                    parts.append(r"{\c" + style.accent + "&}" + txt + r"{\c" + style.text + "&}")
                elif kk == k:
                    parts.append(
                        r"{\c" + style.accent + r"&\fscx100\fscy100\t(0,90,\fscx112\fscy112)\t(90,160,\fscx106\fscy106)}"
                        + txt + r"{\c" + style.text + r"&\fscx100\fscy100}"
                    )
                elif kk in emphasis:
                    parts.append(r"{\c" + style.accent + "&}" + txt + r"{\c" + style.text + "&}")
                else:
                    parts.append(txt)
            entry = "muelle" if solo else style.entry
            pop = ENTRIES.get(entry, ENTRIES["pop"]) if pos == 0 else ""
            y = style.y - 40 if solo else style.y
            place = _place(entry, y) if pos == 0 else f"\\pos(540,{y})"
            font = f"\\fn{style.alt_font}\\fs{style.alt_size}\\c{style.accent}&" if solo else ""
            for a, b in visible(seg_start, seg_end):
                lines.append(
                    f"Dialogue: 1,{_ts(a)},{_ts(b)},{'Box' if style.box else 'Sub'},,0,0,0,,{{{place}{font}{pop}}}"
                    + " ".join(parts)
                )
    lines += extra_events or []
    return "\n".join(lines) + "\n"
