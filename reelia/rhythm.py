"""Ritmo: decide qué partes del vídeo original se quedan.

Trabaja solo con la transcripción palabra a palabra, así que es rápido y
determinista. La IA aporta rangos extra a eliminar (tomas falsas, frases
repetidas) mediante `EditPlan.drop`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Span, Word, normalize


@dataclass(frozen=True)
class Rhythm:
    key: str
    label: str
    description: str
    max_gap: float  # pausa máxima que se conserva entre palabras (s)
    pad_before: float  # aire antes de cada palabra (s)
    pad_after: float  # aire después de cada palabra (s)
    remove_fillers: bool
    remove_retakes: bool
    cut: bool = True


RHYTHMS: dict[str, Rhythm] = {
    "rapido": Rhythm(
        "rapido", "Rápido", "Quita silencios, pausas y muletillas. El ritmo de los reels que enganchan.",
        max_gap=0.10, pad_before=0.04, pad_after=0.06, remove_fillers=True, remove_retakes=True,
    ),
    "dinamico": Rhythm(
        "dinamico", "Dinámico", "Quita silencios y muletillas, pero deja respirar las frases.",
        max_gap=0.25, pad_before=0.06, pad_after=0.10, remove_fillers=True, remove_retakes=True,
    ),
    "natural": Rhythm(
        "natural", "Natural", "Solo quita los silencios largos y las tomas falsas.",
        max_gap=0.60, pad_before=0.10, pad_after=0.18, remove_fillers=False, remove_retakes=True,
    ),
    "sin_tocar": Rhythm(
        "sin_tocar", "Sin tocar", "No corta nada. Solo subtítulos, gancho y formato vertical.",
        max_gap=1e9, pad_before=0, pad_after=0, remove_fillers=False, remove_retakes=False, cut=False,
    ),
}

FILLERS = {
    "eh", "ehh", "ehhh", "ehm", "em", "emm", "mm", "mmm", "hmm", "mhm",
    "ah", "ahh", "uh", "uhm", "um", "umm", "este", "bueno",
}
# "este" y "bueno" solo cuentan como muletilla si van aislados entre pausas.
_CONTEXT_FILLERS = {"este", "bueno"}


def is_filler(words: list[Word], i: int) -> bool:
    w = words[i]
    n = w.norm
    if n not in FILLERS:
        return False
    if n not in _CONTEXT_FILLERS:
        return True
    gap_before = w.start - words[i - 1].end if i > 0 else 1.0
    gap_after = words[i + 1].start - w.end if i + 1 < len(words) else 1.0
    return gap_before > 0.25 and gap_after > 0.25


def detect_retakes(words: list[Word], ngram: int = 3, window: int = 30) -> list[tuple[int, int]]:
    """Encuentra frases que se empiezan, se cortan y se repiten.

    Si las mismas `ngram` palabras vuelven a aparecer poco después, damos por
    hecho que la primera versión fue una toma falsa y la quitamos entera.
    """
    norms = [w.norm for w in words]
    drops: list[tuple[int, int]] = []
    i = 0
    while i + ngram <= len(words):
        key = norms[i : i + ngram]
        if not all(key):
            i += 1
            continue
        found = None
        for j in range(i + ngram, min(len(words) - ngram + 1, i + window)):
            if norms[j : j + ngram] == key:
                found = j
                break
        if found is not None:
            # Solo es toma falsa si entre medias hay una pausa o una corrección.
            between = words[i:found]
            longest_pause = max(
                (words[k + 1].start - words[k].end for k in range(i, found)), default=0
            )
            if longest_pause > 0.3 or len(between) <= ngram + 6:
                drops.append((i, found - 1))
                i = found
                continue
        i += 1
    return drops


def dropped_indices(words: list[Word], rhythm: Rhythm, extra: list[tuple[int, int]]) -> set[int]:
    out: set[int] = set()
    if not rhythm.cut:
        return out
    if rhythm.remove_fillers:
        out |= {i for i in range(len(words)) if is_filler(words, i)}
    ranges = list(extra)
    if rhythm.remove_retakes:
        ranges += detect_retakes(words)
    for a, b in ranges:
        a, b = max(0, a), min(len(words) - 1, b)
        out |= set(range(a, b + 1))
    return out


def keep_spans(
    words: list[Word], duration: float, rhythm: Rhythm, extra_drops: list[tuple[int, int]] | None = None
) -> tuple[list[Span], set[int]]:
    """Devuelve los tramos a conservar y las palabras eliminadas."""
    drops = dropped_indices(words, rhythm, extra_drops or [])
    if not rhythm.cut or not words:
        return [Span(0.0, duration)], drops

    spans: list[Span] = []
    cut_pending = False  # hay palabras eliminadas desde el último tramo
    prev_kept: Word | None = None
    for i, w in enumerate(words):
        if i in drops:
            cut_pending = True
            if spans and prev_kept is not None:
                # Que el relleno del tramo anterior no se coma la palabra eliminada.
                spans[-1].end = min(spans[-1].end, max(prev_kept.end, w.start))
            continue
        s = max(0.0, w.start - rhythm.pad_before)
        e = min(duration, w.end + rhythm.pad_after)
        if cut_pending and i > 0:
            s = max(s, words[i - 1].end)
        if spans and not cut_pending and s - spans[-1].end <= rhythm.max_gap:
            spans[-1].end = max(spans[-1].end, e)
        else:
            if spans and s < spans[-1].end:
                s = spans[-1].end
            spans.append(Span(s, e))
        cut_pending = False
        prev_kept = w
    # Tramos minúsculos producen saltos raros; los descartamos.
    spans = [sp for sp in spans if sp.duration >= 0.12]
    return spans or [Span(0.0, duration)], drops


class TimeMap:
    """Convierte tiempos del vídeo original a tiempos del reel ya cortado."""

    def __init__(self, spans: list[Span]):
        self.spans = spans
        self.offsets = []
        acc = 0.0
        for sp in spans:
            self.offsets.append(acc)
            acc += sp.duration
        self.total = acc

    def map(self, t: float) -> float | None:
        for sp, off in zip(self.spans, self.offsets):
            if sp.start <= t <= sp.end:
                return off + (t - sp.start)
        return None

    def map_word(self, w: Word) -> Word | None:
        s, e = self.map(w.start), self.map(w.end)
        if s is None and e is None:
            # La palabra puede caer en el relleno entre tramos; probamos su centro.
            mid = self.map((w.start + w.end) / 2)
            if mid is None:
                return None
            s = e = mid
        if s is None:
            s = max(0.0, e - (w.end - w.start))
        if e is None:
            e = s + (w.end - w.start)
        return Word(w.text, s, max(e, s + 0.05))


def remap_words(words: list[Word], spans: list[Span], drops: set[int]) -> tuple[list[Word], list[int]]:
    """Palabras que sobreviven, ya en la línea de tiempo del reel, y sus índices originales."""
    tm = TimeMap(spans)
    out, idx = [], []
    for i, w in enumerate(words):
        if i in drops:
            continue
        m = tm.map_word(w)
        if m is not None:
            out.append(m)
            idx.append(i)
    return out, idx


__all__ = [
    "RHYTHMS", "Rhythm", "TimeMap", "detect_retakes", "is_filler", "keep_spans", "normalize", "remap_words",
]
