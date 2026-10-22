"""El "editor" con IA: decide gancho, tomas falsas y palabras a destacar.

Funciona con Claude o con ChatGPT (cada uno con tu propia clave). Si no hay
clave, Imán sigue funcionando con heurísticas locales.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .models import EditPlan, Word

CLAUDE_MODEL = "claude-opus-5-5"
OPENAI_MODEL = "gpt-4o"

EFFECT_TYPES = ["lista", "palabra", "titular", "cifra", "frase", "tecleo", "color", "comentario",
                "contador", "portada", "cta", "dato", "bruto", "fantasma", "pagina", "detras", "fondo", "desenfoque",
                "ubicacion", "oferta", "ruta", "testimonio", "plazas", "precio"]
FREE_TEXT_TYPES = ("titular", "cifra", "frase", "tecleo", "color", "comentario", "contador", "portada", "cta", "dato",
                   "bruto", "fantasma", "pagina", "detras", "fondo", "desenfoque",
                   "ubicacion", "oferta", "ruta", "testimonio", "plazas", "precio")
LISTA_LOOKS = ("checklist", "capitulos", "itinerario")
TITULAR_LOOKS = ("revista", "elegante", "pizarra", "mixto")
COLORS = ("rosa", "amarillo", "negro", "azul", "rojo", "verde")
LOOK_ENUM = ["", *TITULAR_LOOKS, *LISTA_LOOKS, "enfoque", *COLORS]

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
        "effects": {
            "type": "array",
            "description": "Efectos en pantalla. Úsalos con moderación: 0 a 3 por reel.",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": EFFECT_TYPES},
                    "title": {"type": "string", "description": "lista: título corto opcional, o vacío"},
                    "items": {
                        "type": "array",
                        "description": "lista: de 2 a 5 puntos, cada uno con el índice de la palabra donde se empieza a decir",
                        "items": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}, "at_word": {"type": "integer"}},
                            "required": ["text", "at_word"],
                            "additionalProperties": False,
                        },
                    },
                    "until_word": {"type": "integer", "description": "lista: índice de la última palabra del bloque"},
                    "word": {"type": "integer", "description": "palabra, titular, cifra, frase: índice de la palabra donde aparece"},
                    "text": {"type": "string", "description": "texto principal del efecto"},
                    "subtitle": {"type": "string", "description": "titular: remate en letra manuscrita; cifra: qué mide la cifra; si no, vacío"},
                    "look": {"type": "string", "enum": LOOK_ENUM,
                             "description": "titular: revista, elegante, pizarra o mixto; lista: checklist, capitulos o vacío; "
                                            "frase: enfoque o vacío; color: el color; si no, vacío"},
                },
                "required": ["type", "title", "items", "until_word", "word", "text", "subtitle", "look"],
                "additionalProperties": False,
            },
        },
        "zooms": {
            "type": "array",
            "description": "Rangos [desde, hasta] de palabras donde acercar la cámara para dar énfasis (0 a 4).",
            "items": {
                "type": "object",
                "properties": {"from": {"type": "integer"}, "to": {"type": "integer"}},
                "required": ["from", "to"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["hook_title", "hook_line", "drop", "emphasis", "effects", "zooms"],
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
5. effects: solo si aportan.
   - "lista": cuando el creador enumera pasos o razones ("uno…, dos…, tres…"). Cada punto, en 2 a 5 palabras,
     con el índice donde empieza a decirlo. Para "lista" deja word en -1 y text vacío.
   - "palabra": una palabra clave que salta gigante en pantalla un segundo.
   - "titular": la frase más potente del vídeo como titular de revista en la parte de arriba (text: 3 a 6
     palabras; subtitle: 1 a 3 palabras de remate en letra manuscrita, que no repitan text; look: revista,
     elegante, pizarra o mixto; mixto = palabras en mayúsculas sobre cajitas y el remate grande en cursiva,
     ideal para preguntas tipo "¿CUÁNTO CUESTA…?"). Dura hasta until_word.
   - "cifra": un número que impresiona (text: solo la cifra, p. ej. "80" o "3x"; subtitle: qué mide, 3 a 7
     palabras). Ocupa la pantalla dos segundos.
   - "frase": una frase corta y emocional (1 a 4 palabras) a pantalla completa en letra manuscrita. Con look
     "enfoque", una afirmación de hasta 12 palabras en serif que entra desenfocada sobre fondo oscuro.
   - "dato": etiqueta pequeña junto a la cara con un dato (text: la cifra, "12"; subtitle: "horas de vídeo").
   - "contador": cuando el creador habla de cuánto dura la toma en bruto o del tiempo que ahorra; muestra la
     duración real de la toma bajando hasta la del reel. Deja text en "-" y title y subtitle vacíos.
   - "portada": el vídeo convertido en portada de revista (text: la cabecera, 1 palabra corta, p. ej. la
     marca o el tema; subtitle: un titular de portada de 4 a 8 palabras). Úsalo como mucho una vez.
   - "bruto": tarjeta inclinada con la toma original sin cortar, cuando el creador habla de cómo grabó o de
     que no ha editado (title: etiqueta corta, p. ej. "Bruto"; subtitle: nota a mano, p. ej. "tal cual, sin tocar").
   - "fantasma": un eco semitransparente del propio creador durante una frase dramática o de sorpresa
     (text: "-"). Muy de vez en cuando.
   - "pagina": el vídeo encogido dentro de una hoja de revista (text: titular de la hoja, 2 a 6 palabras;
     subtitle: remate a mano o vacío).
   - "detras": una palabra gigante DETRÁS del creador, que le tapa parte de las letras (text: 1 palabra,
     la marca o el concepto clave; subtitle: 1 a 3 palabras encima o vacío; look: color o vacío). Es el efecto
     más llamativo: úsalo en el gancho o en el momento clave, una vez.
   - "fondo": el fondo cambia a un color liso detrás del creador (look: el color; text: palabra blanca
     detrás o "-"). Para un remate o un cambio de tema.
   - "desenfoque": el fondo se desenfoca y el creador queda nítido, para una frase íntima o importante
     (text: "-").
   - "cta": al final, si el creador pide comentar una palabra para recibir algo (text: esa palabra;
     subtitle: el aviso, p. ej. "Te envío el enlace por privado").
   - "tecleo": una caja que se escribe sola con una petición o mensaje que el creador cuenta que escribe
     (text: hasta 120 caracteres; title: etiqueta corta, p. ej. "Le pido a la IA").
   - "color": golpe de color a pantalla completa durante un segundo, con una palabra enorme (text: 1 palabra;
     subtitle: 1 a 3 palabras o vacío; look: el color). Para cambios de tema o remates. Puede haber hasta 3
     seguidos, uno por palabra, si el creador enumera.
   - "comentario": burbuja de un comentario de un seguidor al principio, solo si el creador responde a un
     comentario (text: el comentario; title: nombre de usuario o vacío). word suele ser 0.
   - "ubicacion": chincheta con el nombre de un lugar (text: el lugar; subtitle: país o zona).
   - "oferta": tarjeta de oferta (text: qué se vende o el destino; subtitle: el precio; title: lo que incluye).
   - "ruta": avión de un sitio a otro (text: origen; subtitle: destino; title: duración o vacío).
   - "testimonio": reseña con cinco estrellas (text: lo que dijo el cliente o alumno; subtitle: quién lo dijo).
   - "plazas": aviso rojo de escasez arriba (text: "Solo 7 plazas", "Acaba el domingo").
   - "precio": etiqueta de precio (text: precio nuevo; subtitle: precio anterior tachado o vacío; title: "-30%" o vacío).
   En "lista", look "itinerario" muestra los días de un viaje en una línea de tiempo; look "capitulos" muestra un índice numerado que se ilumina por partes; look "checklist" muestra casillas arriba que se marcan al decir cada punto (bueno para
   "lo que hace" o "lo que no necesitas"); vacío muestra la lista grande en el centro.
   Rellena siempre todos los campos: los que no use el tipo van vacíos, [] o -1. Como mucho uno de cada
   tipo y nunca dos efectos a la vez.
6. zooms: rangos cortos (una frase) donde acercar la cámara para subrayar una idea fuerte.
Respeta el idioma del vídeo. Sigue las instrucciones del creador si las hay."""

