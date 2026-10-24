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
    # Efectos en pantalla (ver effects.py) y rangos de palabras con zoom de énfasis.
    effects: list[dict] = field(default_factory=list)
    zooms: list[tuple[int, int]] = field(default_factory=list)
    # Índices de palabras tras las que hay una pausa con sentido (antes de un dato, tras una pregunta): se respeta.
    pauses: list[int] = field(default_factory=list)
    # Lo que decide el creador en "Revisa lo que dices": frases que quita (cut) o recupera (restore).
    cut: list[tuple[int, int]] = field(default_factory=list)
    restore: list[tuple[int, int]] = field(default_factory=list)
    # Silencio dramático: palabras (inicio de la frase clave) antes de las que se cortan música y efectos en seco.
    silence: list[int] = field(default_factory=list)
    # Estilo de música que la IA recomienda para este vídeo (ver musica.STYLES).
    music: str = ""
    # Look de color que la IA recomienda (ver media.LOOKS).
    color: str = ""
    source: str = "heuristica"

    @classmethod
    def from_dict(cls, d: dict) -> "EditPlan":
        return cls(
            hook_title=d.get("hook_title", ""),
            hook_line=d.get("hook_line", ""),
            drop=[tuple(x) for x in d.get("drop", [])],
            drop_reasons=list(d.get("drop_reasons", [])),
            emphasis=list(d.get("emphasis", [])),
            effects=list(d.get("effects", [])),
            zooms=[tuple(x) for x in d.get("zooms", [])],
            pauses=list(d.get("pauses", [])),
            cut=[tuple(x) for x in d.get("cut", [])],
            restore=[tuple(x) for x in d.get("restore", [])],
            silence=[int(i) for i in d.get("silence", [])],
            music=str(d.get("music", "")),
            color=str(d.get("color", "")),
            source=d.get("source", "heuristica"),
        )

    def to_dict(self) -> dict:
        return asdict(self)


_ACCENTS = str.maketrans("áéíóúüàèìòùâêîôû", "aeiouuaeiouaeiou")


def normalize(text: str) -> str:
    t = text.lower().translate(_ACCENTS)
    return "".join(ch for ch in t if ch.isalnum())
