"""El "editor" con IA: decide gancho, tomas falsas y palabras a destacar.

Funciona con Claude o con ChatGPT (cada uno con tu propia clave). Si no hay
clave, Reelia sigue funcionando con heurísticas locales.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .models import EditPlan, Word

CLAUDE_MODEL = "claude-opus-5-5"
OPENAI_MODEL = "gpt-4o"

EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "hook_title": {"type": "string", "description": "Título corto en pantalla para los primeros segundos (máx. 7 palabras)."},
        "hook_line": {"type": "string", "description": "Una frase de gancho alternativa que el creador podría grabar."},
        "drop": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from": {"type": "integer"},
                    "to": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["from", "to", "reason"],
                "additionalProperties": False,
            },
        },
        "emphasis": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["hook_title", "hook_line", "drop", "emphasis"],
    "additionalProperties": False,
}

EDIT_SYSTEM = """Eres el editor de vídeo de un creador de contenido que publica reels.
Recibes la transcripción palabra a palabra de una toma en bruto. Cada palabra lleva su índice entre corchetes
y las pausas largas aparecen como (pausa Xs).

Tu trabajo:
1. drop: rangos de índices (ambos incluidos) que hay que quitar porque son errores: frases empezadas y repetidas
   (quita SIEMPRE la versión fallida y deja la buena, normalmente la última), muletillas, "espera, lo repito",
   comentarios al equipo, ruido. Nunca quites contenido bueno. Si no hay nada que quitar, devuelve [].
2. hook_title: el texto que aparece grande en pantalla al principio. Corto, concreto, que genere curiosidad,
   con las palabras del propio creador cuando sea posible. Sin emojis ni comillas.
3. hook_line: una frase de gancho alternativa por si el creador quiere regrabar el arranque.
4. emphasis: índices de 3 a 8 palabras clave que conviene resaltar en los subtítulos (cifras, conceptos clave).
Respeta el idioma del vídeo. Sigue las instrucciones del creador si las hay."""


def transcript_for_prompt(words: list[Word]) -> str:
    out = []
    for i, w in enumerate(words):
        if i:
            gap = w.start - words[i - 1].end
            if gap >= 0.5:
                out.append(f"(pausa {gap:.1f}s)")
        out.append(f"[{i}] {w.text}")
    return " ".join(out)


@dataclass
class AIConfig:
    provider: str = "none"  # claude | openai | none
    anthropic_key: str | None = None
    openai_key: str | None = None
    claude_model: str = CLAUDE_MODEL
    openai_model: str = OPENAI_MODEL

    @property
    def enabled(self) -> bool:
        return (self.provider == "claude" and bool(self.anthropic_key)) or (
            self.provider == "openai" and bool(self.openai_key)
        )


def _ask_json(cfg: AIConfig, system: str, user: str, schema: dict) -> dict:
    if cfg.provider == "claude":
        import anthropic

        client = anthropic.Anthropic(api_key=cfg.anthropic_key)
        resp = client.beta.messages.create(
            model=cfg.claude_model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("Claude no ha podido procesar este vídeo")
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)
    if cfg.provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=cfg.openai_key)
        resp = client.chat.completions.create(
            model=cfg.openai_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_schema", "json_schema": {"name": "respuesta", "schema": schema, "strict": True}},
        )
        return json.loads(resp.choices[0].message.content)
    raise RuntimeError("No hay proveedor de IA configurado")


def plan_edit(cfg: AIConfig, words: list[Word], instructions: str = "", hook_template: str = "") -> EditPlan:
    user = "TRANSCRIPCIÓN:\n" + transcript_for_prompt(words)
    if hook_template:
        user += f"\n\nPLANTILLA DE GANCHO elegida por el creador (adáptala a lo que dice el vídeo): {hook_template}"
    if instructions.strip():
        user += f"\n\nINSTRUCCIONES DEL CREADOR:\n{instructions.strip()}"
    data = _ask_json(cfg, EDIT_SYSTEM, user, EDIT_SCHEMA)
    n = len(words)
    drops, reasons = [], []
    for d in data.get("drop", []):
        a, b = int(d["from"]), int(d["to"])
        if 0 <= a <= b < n and (b - a) < n * 0.5:  # nunca dejar que borre medio vídeo
            drops.append((a, b))
            reasons.append(d.get("reason", ""))
    return EditPlan(
        hook_title=data.get("hook_title", "").strip(),
        hook_line=data.get("hook_line", "").strip(),
        drop=drops,
        drop_reasons=reasons,
        emphasis=[i for i in data.get("emphasis", []) if 0 <= int(i) < n],
        source=cfg.provider,
    )


# --- Agente de ideas (paso 0: antes de grabar) ---------------------------------

IDEA_SCHEMA = {
    "type": "object",
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "hook": {"type": "string"},
                    "script": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["hook", "script", "why"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ideas"],
    "additionalProperties": False,
}

IDEA_SYSTEM = """Eres el guionista de reels de un creador. Le das ideas listas para grabar en una sola toma
de 30 a 60 segundos con el móvil. Para cada idea: un gancho que se dice en los 3 primeros segundos, un guion
corto escrito como habla el creador (frases cortas, sin tecnicismos, con una llamada a la acción al final) y
una línea explicando por qué puede funcionar. Si te pasa ejemplos de cómo habla, imita su estilo."""


def generate_ideas(cfg: AIConfig, topic: str, audience: str = "", voice_samples: str = "", n: int = 3) -> list[dict]:
    user = f"Tema: {topic}\nNúmero de ideas: {n}"
    if audience:
        user += f"\nPúblico: {audience}"
    if voice_samples:
        user += f"\n\nASÍ HABLA EL CREADOR (transcripciones de reels anteriores):\n{voice_samples[:6000]}"
    return _ask_json(cfg, IDEA_SYSTEM, user, IDEA_SCHEMA).get("ideas", [])


def fallback_hook(words: list[Word], max_words: int = 6) -> str:
    """Sin IA: usa la primera frase del vídeo como título."""
    out = []
    for w in words:
        out.append(w.text)
        if w.text.rstrip()[-1:] in ".?!" or len(out) >= max_words:
            break
    return " ".join(out).rstrip(",.;:")