REVISE_SYSTEM = EDIT_SYSTEM + """

Ahora el reel ya está montado y el creador te pide cambios, como a su editor. Recibes el plan actual en JSON.
Devuelve el plan COMPLETO actualizado: conserva todo lo que no te pide cambiar y aplica solo lo que pide.
Si pide cambiar el ritmo o el estilo de subtítulos, indícalo en settings (si no, deja los campos vacíos).
En reply, responde al creador en una frase corta diciendo qué has cambiado."""


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
    provider: str = "none"  # iman | claude | openai | none
    anthropic_key: str | None = None
    openai_key: str | None = None
    claude_model: str = CLAUDE_MODEL
    openai_model: str = OPENAI_MODEL
    license_key: str | None = None
    license_instance: str | None = None

    @property
    def enabled(self) -> bool:
        return (
            self.provider == "iman"  # con licencia, o en prueba gratis limitada
            or (self.provider == "claude" and bool(self.anthropic_key))
            or (self.provider == "openai" and bool(self.openai_key))
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


def plan_edit(cfg: AIConfig, words: list[Word], instructions: str = "", hook_template: str = "",
              pack: str = "") -> EditPlan:
    if cfg.provider == "iman":
        from . import cloud

        data = cloud.call(cfg, "plan", {"words": [w.__dict__ for w in words], "instructions": instructions,
                                        "hook_template": hook_template, "pack": pack})
        return _plan_from(data, len(words), "iman")
    return _plan_from(plan_edit_raw(cfg, words, instructions, hook_template, pack), len(words), cfg.provider)


def plan_edit_raw(cfg: AIConfig, words: list[Word], instructions: str = "", hook_template: str = "",
                  pack: str = "") -> dict:
    from . import packs

    user = "TRANSCRIPCIÓN:\n" + transcript_for_prompt(words)
    if packs.get(pack).guide:
        user += "\n\n" + packs.get(pack).guide
    if hook_template:
        user += f"\n\nPLANTILLA DE GANCHO elegida por el creador (adáptala a lo que dice el vídeo): {hook_template}"
    if instructions.strip():
        user += f"\n\nINSTRUCCIONES DEL CREADOR:\n{instructions.strip()}"
    return _ask_json(cfg, EDIT_SYSTEM, user, EDIT_SCHEMA)


def _look(kind: str, look: str) -> str:
    if kind == "titular":
        return look if look in TITULAR_LOOKS else "revista"
    if kind == "color":
        return look if look in COLORS else "rosa"
    if kind in ("detras", "fondo"):
        return look if look in COLORS else ""
    if kind == "frase" and look == "enfoque":
        return look
    return ""


def _plan_from(data: dict, n: int, source: str) -> EditPlan:
    drops, reasons = [], []
    for d in data.get("drop", []):
        a, b = int(d["from"]), int(d["to"])
        if 0 <= a <= b < n and (b - a) < n * 0.5:  # nunca dejar que borre medio vídeo
            drops.append((a, b))
            reasons.append(d.get("reason", ""))
    effects = []
    for fx in data.get("effects", []):
        if fx.get("type") == "lista":
            items = [it for it in fx.get("items", []) if 0 <= int(it.get("at_word", -1)) < n and it.get("text")]
            if len(items) >= 2:
                until = int(fx.get("until_word", -1))
                effects.append({"type": "lista", "title": fx.get("title", ""), "items": items,
                                "until_word": until if 0 <= until < n else None,
                                "look": fx.get("look") if fx.get("look") in LISTA_LOOKS else ""})
        elif fx.get("type") == "palabra" and 0 <= int(fx.get("word", -1)) < n:
            effects.append({"type": "palabra", "word": int(fx["word"]), "text": fx.get("text", "")})
        elif fx.get("type") in FREE_TEXT_TYPES and 0 <= int(fx.get("word", -1)) < n \
                and str(fx.get("text", "")).strip():
            until = int(fx.get("until_word", -1))
            effects.append({"type": fx["type"], "word": int(fx["word"]), "text": str(fx["text"]).strip()[:140],
                            "subtitle": str(fx.get("subtitle", "")).strip()[:60],
                            "title": str(fx.get("title", "")).strip()[:40],
                            "look": _look(fx["type"], fx.get("look", "")),
                            "until_word": until if int(fx["word"]) < until < n else None})
    zooms = [(int(z["from"]), int(z["to"])) for z in data.get("zooms", [])
             if 0 <= int(z["from"]) <= int(z["to"]) < n]
    return EditPlan(
        hook_title=data.get("hook_title", "").strip(),
        hook_line=data.get("hook_line", "").strip(),
        drop=drops,
        drop_reasons=reasons,
        emphasis=[i for i in data.get("emphasis", []) if 0 <= int(i) < n],
        effects=effects,
        zooms=zooms,
        source=source,
    )


REVISE_SCHEMA = {
    **EDIT_SCHEMA,
    "properties": {
        **EDIT_SCHEMA["properties"],
        "settings": {
            "type": "object",
            "properties": {
                "rhythm": {"type": "string", "enum": ["", "rapido", "dinamico", "natural", "sin_tocar"]},
                "style": {"type": "string", "enum": ["", "impacto", "editorial", "palabra", "karaoke", "caja", "neon"]},
            },
            "required": ["rhythm", "style"],
            "additionalProperties": False,
        },
        "reply": {"type": "string"},
    },
    "required": EDIT_SCHEMA["required"] + ["settings", "reply"],
}


def _plan_to_prompt(plan: EditPlan) -> dict:
    return {
        "hook_title": plan.hook_title,
        "hook_line": plan.hook_line,
        "drop": [{"from": a, "to": b, "reason": r} for (a, b), r in
                 zip(plan.drop, plan.drop_reasons + [""] * len(plan.drop))],
        "emphasis": plan.emphasis,
        "effects": plan.effects,
        "zooms": [{"from": a, "to": b} for a, b in plan.zooms],
    }


def revise_plan(cfg: AIConfig, words: list[Word], plan: EditPlan, message: str,
                rhythm: str, style: str) -> tuple[EditPlan, dict, str]:
    """Aplica un cambio pedido en lenguaje natural. Devuelve (plan, ajustes, respuesta)."""
    if cfg.provider == "iman":
        from . import cloud

        data = cloud.call(cfg, "revise", {"words": [w.__dict__ for w in words], "plan": plan.to_dict(),
                                          "message": message, "rhythm": rhythm, "style": style})
        settings = {k: v for k, v in (data.get("settings") or {}).items() if v}
        return _plan_from(data, len(words), "iman"), settings, data.get("reply", "").strip()
    data = revise_plan_raw(cfg, words, plan, message, rhythm, style)
    settings = {k: v for k, v in (data.get("settings") or {}).items() if v}
    return _plan_from(data, len(words), cfg.provider), settings, data.get("reply", "").strip()


def revise_plan_raw(cfg: AIConfig, words: list[Word], plan: EditPlan, message: str, rhythm: str, style: str) -> dict:
    user = (
        "TRANSCRIPCIÓN:\n" + transcript_for_prompt(words)
        + "\n\nPLAN ACTUAL:\n" + json.dumps(_plan_to_prompt(plan), ensure_ascii=False)
        + f"\n\nAJUSTES ACTUALES: ritmo={rhythm}, estilo={style}"
        + f"\n\nEL CREADOR PIDE:\n{message.strip()}"
    )
    return _ask_json(cfg, REVISE_SYSTEM, user, REVISE_SCHEMA)


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
    if cfg.provider == "iman":
        from . import cloud

        return cloud.call(cfg, "ideas", {"topic": topic, "audience": audience,
                                         "voice_samples": voice_samples[:6000], "n": n}).get("ideas", [])
    user = f"Tema: {topic}\nNúmero de ideas: {n}"
    if audience:
        user += f"\nPúblico: {audience}"
    if voice_samples:
        user += f"\n\nASÍ HABLA EL CREADOR (transcripciones de reels anteriores):\n{voice_samples[:6000]}"
    return _ask_json(cfg, IDEA_SYSTEM, user, IDEA_SCHEMA).get("ideas", [])


# --- Kit de marca: la IA escribe el cierre a partir de una frase -------------------

BRAND_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "cta": {"type": "string"},
        "font": {"type": "string", "enum": ["Moderna", "Impacto", "Condensada", "Elegante", "Manuscrita"]},
        "sector": {"type": "string", "enum": ["general", "viajes", "cursos", "productos", "empresas"]},
    },
    "required": ["name", "cta", "font", "sector"],
    "additionalProperties": False,
}

