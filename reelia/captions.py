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
    "neon": Style(
        "neon", "Neón", "Anton", 96, rgb("#FFFFFF"), rgb("#39FF88"), rgb("#0A0A0A"),
        5, 0, True, "Anton", 112, rgb("#39FF88"), rgb("#0A0A0A"), max_words=2, max_chars=14,
    ),
}


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
) -> str:
    """`words` ya están en la línea de tiempo del reel. `emphasis` son índices de `words`."""
    emphasis = emphasis or set()
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
        f"Style: Hook,{style.title_font},{style.title_size},{style.title_text},{style.title_text},"
        f"{style.title_box},{style.title_box},0,0,0,0,100,100,0,0,3,28,0,5,90,90,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    hook_end = 0.0
    if hook_title:
        hook_end = min(hook_seconds, duration)
        title = _esc(hook_title.upper() if style.uppercase else hook_title)
        anim = r"{\pos(540,560)\fad(120,200)\fscx70\fscy70\t(0,180,\fscx104\fscy104)\t(180,260,\fscx100\fscy100)}"
        lines.append(f"Dialogue: 2,{_ts(0)},{_ts(hook_end)},Hook,,0,0,0,,{anim}{title}")

    for group in group_words(words, style.max_words, style.max_chars):
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
                elif kk == k:
                    parts.append(
                        r"{\c" + style.accent + r"&\fscx100\fscy100\t(0,90,\fscx112\fscy112)\t(90,160,\fscx106\fscy106)}"
                        + txt + r"{\c" + style.text + r"&\fscx100\fscy100}"
                    )
                elif kk in emphasis:
                    parts.append(r"{\c" + style.accent + "&}" + txt + r"{\c" + style.text + "&}")
                else:
                    parts.append(txt)
            pop = r"\fscx82\fscy82\t(0,110,\fscx100\fscy100)" if pos == 0 else ""
            y = style.y
            lines.append(
                f"Dialogue: 1,{_ts(seg_start)},{_ts(seg_end)},Sub,,0,0,0,,{{\\pos(540,{y}){pop}}}" + " ".join(parts)
            )
    return "\n".join(lines) + "\n"
