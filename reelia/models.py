"""Estructuras de datos compartidas por todo el pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Word:
    text: str
    start: float
    end: float

    @property
    def norm(self) -> str:
        return normalize(self.text)


@dataclass
class Span:
    """Tramo [start, end) del vídeo original que se conserva."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class EditPlan:
    hook_title: str = ""
    hook_line: str = ""
    # Rangos de índices de palabras [desde, hasta] (ambos incluidos) que se eliminan.
    drop: list[tuple[int, int]] = field(default_factory=list)
    drop_reasons: list[str] = field(default_factory=list)
    # Índices de palabras a destacar en los subtítulos.
    emphasis: list[int] = field(default_factory=list)
    source: str = "heuristica"

    def to_dict(self) -> dict:
        return asdict(self)


_ACCENTS = str.maketrans("áéíóúüàèìòùâêîôû", "aeiouuaeiouaeiou")


def normalize(text: str) -> str:
    t = text.lower().translate(_ACCENTS)
    return "".join(ch for ch in t if ch.isalnum())