BRAND_SYSTEM = """Preparas el kit de marca de un negocio o creador para sus reels de Instagram y TikTok.
Te describen el negocio en una frase. Devuelve: el nombre de la marca tal cual lo dicen (o vacío si no lo
dicen), una llamada a la acción para el cierre del reel (máximo 5 palabras, en imperativo, concreta para ese
negocio, p. ej. "Reserva tu viaje por WhatsApp", "Apúntate al curso", "Pide el tuyo hoy") y la fuente que mejor
encaja: Moderna (limpia, versátil), Impacto (fuerte, ventas), Condensada (titulares, deporte), Elegante (lujo,
moda, viajes premium) o Manuscrita (cercana, artesanal). Y el sector: viajes, cursos (formación, coaching),
productos (tienda, marca de producto), empresas (servicios, negocio local) o general."""


def brand_copy(cfg: AIConfig, description: str) -> dict:
    if cfg.provider == "iman":
        from . import cloud

        return cloud.call(cfg, "brand", {"description": description})
    data = _ask_json(cfg, BRAND_SYSTEM, f"Negocio: {description}", BRAND_SCHEMA)
    return {"name": data.get("name", "")[:40], "cta": data.get("cta", "")[:40], "font": data.get("font", ""),
            "sector": data.get("sector", "")}


def fallback_hook(words: list[Word], max_words: int = 6) -> str:
    """Sin IA: usa la primera frase del vídeo como título."""
    out = []
    for w in words:
        out.append(w.text)
        if w.text.rstrip()[-1:] in ".?!" or len(out) >= max_words:
            break
    return " ".join(out).rstrip(",.;:")
