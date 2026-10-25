"""Zona Inspiración: analiza un reel de otra persona y explica por qué funciona. Copia la forma, nunca el contenido.

Subes un reel que te ha llamado la atención (de la competencia o de quien sea). Imán mide lo que se puede medir
(duración, cortes por segundo, cuándo empieza a hablar, palabras por minuto) y la IA, con los fotogramas y la
transcripción, explica el gancho, la estructura y los trucos de retención, y dice qué parte de la FORMA puedes
llevarte a tus reels (ritmo, tipo de gancho, estilo de letra) y qué no. Nunca se reutiliza su guion ni sus
frases: son suyos. Lo analizado se guarda en tu zona Inspiración y se puede convertir en una plantilla.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from . import ai, config, copystyle, ganchos, jsonfile, media, plantillas

ANALYZE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "De qué va el reel, en 5-8 palabras (para la lista)."},
        "hook": {"type": "string", "description": "Cómo engancha en los primeros 3 s (qué dice y qué pasa en pantalla)."},
        "gancho": {"type": "string", "enum": list(ganchos.GANCHOS),
                   "description": "El gancho visual de Imán que más se parece a lo que hace."},
        "structure": {"type": "string", "description": "La estructura en una frase (gancho → promesa → 3 puntos → cierre…)."},
        "why": {"type": "array", "items": {"type": "string"}, "description": "3 a 5 razones concretas por las que retiene o se comparte."},
        "copy_form": {"type": "array", "items": {"type": "string"},
                      "description": "3 a 5 cosas de la FORMA que el creador puede llevarse (ritmo, tipo de gancho, cómo cierra…). Nunca frases ni el tema."},
        "avoid": {"type": "array", "items": {"type": "string"}, "description": "1 a 3 cosas que no conviene copiar o que fallan."},
        "my_version": {"type": "string",
                       "description": "Una idea de reel con esa misma estructura aplicada al sector del creador: tema y gancho propios, nunca los del vídeo."},
        "score": {"type": "integer", "description": "Potencial de retención de 0 a 100."},
    },
    "required": ["title", "hook", "gancho", "structure", "why", "copy_form", "avoid", "my_version", "score"],
    "additionalProperties": False,
}

ANALYZE_SYSTEM = """Eres un analista de reels. Te paso fotogramas en orden, la transcripción y unas medidas de un reel de OTRA
persona que al creador le ha llamado la atención. Explica por qué funciona (o por qué no) con hechos concretos:
el gancho de los 3 primeros segundos, la estructura, el ritmo, los cambios en pantalla, los subtítulos, el cierre.
Luego di qué puede llevarse el creador DE LA FORMA (ritmo, tipo de gancho, estructura, estilo de letra, cómo cierra)
y qué no. Regla absoluta: nunca propongas reutilizar sus frases, su guion ni su tema; «my_version» es una idea con
esa estructura pero con el tema y el gancho propios del creador y su sector. Sé concreto y corto, sin adjetivos
vacíos. Si no hay voz (solo música y texto), analiza los textos en pantalla."""


def store_dir() -> Path:
    return config.HOME / "inspiracion"


def metrics(src: Path, words: list) -> dict:
    """Lo que se mide sin IA."""
    info = media.probe(src)
    dur = info.duration or 0.0
    rate = copystyle.cut_rate(src)
    first = words[0].start if words else None
    wpm = len(words) / dur * 60 if words and dur else 0.0
    return {"duration": round(dur, 1), "cuts_per_s": round(rate, 2), "cuts": int(round(rate * dur)),
            "rhythm": copystyle.rhythm_for(rate), "first_word_s": round(first, 2) if first is not None else None,
            "wpm": int(wpm), "words": len(words), "vertical": bool(info.height > info.width)}


def _metrics_text(m: dict) -> str:
    bits = [f"duración {m['duration']} s", f"{m['cuts']} cambios de plano ({m['cuts_per_s']} por segundo)"]
    if m.get("first_word_s") is not None:
        bits.append(f"empieza a hablar a los {m['first_word_s']} s")
        bits.append(f"{m['wpm']} palabras por minuto")
    else:
        bits.append("sin voz (o no se ha podido transcribir)")
    return ", ".join(bits)


def analyze(cfg: ai.AIConfig, frames: list[bytes], words: list, m: dict, sector: str = "") -> dict:
    transcript = " ".join(w.text for w in words)[:4000] or "(sin voz)"
    if cfg.provider == "iman":
        import base64

        from . import cloud

        data = cloud.call(cfg, "analizar", {"frames": [base64.b64encode(f).decode() for f in frames[:8]],
                                            "transcript": transcript, "metrics": _metrics_text(m), "sector": sector})
    else:
        data = analyze_raw(cfg, frames, transcript, _metrics_text(m), sector)
    return clean(data)


def analyze_raw(cfg: ai.AIConfig, frames: list[bytes], transcript: str, metrics_text: str, sector: str = "") -> dict:
    user = (f"SECTOR DEL CREADOR: {sector or 'creador de contenido'}\nMEDIDAS: {metrics_text}\n\n"
            f"TRANSCRIPCIÓN DEL REEL AJENO:\n{transcript}\n\nFotogramas del reel, en orden.")
    return ai._ask_json(cfg, ANALYZE_SYSTEM, user, ANALYZE_SCHEMA, images=frames[:8])


def clean(d: dict) -> dict:
    lists = {k: [str(x).strip()[:200] for x in (d.get(k) or []) if str(x).strip()][:5] for k in ("why", "copy_form", "avoid")}
    try:
        score = max(0, min(100, int(d.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    return {"title": str(d.get("title", "")).strip()[:80], "hook": str(d.get("hook", "")).strip()[:300],
            "gancho": d.get("gancho") if d.get("gancho") in ganchos.GANCHOS else "titulo",
            "structure": str(d.get("structure", "")).strip()[:300], **lists,
            "my_version": str(d.get("my_version", "")).strip()[:400], "score": score}


def save(item: dict) -> dict:
    store_dir().mkdir(parents=True, exist_ok=True)
    item = {"id": uuid.uuid4().hex[:8], "created": time.time(), **item}
    jsonfile.save(store_dir() / f"{item['id']}.json", item)
    return item


def listar() -> list[dict]:
    out = []
    for f in store_dir().glob("*.json") if store_dir().exists() else []:
        d = jsonfile.load(f)
        if isinstance(d, dict) and d.get("id"):
            out.append(d)
    return sorted(out, key=lambda d: -float(d.get("created", 0)))


def get(iid: str) -> dict | None:
    if not iid.isalnum():
        return None
    d = jsonfile.load(store_dir() / f"{iid}.json")
    return d if isinstance(d, dict) else None


def borrar(iid: str) -> bool:
    if not iid.isalnum():
        return False
    f = store_dir() / f"{iid}.json"
    if not f.exists():
        return False
    f.unlink()
    return True


def as_template(item: dict, name: str) -> dict:
    """La forma del reel analizado como plantilla: su ritmo, su gancho visual y, si se vio, su estilo de letra."""
    m, a = item.get("metrics") or {}, item.get("analysis") or {}
    opts = {"rhythm": m.get("rhythm", "rapido"), "gancho": a.get("gancho", "titulo"), "hook": True}
    style = item.get("style")
    if isinstance(style, dict) and style.get("font"):
        saved = copystyle.save(name, style, opts["rhythm"])
        opts["style"] = saved["key"]
    return plantillas.crear(name, opts)
