"""Subtítulos en otro idioma: el mismo reel con los textos traducidos (subtítulos, gancho y efectos).

La voz se queda como está; se traducen las frases de los subtítulos por bloques y cada bloque traducido se
reparte en el mismo tramo de tiempo que ocupaba el original. Así el reel sirve para un público que no habla
tu idioma sin volver a grabar nada. Traduce la IA del creador (su clave) o la de Imán.
"""
from __future__ import annotations

from dataclasses import replace

from . import ai, captions
from .models import Word

LANGS = {"en": "inglés", "fr": "francés", "de": "alemán", "it": "italiano", "pt": "portugués", "es": "español",
         "ca": "catalán", "nl": "neerlandés", "ja": "japonés"}

# Efectos cuyos textos son frases para la pantalla (no números de archivo ni coordenadas).
TEXT_TYPES = {"titular", "palabra", "frase", "cta", "dato", "hueca", "marco", "progreso", "paso", "capitulo",
              "bocadillo", "tecleo", "color", "comentario", "portada", "oferta", "ubicacion", "testimonio", "plazas",
              "precio", "texto3d", "etiqueta", "bloques", "particulas", "detras", "fondo", "sube", "choque", "aparece",
              "notificaciones", "chat", "buscador", "pagina", "bruto", "tarjetas", "grafico", "lista"}

TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {
        "phrases": {"type": "array", "items": {"type": "string"},
                    "description": "Las frases traducidas, en el MISMO orden y el MISMO número que las recibidas."},
        "texts": {"type": "array", "items": {"type": "string"},
                  "description": "Los textos de pantalla traducidos, en el mismo orden y número."},
    },
    "required": ["phrases", "texts"],
    "additionalProperties": False,
}

TRANSLATE_SYSTEM = """Traduces los subtítulos y los textos en pantalla de un reel al idioma que te indican.
Recibes las frases de los subtítulos numeradas y los textos de pantalla numerados. Devuelve la traducción de
cada una en el mismo orden y con el mismo número de elementos: nunca juntes dos frases ni dejes ninguna fuera.
Traduce como habla la gente en redes en ese idioma (natural, corto, con el tono del original), no literal.
Deja tal cual los nombres propios, las cifras, los precios y las palabras en mayúsculas que son claves para
comentar ("GUÍA"). Si una frase ya está en ese idioma o es solo una cifra, devuélvela igual."""


def _phrases(words: list[Word]) -> list[list[int]]:
    return captions.group_words(words, 7, 34)


def _spread(text: str, start: float, end: float) -> list[Word]:
    """Reparte las palabras de una frase traducida a lo largo del tramo [start, end], según su longitud."""
    toks = text.split()
    if not toks:
        return []
    weights = [max(2, len(t)) for t in toks]
    total = sum(weights)
    out, t = [], start
    span = max(0.0, end - start)
    for tok, w in zip(toks, weights):
        d = span * w / total
        out.append(Word(tok, round(t, 3), round(t + d, 3)))
        t += d
    return out


def translate(cfg: ai.AIConfig, words: list[Word], texts: list[str], lang: str) -> tuple[list[Word], list[str]]:
    """Palabras nuevas (misma línea de tiempo) y textos de pantalla traducidos. Si algo no cuadra, lo original."""
    lang = (lang or "").lower()[:2]
    if lang not in LANGS or not words:
        return words, texts
    groups = _phrases(words)
    phrases = [" ".join(words[i].text for i in g) for g in groups]
    target = LANGS[lang]
    if cfg.provider == "iman":
        from . import cloud

        data = cloud.call(cfg, "traducir", {"lang": lang, "phrases": phrases[:400], "texts": texts[:80]})
    else:
        data = translate_raw(cfg, phrases, texts, target)
    out_phrases = [str(p) for p in data.get("phrases", [])]
    out_texts = [str(t) for t in data.get("texts", [])]
    if len(out_phrases) != len(phrases):
        return words, texts  # la IA ha juntado o perdido frases: mejor el original que un desajuste
    new_words: list[Word] = []
    for g, text in zip(groups, out_phrases):
        new_words += _spread(text, words[g[0]].start, words[g[-1]].end) or [words[i] for i in g]
    if len(out_texts) != len(texts):
        out_texts = texts
    return new_words, out_texts


def translate_raw(cfg: ai.AIConfig, phrases: list[str], texts: list[str], target: str) -> dict:
    user = f"IDIOMA DESTINO: {target}\n\nFRASES DE LOS SUBTÍTULOS:\n" + "\n".join(f"{i + 1}. {p}" for i, p in enumerate(phrases))
    user += "\n\nTEXTOS DE PANTALLA:\n" + ("\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts)) or "(ninguno)")
    return ai._ask_json(cfg, TRANSLATE_SYSTEM, user, TRANSLATE_SCHEMA)


def effect_texts(active: list[dict]) -> list[tuple[int, str, str]]:
    """(índice del efecto, campo, texto) de cada texto de pantalla traducible, en orden fijo."""
    out = []
    for k, fx in enumerate(active):
        if fx.get("type") not in TEXT_TYPES:
            continue
        if fx.get("type") == "lista":
            for j, it in enumerate(fx.get("items") or []):
                if isinstance(it, dict) and str(it.get("text", "")).strip():
                    out.append((k, f"items.{j}", str(it["text"])))
            if str(fx.get("title", "")).strip():
                out.append((k, "title", str(fx["title"])))
            continue
        for field in ("text", "subtitle", "title"):
            v = str(fx.get(field, "") or "").strip()
            if v and v != "-" and not v.replace(".", "").replace(",", "").isdigit():
                out.append((k, field, v))
    return out


def apply_texts(active: list[dict], refs: list[tuple[int, str, str]], translated: list[str]) -> list[dict]:
    """Copia de los efectos con los textos traducidos puestos en su sitio."""
    out = [dict(fx) for fx in active]
    for (k, field, _), new in zip(refs, translated):
        if field.startswith("items."):
            j = int(field.split(".")[1])
            items = [dict(it) if isinstance(it, dict) else it for it in out[k].get("items") or []]
            if j < len(items) and isinstance(items[j], dict):
                items[j]["text"] = new[:60]
            out[k]["items"] = items
        else:
            out[k][field] = new[:140]
    return out


def localized(cfg: ai.AIConfig, kept: list[Word], hook_title: str, active: list[dict], lang: str):
    """Todo junto: palabras, gancho y efectos traducidos (o los originales si no se puede)."""
    refs = effect_texts(active)
    texts = ([hook_title] if hook_title else []) + [t for _, _, t in refs]
    new_words, new_texts = translate(cfg, kept, texts, lang)
    if new_texts is texts or len(new_texts) != len(texts):
        return new_words, hook_title, active
    if hook_title:
        hook_title, new_texts = new_texts[0][:80], new_texts[1:]
    return new_words, hook_title, apply_texts(active, refs, new_texts)
